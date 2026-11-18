/* One frame at a time; all detection stays on this device. */
importScripts('vendor/js-aruco2/cv.js','vendor/js-aruco2/aruco.js','vendor/js-aruco2/opencv-dictionaries.js','live-aruco-math.js');
let detector=null,dictionary=null;
self.onmessage=event=>{
  const frame=event.data;
  try{
    if(dictionary!==frame.configuration.aruco.dictionary){
      dictionary=frame.configuration.aruco.dictionary;
      detector=new AR.Detector({dictionaryName:dictionary,maxHammingDistance:1});
    }
    const started=performance.now();
    const markers=detector.detect({width:frame.width,height:frame.height,data:new Uint8ClampedArray(frame.pixels)});
    const marker=DgLiveArucoMath.locate(markers,frame.configuration,frame.width,frame.height);
    self.postMessage({token:frame.token,capturedAt:frame.capturedAt,width:frame.width,height:frame.height,
      marker,processingMs:performance.now()-started});
  }catch(error){self.postMessage({token:frame.token,capturedAt:frame.capturedAt,error:'브라우저 ArUco 검출 실패'});}
};
