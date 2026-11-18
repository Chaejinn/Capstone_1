/* Local, display-only board marker and distance overlay. Never emits control commands. */
(() => {
  const el=id=>document.getElementById(id),video=el('localCameraFeed'),canvas=el('liveMarkerOverlay'),panel=el('videoPanel');
  const readout=el('liveMarkerReadout'),status=el('liveMarkerStatus'),context=canvas.getContext('2d');
  const capture=document.createElement('canvas'),pixels=capture.getContext('2d',{willReadFrequently:true});
  const workerUrl=new URL('live-aruco-worker.js?v=1',document.currentScript.src);
  let stream=null,configuration=null,worker=null,token=0,busy=false,raf=null,lastSent=-Infinity;
  let expiry=null,targets=null,captureTimes=[],lastVideoTime=-Infinity;
  function distance(value){
    window.dgLiveDistance=value;
    if(window.dgCameraLive){
      el('statDistLabel').textContent='익수자까지 거리';
      el('statDist').textContent=value?value.distance_m.toFixed(2)+' m':'— m';
      el('statDist').title=value?`익수자 좌표 ${value.age.toFixed(1)}초 전 · 표시용 계산`:'유효한 보드·익수자 좌표 대기';
    }
  }
  function clear(message){
    clearTimeout(expiry);expiry=null;context.clearRect(0,0,canvas.width,canvas.height);canvas.hidden=true;distance(null);
    readout.hidden=!stream||!configuration?.aruco?.enabled;
    readout.textContent=message||'보드 마커 검출 대기';
  }
  function fit(){
    if(!video.videoWidth||!video.videoHeight||!panel.clientWidth||!panel.clientHeight)return;
    const scale=Math.min(panel.clientWidth/video.videoWidth,panel.clientHeight/video.videoHeight);
    const width=video.videoWidth*scale,height=video.videoHeight*scale;
    Object.assign(canvas.style,{inset:'auto',left:`${(panel.clientWidth-width)/2}px`,top:`${(panel.clientHeight-height)/2}px`,width:`${width}px`,height:`${height}px`});
  }
  function terminate(){worker?.terminate();worker=null;busy=false;clearTimeout(expiry);}
  function startWorker(){
    terminate();token++;captureTimes=[];
    if(!stream||!configuration?.aruco?.enabled)return;
    if(typeof Worker==='undefined'){status.textContent='브라우저가 실시간 ArUco 검출을 지원하지 않습니다.';return;}
    try{worker=new Worker(workerUrl);}catch(error){status.textContent='실시간 ArUco 검출기를 시작할 수 없습니다.';return;}
    worker.onerror=()=>{terminate();clear('실시간 마커 검출 초기화 실패');status.textContent='실시간 마커 검출 초기화 실패 · 카메라를 다시 연결하세요.';};
    worker.onmessage=event=>{
      const result=event.data;
      if(result.token!==token||!stream)return;
      busy=false;
      if(document.hidden){clear();return;}
      if(result.error){clear(result.error);return;}
      const age=performance.now()-result.capturedAt;
      if(age<0||age>200){clear('실시간 마커 처리 지연 · 새 영상 대기');return;}
      const marker=result.marker;
      if(!marker?.detected){clear(marker?.coordinate_status==='AMBIGUOUS_MARKER'?'같은 ID의 마커가 여러 개입니다.':'보드 마커 검출 대기');return;}
      fit();canvas.width=video.videoWidth;canvas.height=video.videoHeight;
      const sx=canvas.width/result.width,sy=canvas.height/result.height;
      const observation={...marker,corners_px:marker.corners_px.map(p=>[p[0]*sx,p[1]*sy]),center_px:[marker.center_px[0]*sx,marker.center_px[1]*sy]};
      if(marker.board_front_px)observation.board_front_px=[marker.board_front_px[0]*sx,marker.board_front_px[1]*sy];
      context.clearRect(0,0,canvas.width,canvas.height);window.dgDrawMarker?.(context,observation);
      captureTimes.push(result.capturedAt);
      while(captureTimes.length>1&&result.capturedAt-captureTimes[0]>1000)captureTimes.shift();
      const elapsed=result.capturedAt-captureTimes[0];
      const fps=elapsed>0?(captureTimes.length-1)*1000/elapsed:null;
      const distances=DgLiveArucoMath.distances(marker,targets,configuration,Date.now());
      distance(distances[0]||null);
      let text=`보드 ID ${marker.marker_id}${fps?` · 검출 ${fps.toFixed(1)} fps`:''}`;
      if(marker.coordinate_valid)text+=` · X ${marker.x_m.toFixed(2)} m · Y ${marker.y_m.toFixed(2)} m`;
      for(const item of distances.slice(0,3)){
        const target=[item.target_percent[0]/100*canvas.width,item.target_percent[1]/100*canvas.height];
        context.strokeStyle='#42e8ef';context.lineWidth=2;context.setLineDash([8,5]);context.beginPath();
        context.moveTo(...observation.center_px);context.lineTo(...target);context.stroke();context.setLineDash([]);
        text+=`\n익수자 ID ${item.generation}-${item.track_id}까지 ${item.distance_m.toFixed(2)} m · 익수자 좌표 ${item.age.toFixed(1)}초 전`;
      }
      if(!distances.length)text+=marker.coordinate_valid?'\n익수 확정 대상의 유효한 좌표 대기':'\n거리 계산 대기 · 호모그래피 보정·영상 비율을 확인하세요.';
      readout.hidden=false;readout.textContent=text;canvas.hidden=false;
      status.textContent='ArUco는 이 PC에서 실시간 검출 중 · 익수자 좌표는 최근 AI 분석 시각 기준';
      clearTimeout(expiry);expiry=setTimeout(()=>clear('보드 위치 관측 만료 · 새 영상 대기'),Math.max(0,200-age));
    };
  }
  function loop(now){
    raf=null;if(!stream)return;
    raf=requestAnimationFrame(loop);
    if(document.hidden||!configuration?.aruco?.enabled||!worker||busy||now-lastSent<100||video.readyState<2||!video.videoWidth)return;
    if(!Number.isFinite(video.currentTime)||video.currentTime===lastVideoTime)return;
    try{
      capture.width=Math.min(640,video.videoWidth);capture.height=Math.round(video.videoHeight*capture.width/video.videoWidth);
      const capturedAt=performance.now();pixels.drawImage(video,0,0,capture.width,capture.height);
      const image=pixels.getImageData(0,0,capture.width,capture.height);busy=true;lastSent=now;lastVideoTime=video.currentTime;
      worker.postMessage({token,capturedAt,width:capture.width,height:capture.height,pixels:image.data.buffer,configuration},[image.data.buffer]);
    }catch(error){busy=false;clear('현재 카메라 프레임을 읽지 못했습니다.');}
  }
  window.dgSetLiveArucoConfiguration=data=>{
    configuration=JSON.parse(JSON.stringify(data));targets=null;clear();startWorker();
    if(!data.aruco.enabled)status.textContent='실시간 ArUco 표시 꺼짐 · 설정에서 ArUco 사용을 켜고 저장하세요.';
  };
  window.dgSyncLiveAruco=value=>{
    stream=value;targets=null;token++;lastSent=-Infinity;lastVideoTime=-Infinity;clear();startWorker();
    if(raf!==null)cancelAnimationFrame(raf);raf=stream?requestAnimationFrame(loop):null;
    if(!stream){readout.hidden=true;status.textContent='';}
  };
  window.dgUpdateLiveTargets=packet=>{targets=packet;};
  video.addEventListener('loadedmetadata',fit);video.addEventListener('resize',()=>{clear();fit();});
  new ResizeObserver(fit).observe(panel);window.addEventListener('resize',fit);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)clear();});
  window.addEventListener('pagehide',()=>{stream=null;terminate();if(raf!==null)cancelAnimationFrame(raf);});
})();
