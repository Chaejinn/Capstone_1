/* Read external AI observations. This viewer never counts evidence or issues commands. */
(() => {
  const el = id => document.getElementById(id);
  const site = new URLSearchParams(location.search).get('site');
  let generation = 0, timer, poseExpiryTimer, request, running = false;
  const canvas = el('edgePreview');
  const labels = {SWIMMING:'수영', DROWNING:'익수 의심', UNCLEAR:'판단 보류'};
  function stop(){
    ++generation; running = false; clearTimeout(timer); clearTimeout(poseExpiryTimer); request?.abort();
    canvas.hidden = true; el('edgeDetails').textContent = ''; el('edgePoseDetails').textContent = '';
    el('edgeConnectBtn').disabled = false; el('edgeDisconnectBtn').disabled = true;
    el('edgeCameraId').disabled = false; el('edgeSource').disabled = false;
    el('cameraConnectBtn').disabled = false;
    window.dgCameraLive = false; updateSimControls();
    el('edgeStatus').textContent = '로컬 AI 결과 수신 종료';
  }
  async function poll(run, source, camera){
    if(run !== generation || !running) return;
    request = new AbortController();
    const timeout = setTimeout(() => request.abort(), 10000);
    try{
      const query = '?site_id=' + encodeURIComponent(site);
      let packet, board;
      if(source === 'hybrid'){
        packet = await dgApi('/vision/edge/' + encodeURIComponent(camera) + query, {signal:request.signal});
        board = packet.pose;
      }else{
        const suffix = query + '&camera_id=' + encodeURIComponent(camera);
        const [analysisResult, poseResult] = await Promise.allSettled([
          dgApi('/edge/latest' + suffix, {signal:request.signal}),
          dgApi('/edge/pose' + suffix, {signal:request.signal})
        ]);
        if(analysisResult.status === 'rejected' && poseResult.status === 'rejected') throw analysisResult.reason;
        packet = analysisResult.status === 'fulfilled' ? analysisResult.value : {observation:null};
        board = poseResult.status === 'fulfilled' ? poseResult.value.pose : null;
      }
      if(run !== generation) return;
      clearTimeout(poseExpiryTimer);
      const poseAge = board?.timestamp ? (Date.now()-Date.parse(board.timestamp))/1000 : NaN;
      const validPose = board?.tracking_valid === true && board.unit === 'm'
        && Number.isFinite(poseAge) && poseAge >= 0 && poseAge <= 0.25
        && [board.x,board.y,board.heading].every(Number.isFinite);
      el('edgePoseDetails').textContent = validPose
        ? `보드 관측 · X ${board.x.toFixed(3)} m · Y ${board.y.toFixed(3)} m · 방향 ${board.heading.toFixed(1)}° · 출동 명령 미발행`
        : board ? `보드 위치 사용 불가 · ${board.status || '관측 만료'} · 출동 명령 미발행` : '보드 위치 관측 대기';
      if(validPose) poseExpiryTimer = setTimeout(() => {
        if(run === generation && running) el('edgePoseDetails').textContent = '보드 위치 사용 불가 · 관측 만료 · 출동 명령 미발행';
      }, Math.max(0,250-poseAge*1000));
      const analysis = source === 'hybrid' ? packet.analysis : packet.observation;
      const time = analysis?.captured_at ? Date.parse(analysis.captured_at) : NaN;
      const age = (Date.now()-time)/1000;
      const fresh = Number.isFinite(age) && age >= -0.5 && age <= 30 && !packet.expired;
      canvas.hidden = true;
      el('edgeStatus').textContent = fresh ? '로컬 AI 결과 수신 중 · 출동 명령 미발행'
        : '분석 결과가 없거나 촬영 시각이 오래되었습니다.';
      const score = Number.isFinite(analysis?.drowning_score) ? (analysis.drowning_score*100).toFixed(1)+'%' : '미제공';
      el('edgeDetails').textContent = analysis
        ? `ID ${analysis.track_id ?? '미제공'} · ${labels[analysis.state] || '판단 보류'} · 익수 점수 ${score} · ${Number.isFinite(age) ? Math.max(0,age).toFixed(1)+'초 전' : '촬영 시각 미제공'} · 웹의 15프레임 검증 미실시`
        : 'PC의 중계 설정과 분석 실행 상태를 확인해 주세요.';
      if(source === 'hybrid' && fresh && Number.isInteger(analysis.frame_id)){
        const frame = await dgApi('/vision/edge/' + encodeURIComponent(camera) + '/frames/' + analysis.frame_id
          + query + '&session_id=' + encodeURIComponent(packet.session_id), {signal:request.signal});
        if(run !== generation) return;
        if(frame.frame_id !== analysis.frame_id || frame.session_id !== packet.session_id
          || frame.captured_at !== analysis.captured_at || typeof frame.image_base64 !== 'string'
          || frame.image_base64.length > 1400000) throw new Error('분석 프레임 정보가 일치하지 않습니다.');
        const image = new Image();
        image.src = 'data:image/jpeg;base64,' + frame.image_base64;
        await image.decode();
        if(run !== generation) return;
        if((Date.now()-time)/1000 > 30) throw new Error('분석 프레임이 만료되었습니다.');
        canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
        const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0);
        if(Array.isArray(analysis.bbox) && analysis.bbox.length === 4 && analysis.bbox.every(Number.isFinite)){
          const [x1,y1,x2,y2] = analysis.bbox;
          if(0 <= x1 && x1 < x2 && x2 <= canvas.width && 0 <= y1 && y1 < y2 && y2 <= canvas.height){
            ctx.strokeStyle = analysis.state === 'DROWNING' ? '#ff5050' : '#32e58b'; ctx.lineWidth = 3;
            ctx.strokeRect(x1,y1,x2-x1,y2-y1);
          }
        }
        canvas.hidden = false;
      }
    }catch(error){
      if(run !== generation) return;
      clearTimeout(poseExpiryTimer);
      canvas.hidden = true; el('edgeDetails').textContent = ''; el('edgePoseDetails').textContent = '';
      el('edgeStatus').textContent = '로컬 AI 수신 실패: ' + error.message;
      if(!dgGetSession()){stop(); el('edgeStatus').textContent = '세션이 만료되었습니다. 다시 로그인하세요.'; return;}
    }finally{
      clearTimeout(timeout);
      if(run === generation && running) timer = setTimeout(() => poll(run,source,camera), 1000);
    }
  }
  el('edgeConnectBtn').addEventListener('click', () => {
    const camera = el('edgeCameraId').value.trim(), source = el('edgeSource').value;
    if(!site || !/^[A-Za-z0-9_-]{1,80}$/.test(camera)){
      el('edgeStatus').textContent = '사이트를 선택하고 올바른 카메라 ID를 입력해 주세요.'; return;
    }
    el('cameraDisconnectBtn').click(); pauseSim(); stop();
    running = true; window.dgCameraLive = true; updateSimControls();
    el('cameraConnectBtn').disabled = true;
    el('edgeConnectBtn').disabled = true; el('edgeDisconnectBtn').disabled = false;
    el('edgeCameraId').disabled = true; el('edgeSource').disabled = true;
    el('edgeStatus').textContent = '로컬 AI 결과 연결 중…';
    void poll(generation,source,camera);
  });
  el('edgeDisconnectBtn').addEventListener('click',stop);
  el('logoutBtn').addEventListener('click',() => {if(running) stop();});
  window.addEventListener('pagehide',() => {if(running) stop();});
})();
