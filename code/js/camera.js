/* MJPEG over authenticated fetch. Passwords and tokens are never persisted. */
(function(){
  const el = id => document.getElementById(id);
  const server = el('cameraServer');
  server.value = localStorage.getItem('dg_camera_server') || `${location.protocol === 'https:' ? 'https:' : 'http:'}//${location.hostname || 'localhost'}:8000`;
  el('cameraUsername').value = (dgGetSession() || {}).id || '';
  let controller = null, frameUrl = null;

  function clearVideo(){
    el('cameraFeed').hidden = true;
    el('cameraFeed').removeAttribute('src');
    if(frameUrl) URL.revokeObjectURL(frameUrl);
    frameUrl = null;
    el('videoPanel').classList.remove('camera-connected');
    el('cameraBadge').textContent = '시뮬레이션';
  }
  function disconnect(){
    if(controller) controller.abort();
    controller = null;
    clearVideo();
    el('cameraConnectBtn').disabled = false;
    el('cameraDisconnectBtn').disabled = true;
    el('videoReadout').textContent = '웹캠 연결 대기';
    el('cameraStatus').textContent = '웹캠 연결이 해제되었습니다.';
  }

  async function checked(response){
    if(!response.ok){
      const error = await response.json().catch(() => ({}));
      throw new Error(typeof error.detail === 'string' ? error.detail : `카메라 요청 실패 (${response.status})`);
    }
    return response;
  }

  el('cameraForm').addEventListener('submit', async event => {
    event.preventDefault();
    disconnect();
    const current = new AbortController();
    controller = current;
    el('cameraConnectBtn').disabled = true;
    el('cameraDisconnectBtn').disabled = false;
    el('cameraStatus').textContent = '웹캠 연결 중…';
    let watchdog;
    const refreshTimeout = () => {
      clearTimeout(watchdog);
      watchdog = setTimeout(() => current.abort(new Error('영상 수신 시간이 초과되었습니다. 다시 연결하세요.')), 15000);
    };
    refreshTimeout();
    try{
      const base = new URL(server.value);
      if(!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash){
        throw new Error('올바른 HTTP 또는 HTTPS 백엔드 주소를 입력하세요.');
      }
      const root = base.href.replace(/\/$/, '');
      const site = new URLSearchParams(location.search).get('site');
      if(!site) throw new Error('사이트를 먼저 선택하세요.');
      const body = new URLSearchParams({username:el('cameraUsername').value.trim(), password:el('cameraPassword').value});
      const login = await checked(await fetch(`${root}/auth/login`, {method:'POST', body, signal:current.signal}));
      const {access_token:token} = await login.json();
      el('cameraPassword').value = '';
      const response = await checked(await fetch(`${root}/sites/${encodeURIComponent(site)}/camera/stream`, {
        headers:{Authorization:`Bearer ${token}`}, signal:current.signal, cache:'no-store',
      }));
      if(!response.headers.get('content-type')?.includes('multipart/x-mixed-replace')) throw new Error('MJPEG 응답이 아닙니다.');
      localStorage.setItem('dg_camera_server', root);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = new Uint8Array(0);
      try{
        while(true){
          const {done, value} = await reader.read();
          if(done) throw new Error('영상 연결이 종료되었습니다. 다시 연결하세요.');
          const joined = new Uint8Array(buffer.length + value.length);
          joined.set(buffer); joined.set(value, buffer.length); buffer = joined;
          if(buffer.length > 8 * 1024 * 1024) throw new Error('영상 프레임 크기가 너무 큽니다.');
          while(true){
            let end = -1;
            for(let i=0; i<buffer.length-3; i++){
              if(buffer[i]===13 && buffer[i+1]===10 && buffer[i+2]===13 && buffer[i+3]===10){end=i;break;}
            }
            if(end<0) break;
            const header = decoder.decode(buffer.subarray(0,end));
            const match = /Content-Length:\s*(\d+)/i.exec(header);
            if(!match) throw new Error('MJPEG 프레임 헤더가 올바르지 않습니다.');
            const length = Number(match[1]), start = end+4;
            if(length<=0 || length>8*1024*1024) throw new Error('MJPEG 프레임 크기가 올바르지 않습니다.');
            if(buffer.length<start+length+2) break;
            const nextUrl = URL.createObjectURL(new Blob([buffer.slice(start,start+length)], {type:'image/jpeg'}));
            el('cameraFeed').src = nextUrl;
            if(frameUrl) URL.revokeObjectURL(frameUrl);
            frameUrl = nextUrl;
            buffer = buffer.slice(start+length+2);
            el('cameraFeed').hidden = false;
            el('videoPanel').classList.add('camera-connected');
            el('cameraBadge').textContent = 'LIVE';
            el('videoReadout').textContent = 'MJPEG · 실시간 영상';
            el('cameraStatus').textContent = '웹캠 연결됨 · 시뮬레이션 일시정지와 별도로 영상은 계속 수신합니다.';
            refreshTimeout();
          }
        }
      }finally{
        await reader.cancel().catch(() => {});
        reader.releaseLock();
      }
    }catch(error){
      if(controller === current){
        const message = current.signal.aborted ? current.signal.reason?.message : error.message;
        disconnect();
        el('cameraStatus').textContent = message || '웹캠 연결에 실패했습니다. 서버 주소와 연결 상태를 확인하세요.';
        el('videoReadout').textContent = '웹캠 연결 끊김';
      }
    }finally{
      clearTimeout(watchdog);
    }
  });
  el('cameraDisconnectBtn').addEventListener('click', disconnect);
  el('logoutBtn').addEventListener('click', disconnect);
  window.addEventListener('pagehide', disconnect);
})();
