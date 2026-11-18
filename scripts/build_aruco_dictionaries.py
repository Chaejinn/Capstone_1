"""Export canonical OpenCV marker bits for the vendored browser detector."""
from pathlib import Path
import json
import cv2

root=Path(__file__).resolve().parents[1]
result={}
for name in ('DICT_4X4_50','DICT_5X5_100','DICT_6X6_250'):
    dictionary=cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco,name))
    bits=dictionary.markerSize
    codes=[]
    for marker_id in range(len(dictionary.bytesList)):
        marker=cv2.aruco.generateImageMarker(dictionary,marker_id,bits+2)
        binary=''.join('1' if pixel else '0' for pixel in marker[1:-1,1:-1].ravel())
        codes.append(format(int(binary,2),'x'))
    # tau=1 means exact bit matches. A wrong ID must never be used for board display.
    result[name]={'nBits':bits*bits,'tau':1,'codeList':codes}
(root/'code/js/vendor/js-aruco2/opencv-dictionaries.js').write_text(
    '// Generated from OpenCV canonical marker bit matrices; regenerate with scripts/build_aruco_dictionaries.py.\n'+
    'Object.assign(AR.DICTIONARIES,'+json.dumps(result,separators=(',',':'))+');\n')
print('Exported',sum(len(d['codeList']) for d in result.values()),'OpenCV marker codes')
