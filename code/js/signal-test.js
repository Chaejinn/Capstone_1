/* Foreground polling deliberately works without WebSocket hosting or push services. */
(() => {
  const el = id => document.getElementById(id);
  let controlCursor = 0;
  let cursor = 0, timer, running = false, generation = 0, count = 0, audio;
  const notify = message => { el('notice').textContent = message; };
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
  el('logout').addEventListener('click', () => { dgClearSession(); stop(); notify('로그아웃했습니다.'); });
  dgReady.then(async () => { if (dgGetSession()) await start(); }).catch(error => notify(error.message));
})();
