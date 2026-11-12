"""Per-stream camera configuration and independent CPU marker diagnostics."""
import base64
import math
import time
from threading import Lock
import cv2
import numpy as np
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from src.camera_configuration import CameraConfiguration, Aruco, calibration_dict, fit_homography
from src.flow.sensing.coordinates import Calibration


class ImageCalibration:
    def __init__(self,settings):
        self.settings=settings
        self.cache={}
        self.percent_matrix,self.fit_report=fit_homography(settings) if settings.enabled else (None,None)
        original=self.for_size(settings.image_size) if settings.enabled else Calibration({})
        self.config,self.matrix=original.config,original.matrix

    def for_size(self,size):
        key=tuple(size)
        if key not in self.cache:
            if len(self.cache)>4:self.cache.clear()
            config=calibration_dict(self.settings,size)
            if not config:self.cache[key]=Calibration({})
            else:
                # Validate the boundary with the legacy geometry adapter, then use
                # the exact all-point fit also used by Vercel's error report.
                base={**config,'image_points':config['image_points'][:4],'world_points':config['world_points'][:4]}
                value=Calibration(base)
                if value.matrix is None:raise ValueError('Invalid pool boundary')
                value.config=config;value.pixels=np.asarray(config['image_points'],dtype=float)
                value.matrix=self.percent_matrix@np.diag([100/size[0],100/size[1],1])
                value.errors=np.asarray(self.fit_report['point_errors_m']);value.reason='VALID'
                self.cache[key]=value
        return self.cache[key]

    def point(self,pixel,size):
        if not self.settings.enabled:return None,'UNCALIBRATED'
        try:return self.for_size(size).point(pixel,list(size))
        except ValueError:return None,'IMAGE_ASPECT_MISMATCH'

    def bbox(self,box,size):
        if not self.settings.enabled:return None,None,'UNCALIBRATED'
        try:return self.for_size(size).bbox(box,list(size))
        except ValueError:return None,None,'IMAGE_ASPECT_MISMATCH'


class MarkerLocator:
    def __init__(self,calibration,settings,revision):
        self.calibration,self.settings,self.revision=calibration,settings,revision
        dictionary=cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco,settings.dictionary))
        self.detector=cv2.aruco.ArucoDetector(dictionary,cv2.aruco.DetectorParameters())
        self.lock=Lock()

    def inspect(self,image):
        a=self.settings
        result={'enabled':a.enabled,'detected':False,'marker_id':a.marker_id,'dictionary':a.dictionary,
            'corners_px':None,'center_px':None,'pixel_heading_deg':None,'heading_deg':None,
            'x_m':None,'y_m':None,'coordinate_valid':False,'coordinate_status':'ARUCO_DISABLED',
            'heading_measured':a.heading_measured,'configuration_revision':self.revision}
        if not a.enabled:return result
        with self.lock:corners,ids,_=self.detector.detectMarkers(image)
        selected=[] if ids is None else [corners[i] for i,n in enumerate(ids.ravel()) if int(n)==a.marker_id]
        if len(selected)!=1:
            result['coordinate_status']='MARKER_NOT_FOUND' if not selected else 'AMBIGUOUS_MARKER'
            return result
        p=np.asarray(selected[0],dtype=float).reshape(4,2);center=p.mean(axis=0)
        dx,dy=(p[0]+p[1])/2-center
        result.update(detected=True,corners_px=p.tolist(),center_px=center.tolist(),
                      pixel_heading_deg=math.degrees(math.atan2(-dy,dx))%360)
        size=[image.shape[1],image.shape[0]]
        world=[self.calibration.point(point,size) for point in p]
        if any(point is None for point,_ in world):
            result['coordinate_status']=next(reason for point,reason in world if point is None)
            return result
        xy=np.array([[point['x'],point['y']] for point,_ in world]);mean=xy.mean(axis=0)
        forward=(xy[0]+xy[1])/2-mean
        result.update(x_m=float(mean[0]),y_m=float(mean[1]),coordinate_valid=True,coordinate_status='VALID')
        if a.heading_measured and a.heading_offset_deg is not None:
            result['heading_deg']=(math.degrees(math.atan2(forward[1],forward[0]))+a.heading_offset_deg)%360
        return result

    def locate(self,frame,now=None):
        observation=self.inspect(frame.image)
        age=(time.monotonic() if now is None else now)-frame.monotonic
        valid=(observation['coordinate_valid'] and observation['heading_measured']
               and observation['heading_deg'] is not None and 0<=age<=.2)
        status=observation['coordinate_status']
        if observation['coordinate_valid']:
            status='tracked' if valid else 'unmeasured_heading' if not observation['heading_measured'] else 'stale_frame'
        return {'timestamp':frame.captured_at,'frame_id':frame.frame_id,'tracking_valid':valid,
            'x':observation['x_m'] if valid else None,'y':observation['y_m'] if valid else None,
            'heading':observation['heading_deg'] if valid else None,'status':status,'unit':'m',
            'heading_offset_measured':observation['heading_measured'],
            'coordinate_frame':self.calibration.config.get('frame_id'),
            'marker_id':self.settings.marker_id}


def create_profile(payload):
    settings=CameraConfiguration.model_validate(payload or {})
    calibration=ImageCalibration(settings.homography)
    if settings.homography.enabled and calibration.matrix is None:raise ValueError('Invalid calibration')
    return calibration,MarkerLocator(calibration,settings.aruco,settings.revision),settings.revision


class Inspection(BaseModel):
    image_base64:str=Field(max_length=2800000)
    configuration:CameraConfiguration


def register_routes(app,identity):
    @app.post('/v1/vision/inspect')
    def inspect(body:Inspection,scope=Depends(identity)):
        from src.modal_api import _decode_image
        try:
            raw=base64.b64decode(body.image_base64,validate=True)
            if not raw or len(raw)>2*1024*1024:raise ValueError('size')
            image=_decode_image(raw)
            calibration,locator,revision=create_profile(body.configuration.model_dump(mode='json'))
            return {'marker_observation':locator.inspect(image),'image_size':[image.shape[1],image.shape[0]],
                'configuration_revision':revision,'homography_enabled':calibration.settings.enabled,
                'homography_report':calibration.fit_report,'command_issued':False}
        except (ValueError,cv2.error):raise HTTPException(422,'Invalid camera configuration or image') from None

    @app.post('/v1/vision/marker')
    def marker(body:Aruco,scope=Depends(identity)):
        dictionary=cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco,body.dictionary))
        image=cv2.aruco.generateImageMarker(dictionary,body.marker_id,600)
        image=cv2.copyMakeBorder(image,100,100,100,100,cv2.BORDER_CONSTANT,value=255)
        from PIL import Image
        from io import BytesIO
        output=BytesIO();dpi=600/(body.marker_size_m/.0254)
        Image.fromarray(image).save(output,format='PNG',dpi=(dpi,dpi))
        return {'image_base64':base64.b64encode(output.getvalue()).decode(),'dictionary':body.dictionary,
            'marker_id':body.marker_id,'marker_size_m':body.marker_size_m,'image_size':[800,800]}
