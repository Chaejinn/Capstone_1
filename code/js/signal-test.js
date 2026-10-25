/* Foreground history polling plus opt-in background Web Push. */
(() => {
  const el = id => document.getElementById(id);
  let controlCursor = 0;
  let cursor = 0, timer, running = false, generation = 0, count = 0, audio;
  const notify = message => { el('notice').textContent = message; };
  function showAuto(data) {
    el('autoStatus').textContent = !data.available ? '자동 테스트는 상시 실행 로컬 서버에서 지원합니다.' :
      data.error || (data.running ? `자동 발생 중 · ${data.generated}건 · 남은 시간 ${data.remaining_seconds}초` : '자동 발생 중지됨');
    el('autoStart').disabled = !data.available || data.running;
    el('autoStop').disabled = !data.running;
  }
  function beep() {
    if (!audio || audio.state !== 'running') return;
    const oscillator = audio.createOscillator(), gain = audio.createGain();
    oscillator.connect(gain); gain.connect(audio.destination);
    oscillator.frequency.value = 880; gain.gain.value = 0.15;
    oscillator.start(); oscillator.stop(audio.currentTime + 0.3);
  }
  async function poll(version) {
    if (!running || version !== generation) return;
    try {
      const data = await dgApi(`/test-signals?after_id=${cursor}`);
      if (!running || version !== generation) return;
      for (const signal of data.signals) {
        const item = document.createElement('li');
        item.textContent = `#${signal.id} · ${new Date(signal.created_at).toLocaleString('ko-KR')} · ${signal.source}: ${signal.message}`;
        el('signals').prepend(item);
        while (el('signals').children.length > 100) el('signals').lastChild.remove();
        count++;
      }
      cursor = data.cursor;
      el('count').textContent = count;
      if (data.signals.length) beep();
      const control = await dgApi(`/test-control?after_id=${controlCursor}`);
      if (!running || version !== generation) return;
      controlCursor = control.cursor;
      el('controlState').textContent = JSON.stringify(control.state, null, 2);
      if (control.packets.length) {
        el('controlPacket').textContent = JSON.stringify(control.packets[control.packets.length - 1], null, 2);
      }
      showAuto(await dgApi('/test-control/auto'));
      if (!running || version !== generation) return;
      el('status').textContent = `수신 대기 중 · 마지막 확인 ${new Date().toLocaleTimeString('ko-KR')}`;
    } catch (error) {
      if (version !== generation) return;
      el('status').textContent = `연결 오류: ${error.message} (자동 재시도)`;
      if (!dgGetSession()) { stop(); return; }
    }
    if (running && version === generation) timer = setTimeout(() => poll(version), 1000);
  }
  function stop() {
    running = false; generation++; clearTimeout(timer);
    el('loginPanel').hidden = false; el('receiver').hidden = true;
  }
  async function start() {
    const data = await dgApi('/test-signals?latest=true');
    const control = await dgApi('/test-control?latest=true');
    controlCursor = control.cursor;
    el('controlState').textContent = JSON.stringify(control.state, null, 2);
    el('controlPacket').textContent = '수신 대기 중';
    cursor = data.cursor; running = true;
    el('signals').replaceChildren(); count = 0; el('count').textContent = '0';
    el('loginPanel').hidden = true; el('receiver').hidden = false;
    notify('수신 시작 이후 도착한 신호를 표시합니다.');
    poll(++generation);
    try { showAuto(await dgApi('/test-control/auto/start', {method: 'POST'})); }
    catch (error) { el('autoStatus').textContent = error.message; }
    await refreshPushStatus();
  }
  el('loginForm').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      await dgLogin(el('username').value.trim(), el('password').value);
      el('password').value = ''; await start();
    } catch (error) { notify(error.message); }
  });
  el('sendForm').addEventListener('submit', async event => {
    event.preventDefault(); el('send').disabled = true;
    try {
      const signal = await dgApi('/test-signals', {method: 'POST', body: {source: 'web-test', message: el('message').value}});
      notify(`#${signal.id} 서버 저장 완료. 휴대폰 수신 기록을 확인하세요.`);
    } catch (error) { notify(error.message); }
    finally { el('send').disabled = false; }
  });
  document.querySelectorAll('[data-command]').forEach(button => {
    button.addEventListener('click', async () => {
      const body = {command: button.dataset.command};
      if (body.command === 'DISPATCH') {
        if (!el('targetX').reportValidity() || !el('targetY').reportValidity()) return;
        body.target_x = Number(el('targetX').value);
        body.target_y = Number(el('targetY').value);
      }
      button.disabled = true;
      try {
        const packet = await dgApi('/test-control', {method: 'POST', body});
        notify(`#${packet.id} ${packet.command} 저장 완료. 휴대폰의 수신 기록을 확인하세요.`);
      } catch (error) { notify(error.message); }
      finally { button.disabled = false; }
    });
  });
  el('sound').addEventListener('click', async () => {
    try {
      audio ||= new (window.AudioContext || window.webkitAudioContext)();
      await audio.resume(); beep(); el('sound').textContent = '알림 소리 활성화됨';
    } catch { notify('이 브라우저에서 소리를 활성화할 수 없습니다. 수신 기록으로 확인하세요.'); }
  });
  async function refreshPushStatus() {
    if (!window.isSecureContext) {
      el('pushStatus').textContent = '휴대폰 푸시에는 HTTPS가 필요합니다. 현재는 화면 내 수신과 소리를 사용할 수 있습니다.';
      return;
    }
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
      el('pushStatus').textContent = '이 환경은 Web Push를 지원하지 않습니다. iPhone은 홈 화면에 추가한 뒤 실행하세요.';
      return;
    }
    try {
      const registration = await navigator.serviceWorker.register('/signal-sw.js');
      const subscription = await registration.pushManager.getSubscription();
      el('pushStatus').textContent = subscription ? '이 기기 푸시 등록됨 · 실제 수신 여부를 알림 센터에서 확인하세요.' : '푸시 미등록 · 알림 켜기를 눌러 권한을 허용하세요.';
    } catch (error) { el('pushStatus').textContent = `푸시 준비 실패: ${error.message}`; }
  }
  el('pushOn').addEventListener('click', async () => {
    el('pushOn').disabled = true;
    try {
      if (!window.isSecureContext) throw new Error('휴대폰에서 HTTPS 주소로 접속해야 합니다.');
      if (!('Notification' in window) || !('PushManager' in window)) throw new Error('Web Push 지원 브라우저가 필요합니다. iPhone은 홈 화면에 추가 후 실행하세요.');
      // Request permission directly from the user's click (required on iOS).
      if (await Notification.requestPermission() !== 'granted') throw new Error('브라우저 설정에서 알림을 허용하세요.');
      const config = await dgApi('/test-push');
      if (!config.available) throw new Error(config.reason);
      await navigator.serviceWorker.register('/signal-sw.js');
      const registration = await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (!subscription) {
        const raw = atob(config.public_key.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - config.public_key.length % 4) % 4));
        subscription = await registration.pushManager.subscribe({userVisibleOnly: true,
          applicationServerKey: Uint8Array.from(raw, char => char.charCodeAt(0))});
      }
      await dgApi('/test-push', {method: 'POST', body: subscription.toJSON()});
      el('pushStatus').textContent = '푸시 등록 완료 · 자동 테스트 실행 중이면 다음 신호부터 알림이 옵니다.';
    } catch (error) { el('pushStatus').textContent = error.message; }
    finally { el('pushOn').disabled = false; }
  });
  async function disablePush() {
    if (!('serviceWorker' in navigator)) return;
    const registration = await navigator.serviceWorker.getRegistration('/signal-test.html');
    const subscription = await registration?.pushManager.getSubscription();
    if (subscription) {
      const body = subscription.toJSON();
      await subscription.unsubscribe();
      await dgApi('/test-push', {method: 'DELETE', body});
    }
    el('pushStatus').textContent = '이 기기의 푸시 알림을 껐습니다.';
  }
  el('pushOff').addEventListener('click', () => disablePush().catch(error => { el('pushStatus').textContent = error.message; }));
  el('autoStart').addEventListener('click', async () => {
    try { showAuto(await dgApi('/test-control/auto/start', {method: 'POST'})); }
    catch (error) { notify(error.message); }
  });
  el('autoStop').addEventListener('click', async () => {
    el('autoStop').disabled = true;
    try { showAuto(await dgApi('/test-control/auto/stop', {method: 'POST'})); }
    catch (error) { notify(error.message); el('autoStop').disabled = false; }
  });
  el('logout').addEventListener('click', async () => {
    try { await disablePush(); } catch { /* Local unsubscription still invalidates delivery. */ }
    dgClearSession(); stop(); notify('로그아웃했습니다. 자동 테스트는 서버에서 계속됩니다.');
  });
  dgReady.then(async () => { if (dgGetSession()) await start(); }).catch(error => notify(error.message));
})();
