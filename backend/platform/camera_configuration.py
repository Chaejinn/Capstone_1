"""Validated camera configuration contract shared by Vercel and the CPU vision service."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
import numpy as np

DICTIONARY_COUNTS = {'DICT_4X4_50':50, 'DICT_5X5_100':100, 'DICT_6X6_250':250}


class Point(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    x: float = Field(ge=0,le=100)
    y: float = Field(ge=0,le=100)


class WorldPoint(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)
    x: float = Field(ge=0,le=10000)
    y: float = Field(ge=0,le=10000)


class Homography(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    enabled: StrictBool = False
    image_points: list[Point] = Field(default_factory=list)
    world_points: list[WorldPoint] | None = None
    image_size: tuple[int,int] | None = None
    pool_width_m: float | None = Field(default=None,gt=0,le=10000)
    pool_height_m: float | None = Field(default=None,gt=0,le=10000)
    frame_id: str = Field(default='pool-01',min_length=1,max_length=80)
    calibration_id: str | None = Field(default=None,max_length=80)

    @model_validator(mode='after')
    def geometry(self):
        if self.image_size is not None and any(not 2<=v<=16384 for v in self.image_size):
            raise ValueError('영상 크기가 올바르지 않습니다.')
        if self.world_points is not None and len(self.world_points)!=len(self.image_points):
            raise ValueError('영상 기준점과 실제 좌표의 개수가 같아야 합니다.')
        if not self.enabled and not self.image_points:return self
        if len(self.image_points)<4:
            raise ValueError('먼저 좌상·우상·우하·좌하 순서로 모서리 4점을 지정하세요.')
        pixels=np.array([[v.x,v.y] for v in self.image_points])
        p=pixels[:4]
        edges=np.roll(p,-1,axis=0)-p
        cross=edges[:,0]*np.roll(edges,-1,axis=0)[:,1]-edges[:,1]*np.roll(edges,-1,axis=0)[:,0]
        area=.5*np.sum(p[:,0]*np.roll(p[:,1],-1)-np.roll(p[:,0],-1)*p[:,1])
        if len(np.unique(pixels,axis=0))!=len(pixels) or not np.all(cross>1e-6) or area<100:
            raise ValueError('4점은 화면 기준 시계 방향의 볼록 사각형이어야 합니다 (영상 면적 1% 이상).')
        # Additional points may be in any order, but must stay in the calibrated pool.
        for start,edge in zip(p,edges):
            delta=pixels-start
            if np.any(edge[0]*delta[:,1]-edge[1]*delta[:,0]<-1e-7):
                raise ValueError('추가 기준점은 모서리 4점으로 지정한 보정 영역 안에 있어야 합니다.')
        if self.enabled and (self.image_size is None or self.pool_width_m is None or self.pool_height_m is None):
            raise ValueError('영상 크기와 보정 영역 실측 너비·세로 길이가 필요합니다.')
        if len(pixels)>4 and self.world_points is None:
            raise ValueError('추가 기준점마다 실제 X·Y 좌표를 입력하세요.')
        if self.world_points is not None:
            if self.pool_width_m is None or self.pool_height_m is None:
                raise ValueError('실제 좌표를 사용하려면 보정 영역 크기가 필요합니다.')
            world=np.array([[v.x,v.y] for v in self.world_points])
            if (len(np.unique(world,axis=0))!=len(world) or
                np.any(world[:,0]>self.pool_width_m+1e-9) or np.any(world[:,1]>self.pool_height_m+1e-9)):
                raise ValueError('실제 좌표는 중복 없이 보정 영역 범위 안에 있어야 합니다.')
            if not np.allclose(world[:4],pool_corners(self),atol=1e-8,rtol=0):
                raise ValueError('처음 4점의 실제 좌표는 보정 영역 모서리와 일치해야 합니다.')
        if self.enabled:
            _,report=fit_homography(self)
            if report['max_error_m']>.05:
                worst=int(np.argmax(report['point_errors_m']))+1
                raise ValueError(f'{worst}번 기준점의 재투영 오차가 5cm를 넘습니다. 영상 위치와 실측 좌표를 확인하세요.')
        return self


def pool_corners(h):
    return [[0,h.pool_height_m],[h.pool_width_m,h.pool_height_m],[h.pool_width_m,0],[0,0]]


def fit_homography(h):
    """Hartley-normalized DLT over every pair; no count cap or N-by-N allocation."""
    pixels=np.asarray([[p.x,p.y] for p in h.image_points],dtype=float)
    world=np.asarray([[p.x,p.y] for p in h.world_points] if h.world_points is not None else pool_corners(h),dtype=float)
    def normalize(points):
        center=points.mean(axis=0);distance=np.linalg.norm(points-center,axis=1).mean()
        if not np.isfinite(distance) or distance<=1e-12:raise ValueError('서로 다른 기준점이 필요합니다.')
        scale=np.sqrt(2)/distance
        matrix=np.array([[scale,0,-scale*center[0]],[0,scale,-scale*center[1]],[0,0,1]])
        return (points-center)*scale,matrix
    p,tp=normalize(pixels);q,tq=normalize(world)
    x,y=p[:,0],p[:,1];u,v=q[:,0],q[:,1]
    a=np.zeros((2*len(p),9));a[0::2,:3]=np.c_[-x,-y,-np.ones(len(p))]
    a[1::2,3:6]=np.c_[-x,-y,-np.ones(len(p))]
    a[0::2,6:]=np.c_[x*u,y*u,u];a[1::2,6:]=np.c_[x*v,y*v,v]
    _,singular,vt=np.linalg.svd(a,full_matrices=len(p)==4)
    if np.count_nonzero(singular>singular[0]*1e-12)<8:raise ValueError('기준점 배치로 호모그래피를 계산할 수 없습니다.')
    matrix=np.linalg.inv(tq)@vt[-1].reshape(3,3)@tp
    matrix/=np.max(np.abs(matrix))
    if not np.isfinite(matrix).all() or np.linalg.matrix_rank(matrix)!=3:raise ValueError('유효한 좌표 변환을 계산할 수 없습니다.')
    projected=np.c_[pixels,np.ones(len(pixels))]@matrix.T
    z=projected[:,2]
    if np.any(np.abs(z)<1e-12) or not (np.all(z>0) or np.all(z<0)):raise ValueError('기준점 대응이 뒤집혔습니다.')
    errors=np.linalg.norm(projected[:,:2]/z[:,None]-world,axis=1)
    return matrix,{'point_count':len(pixels),'point_errors_m':errors.tolist(),
        'rms_error_m':float(np.sqrt(np.mean(errors**2))),'max_error_m':float(errors.max())}


def homography_report(h):
    return fit_homography(h)[1] if h.enabled else None


class Aruco(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    enabled: StrictBool = False
    dictionary: Literal['DICT_4X4_50','DICT_5X5_100','DICT_6X6_250'] = 'DICT_4X4_50'
    marker_id: int = Field(default=0,ge=0,strict=True)
    marker_size_m: float = Field(default=.05,gt=0,le=5)
    heading_offset_deg: float | None = Field(default=None,ge=-180,le=180)
    heading_measured: StrictBool = False

    @model_validator(mode='after')
    def marker(self):
        if self.marker_id>=DICTIONARY_COUNTS[self.dictionary]:raise ValueError('선택한 사전에 없는 마커 ID입니다.')
        if self.heading_measured and self.heading_offset_deg is None:raise ValueError('측정한 헤딩 오프셋을 입력하세요.')
        return self


class CameraConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(default=0,ge=0)
    homography: Homography = Field(default_factory=Homography)
    aruco: Aruco = Field(default_factory=Aruco)


def calibration_dict(homography, image_size):
    """Normalize full-image percentages to the actual resized upload dimensions."""
    h=homography if isinstance(homography,Homography) else Homography.model_validate(homography)
    if not h.enabled:return {}
    w,hei=image_size
    oldw,oldh=h.image_size
    if abs((w/hei)/(oldw/oldh)-1)>.01:raise ValueError('IMAGE_ASPECT_MISMATCH')
    points=[[p.x*w/100,p.y*hei/100] for p in h.image_points]
    world=[[p.x,p.y] for p in h.world_points] if h.world_points is not None else pool_corners(h)
    return {'image_points':points,'world_points':world,'image_size':[w,hei],'world_bounds':[0,0,h.pool_width_m,h.pool_height_m],
        'frame_id':h.frame_id,'calibration_id':h.calibration_id or 'web-calibration',
        'unit':'m','origin':'physical lower-left corner','x_axis':'physical right','y_axis':'physical up',
        'bbox_anchor':[.5,1.0],'max_error_m':.05,'roi':points[:4],'exclude_outside_roi':True}
