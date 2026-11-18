from pathlib import Path
import cv2,numpy as np,json,base64,sys,tempfile
fixtures=[]
for name in ('DICT_4X4_50','DICT_5X5_100','DICT_6X6_250'):
 d=cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco,name));detector=cv2.aruco.ArucoDetector(d,cv2.aruco.DetectorParameters())
 for marker_id in (0,len(d.bytesList)-1):
  marker=cv2.aruco.generateImageMarker(d,marker_id,96)
  for rotation in range(4):
   grey=np.full((240,320),255,np.uint8);grey[72:168,112:208]=np.rot90(marker,rotation)
   corners,ids,_=detector.detectMarkers(grey);assert ids is not None
   image=cv2.cvtColor(grey,cv2.COLOR_GRAY2RGBA)
   fixtures.append({'dictionary':name,'id':marker_id,'rotation':rotation,'width':320,'height':240,'rgba':base64.b64encode(image.tobytes()).decode(),'expected_corners':corners[0].reshape(4,2).tolist()})
Path(sys.argv[1] if len(sys.argv)>1 else Path(tempfile.gettempdir())/'dg-live-marker-fixtures.json').write_text(json.dumps(fixtures))
print('Generated',len(fixtures),'canonical OpenCV images')
