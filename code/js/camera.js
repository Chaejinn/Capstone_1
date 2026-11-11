/* Browser camera -> authenticated backend -> AI API. No API keys in browser. */
(function(){
  const el = id => document.getElementById(id);
  const video = el('localCameraFeed'), overlay = el('cameraOverlay');
  const capture = document.createElement('canvas');
  let controller = null, stream = null, timer = null, generation = 0, frameId = 0;
  let trackingId = null, pendingFrame = null, lastResult = 0;
  let resultClock = null, resultCapturedAt = null, resultInferenceMs = 0;
  function updateResultTime(){
    if(!resultCapturedAt) return;
    const age = Math.max(0,(Date.now()-resultCapturedAt.getTime())/1000);
    el('aiResultInfo').textContent = `촬영 ${resultCapturedAt.toLocaleTimeString('ko-KR',{hour12:false})} · ${age.toFixed(1)}초 전 · 분석 ${(resultInferenceMs/1000).toFixed(1)}초`;
  }
  const siteId = new URLSearchParams(window.location.search).get('site');
  function path(suffix){
    return '/vision/streams' + suffix + '?site_id=' + encodeURIComponent(siteId || '');
  }
  function closeTracking(id){
    if(id) void dgApi(path('/' + id),{method:'DELETE'}).catch(()=>{});
  }
  const labels = {SWIMMING:'수영', DROWNING:'익수 의심', UNCLEAR:'판단 보류'};
  function clearBoxes(){
    overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height);
  }
  function disconnect(){
    generation++;
    closeTracking(trackingId); trackingId = null; pendingFrame = null; lastResult = 0;
    clearTimeout(timer);
    clearInterval(resultClock); resultClock = null; resultCapturedAt = null;
    el('aiResultPanel').hidden = true;
    el('aiResultPlaceholder').hidden = false;
    el('aiResultInfo').textContent = '분석 결과 대기';
    if(controller) controller.abort();
    controller = null;
    if(stream) stream.getTracks().forEach(track => {track.onended = null; track.stop();});
    stream = null;
    video.pause(); video.srcObject = null; video.hidden = true;
    window.dgSyncRoiCamera?.(null);
    window.dgSyncVisionCamera?.(null);
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
    // Draw boxes on the exact analyzed image, never on a later live frame.
    context.drawImage(capture,0,0,overlay.width,overlay.height);
    const detections = Array.isArray(data.detections) ? data.detections : [];
    context.lineWidth = 3; context.font = '18px sans-serif';
    for(const item of detections){
      if(!Array.isArray(item.bbox) || item.bbox.length !== 4 || !item.bbox.every(Number.isFinite)) continue;
      const [x1,y1,x2,y2] = item.bbox;
      const state = item.water_state || 'UNCLEAR';
      context.strokeStyle = state === 'DROWNING' ? '#ff5050' : state === 'SWIMMING' ? '#32e58b' : '#ffd166';
      context.fillStyle = context.strokeStyle;
      context.strokeRect(x1,y1,x2-x1,y2-y1);
      const score = Number.isFinite(item.drowning_score) ? (item.drowning_score*100).toFixed(1)+'%' : '미제공';
      context.fillText(`익수 점수 ${score} · 연속 ${item.consecutive_frames || 0}/${item.required_frames || 15}`, Math.max(0,x1), Math.min(size[1]-8,Math.max(44,y1+24)));
      context.fillText(`${item.track_id == null ? 'ID 대기' : 'ID ' + (item.track_generation ?? data.track_generation ?? 0) + '-' + item.track_id} · ${labels[state] || '판단 보류'} · 탐지 ${Math.round((item.confidence || 0)*100)}%`, Math.max(0,x1), Math.max(22,y1-8));
      if(item.coordinate_valid && Number.isFinite(item.target_x_m) && Number.isFinite(item.target_y_m)){
        context.fillText(`X ${item.target_x_m.toFixed(3)} m · Y ${item.target_y_m.toFixed(3)} m`,Math.max(0,x1),Math.min(size[1]-8,y1+46));
      }
    }
    window.dgDrawMarker?.(context,data.marker_observation);
    el('aiResultPanel').hidden = false;
    el('aiResultPlaceholder').hidden = true;
    resultCapturedAt = new Date(data.captured_at || pendingFrame.capturedAt);
    resultInferenceMs = data.inference_ms || 0;
    updateResultTime();
    el('cameraBadge').textContent = 'CAM LIVE';
    el('videoReadout').textContent = '실시간 카메라 · AI 결과는 오른쪽에 표시됩니다.';
    el('cameraStatus').textContent = detections.some(item=>item.confirmed) ?
      (detections.some(item=>item.confirmed&&item.coordinate_valid)?'익수 확정 · 실제 출동 차단: 보트 브릿지 연결 필요':'익수 확정 · 실제 출동 차단: 좌표 보정·보트 브릿지 연결 필요') : detections.length ? '대상별 익수 점수 0.8 이상 · 15프레임 연속 확인 중' : data.marker_observation?.detected ? 'ArUco 마커 검출 · 익수 분석 대상 없음' : 'AI 분석 중 · 탐지된 대상 없음';
  }
  async function analyze(run){
    if(run !== generation || !stream) return;
    const request = new AbortController(); controller = request;
    const timeout = setTimeout(() => request.abort(), 60000);
    try{
      if(!siteId) throw new Error('사이트 선택 화면에서 사이트를 선택한 뒤 연결하세요.');
      if(!trackingId){
        const opened = await dgApi(path(''),{method:'POST',signal:request.signal});
        if(run !== generation){closeTracking(opened.stream_id);return;}
        trackingId = opened.stream_id;
        window.dgReportVisionApplied?.(opened.configuration_revision);
      }
      if(!pendingFrame){
        if(!video.videoWidth || !video.videoHeight) throw new Error('카메라 영상을 준비 중입니다.');
        capture.width = Math.min(960,video.videoWidth);
        capture.height = Math.round(video.videoHeight*capture.width/video.videoWidth);
        const capturedAt = new Date().toISOString();
        capture.getContext('2d').drawImage(video,0,0,capture.width,capture.height);
        const blob = await new Promise(resolve => capture.toBlob(resolve,'image/jpeg',0.8));
        if(run !== generation) return;
        if(!blob) throw new Error('카메라 이미지를 생성하지 못했습니다.');
        const current = ++frameId;
        const body = new FormData(); body.append('image',blob,'frame.jpg');
        body.append('frame_id',String(current)); body.append('captured_at',capturedAt);
        body.append('image_width',String(capture.width)); body.append('image_height',String(capture.height));
        pendingFrame = {id:current, started:Date.now(), capturedAt};
        await dgApi(path('/' + trackingId + '/frames'),{method:'POST',body,signal:request.signal});
        if(run !== generation) return;
      }
      const snapshot = await dgApi(path('/' + trackingId + '/results'),{signal:request.signal});
      if(run !== generation) return;
      if(snapshot.last_error) throw new Error('추적 서버 분석 실패: ' + snapshot.last_error);
      const result = snapshot.analysis;
      if(result && !result.expired && result.frame_id === pendingFrame.id && result.frame_id > lastResult){
        draw(result); overlay.hidden = false;
        lastResult = result.frame_id; pendingFrame = null;
      }else if(Date.now() - pendingFrame.started > 65000){
        throw new Error('추적 분석 시간이 초과되었습니다.');
      }else{
        el('cameraStatus').textContent = 'AI 추적 분석 중…';
      }
    }catch(error){
      if(run !== generation) return;
      closeTracking(trackingId); trackingId = null; pendingFrame = null;
      el('cameraBadge').textContent = 'CAM LIVE';
      el('cameraStatus').textContent = request.signal.aborted ? 'AI 응답 시간이 초과되었습니다. 다시 시도합니다.' : `AI 분석 실패: ${error.message}`;
      el('videoReadout').textContent = '실시간 카메라 · AI 연결 재시도 중';
      if(!dgGetSession()){disconnect();el('cameraStatus').textContent='세션이 만료되었습니다. 다시 로그인하세요.';return;}
    }finally{
      clearTimeout(timeout);
      if(run === generation && stream) timer = setTimeout(() => analyze(run),pendingFrame ? 700 : 1000);
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
      video.hidden = false; overlay.hidden = true;
      window.dgSyncRoiCamera?.(stream);
      window.dgSyncVisionCamera?.(stream);
      resultClock = setInterval(updateResultTime,1000);
      el('videoPanel').classList.add('camera-connected');
      el('cameraBadge').textContent = 'CAM LIVE';
      el('videoReadout').textContent = '실시간 카메라 · AI 결과는 오른쪽에 표시됩니다.';
      el('cameraStatus').textContent = '카메라 연결됨';
      void analyze(run);
    }catch(error){
      if(run !== generation) return;
      disconnect();
      el('cameraStatus').textContent = error.name === 'NotAllowedError' ? '브라우저와 macOS에서 카메라 접근을 허용하세요.' : error.name === 'NotFoundError' ? '사용 가능한 카메라가 없습니다.' : error.message;
    }
  });
  el('cameraDisconnectBtn').addEventListener('click',disconnect);
  window.dgRestartCameraTracking=()=>{
    if(!stream)return;
    generation++;clearTimeout(timer);controller?.abort();
    closeTracking(trackingId);trackingId=null;pendingFrame=null;lastResult=0;
    el('aiResultPanel').hidden=true;
    el('cameraStatus').textContent='설정 변경으로 추적 판정을 새로 시작합니다.';
    void analyze(generation);
  };
  el('logoutBtn').addEventListener('click',disconnect);
  window.addEventListener('pagehide',disconnect);
})();
