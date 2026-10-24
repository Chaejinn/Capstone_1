/* Browser camera -> authenticated local backend -> Modal. No API keys in browser. */
(function(){
  const el = id => document.getElementById(id);
  const video = el('localCameraFeed'), overlay = el('cameraOverlay');
  const capture = document.createElement('canvas');
  let controller = null, stream = null, timer = null, generation = 0, frameId = 0;
  const labels = {SWIMMING:'수영', DROWNING:'익수 의심', UNCLEAR:'판단 보류'};
  function clearBoxes(){
    overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height);
  }
  function disconnect(){
    generation++;
    clearTimeout(timer);
    if(controller) controller.abort();
    controller = null;
    if(stream) stream.getTracks().forEach(track => {track.onended = null; track.stop();});
    stream = null;
    video.pause(); video.srcObject = null; video.hidden = true;
    clearBoxes(); overlay.hidden = true;
    window.dgCameraLive = false;
    updateSimControls();
    el('videoPanel').classList.remove('camera-connected');
    el('cameraConnectBtn').disabled = false;
    el('cameraDisconnectBtn').disabled = true;
    el('cameraBadge').textContent = '시뮬레이션';
    el('videoReadout').textContent = '카메라 연결 대기';
    el('cameraStatus').textContent = '카메라 연결이 해제되었습니다.';
  }
  function draw(data){
    clearBoxes();
    const context = overlay.getContext('2d');
    const size = data.image_size;
    if(!Array.isArray(size) || size.length !== 2 || !(size[0]>0 && size[1]>0)) throw new Error('AI 응답의 이미지 크기가 올바르지 않습니다.');
    overlay.width = size[0]; overlay.height = size[1];
    const detections = Array.isArray(data.detections) ? data.detections : [];
    context.lineWidth = 3; context.font = '18px sans-serif';
    for(const item of detections){
      if(!Array.isArray(item.bbox) || item.bbox.length !== 4 || !item.bbox.every(Number.isFinite)) continue;
      const [x1,y1,x2,y2] = item.bbox;
      const state = item.water_state || 'UNCLEAR';
      context.strokeStyle = state === 'DROWNING' ? '#ff5050' : state === 'SWIMMING' ? '#32e58b' : '#ffd166';
      context.fillStyle = context.strokeStyle;
      context.strokeRect(x1,y1,x2-x1,y2-y1);
      context.fillText(`${labels[state] || '판단 보류'} · 탐지 ${Math.round((item.confidence || 0)*100)}%`, Math.max(0,x1), Math.max(22,y1-8));
    }
    el('cameraBadge').textContent = 'AI LIVE';
    el('videoReadout').textContent = `Modal 분석 · 탐지 ${detections.length}개 · ${Math.round(data.inference_ms || 0)}ms`;
    el('cameraStatus').textContent = detections.length ? 'AI 분석 중 · 박스는 최근 분석 프레임의 결과입니다.' : 'AI 분석 중 · 탐지된 대상 없음';
  }
  async function analyze(run){
    if(run !== generation || !stream) return;
    const request = new AbortController(); controller = request;
    const timeout = setTimeout(() => request.abort(), 60000);
    try{
      if(!video.videoWidth || !video.videoHeight) throw new Error('카메라 영상을 준비 중입니다.');
      capture.width = Math.min(960,video.videoWidth);
      capture.height = Math.round(video.videoHeight*capture.width/video.videoWidth);
      capture.getContext('2d').drawImage(video,0,0,capture.width,capture.height);
      const blob = await new Promise(resolve => capture.toBlob(resolve,'image/jpeg',0.8));
      if(run !== generation) return;
      if(!blob) throw new Error('카메라 이미지를 생성하지 못했습니다.');
      const body = new FormData(); body.append('image',blob,'frame.jpg'); body.append('frame_id',String(++frameId));
      const result = await dgApi('/camera/analyze',{method:'POST',body,signal:request.signal});
      if(run !== generation) return;
      draw(result);
    }catch(error){
      if(run !== generation) return;
      clearBoxes();
      el('cameraBadge').textContent = 'AI 연결 대기';
      el('cameraStatus').textContent = request.signal.aborted ? 'AI 응답 시간이 초과되었습니다. 다시 시도합니다.' : `AI 분석 실패: ${error.message}`;
      el('videoReadout').textContent = '카메라 미리보기 · AI 결과 없음';
      if(!dgGetSession()){disconnect();el('cameraStatus').textContent='세션이 만료되었습니다. 다시 로그인하세요.';return;}
    }finally{
      clearTimeout(timeout);
      if(run === generation && stream) timer = setTimeout(() => analyze(run),1500);
    }
  }
  el('cameraForm').addEventListener('submit',async event => {
    event.preventDefault(); disconnect(); const run = generation;
    el('cameraConnectBtn').disabled = true; el('cameraDisconnectBtn').disabled = false;
    el('cameraStatus').textContent = '카메라 권한 확인 중…';
    try{
      if(!navigator.mediaDevices?.getUserMedia) throw new Error('HTTPS 또는 localhost에서 카메라를 사용할 수 있습니다.');
      const next = await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720}},audio:false});
      if(run !== generation){next.getTracks().forEach(track=>track.stop());return;}
      stream = next; video.srcObject = stream; await video.play();
      if(run !== generation) return;
      stream.getVideoTracks().forEach(track => {track.onended=()=>{if(run===generation){disconnect();el('cameraStatus').textContent='카메라 연결이 종료되었습니다.';}};});
      pauseSim(); window.dgCameraLive = true; updateSimControls();
      video.hidden = false; overlay.hidden = false;
      el('videoPanel').classList.add('camera-connected');
      el('cameraBadge').textContent = 'AI 분석 대기';
      el('cameraStatus').textContent = '카메라 연결됨 · 첫 AI 분석 중…';
      void analyze(run);
    }catch(error){
      if(run !== generation) return;
      disconnect();
      el('cameraStatus').textContent = error.name === 'NotAllowedError' ? '브라우저와 macOS에서 카메라 접근을 허용하세요.' : error.name === 'NotFoundError' ? '사용 가능한 카메라가 없습니다.' : error.message;
    }
  });
  el('cameraDisconnectBtn').addEventListener('click',disconnect);
  el('logoutBtn').addEventListener('click',disconnect);
  window.addEventListener('pagehide',disconnect);
})();
