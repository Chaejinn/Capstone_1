/* ============================================================
   dashboard.js — dashboard.html
   ============================================================ */

/* ---------------- session guard & topbar ---------------- */
const session = dgRequireRole(['operator','admin'], 'index.html');

(function initTopbar(){
  document.getElementById('userLabel').textContent =
    session.role === 'admin' ? '관리자님' : '운영자 · ' + session.name;

  if(session.role === 'admin'){
    document.getElementById('adminLink').style.display = 'inline-block';
  }

  const params = new URLSearchParams(window.location.search);
  const siteId = params.get('site');
  const site = dgGetSites().find(s => s.id === siteId);
  document.getElementById('siteLabel').textContent = site ? `${site.name} · BOARD-01` : '사이트 미지정';

  document.getElementById('logoutBtn').addEventListener('click', () => {
    clearInterval(simTimer);
    dgAudit(`로그아웃 · ${session.name}`);
    dgClearSession();
    window.location.href = 'index.html';
  });
})();

/* ---------------- CLOCK ---------------- */
function tickClock(){
  document.getElementById('clock').textContent = new Date().toLocaleString('ko-KR',{hour12:false});
}
tickClock(); setInterval(tickClock,1000);

/* ---------------- NAV ---------------- */
function switchView(v){
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active', b.dataset.view===v));
  document.querySelectorAll('.view').forEach(el=>el.hidden = el.id!=='view-'+v);
  if(v==='settings'){ renderRoi(); renderContacts(); }
  if(v==='system'){ renderDiag(); }
  if(v==='events'){ renderLog(); }
}

/* ---------------- STATE ---------------- */
const globalSettings = dgGetSettings();
const state = {
  phase:'IDLE', running:false, mode:'AUTO', estop:false,
  confidence:0, distance:null, battery:87,
  boardPos:{x:15,y:78}, targetPos:{x:62,y:38}, approachPos:{x:54,y:44},
  stepIndex:-1,
  threshConf: globalSettings.threshConf ?? 0.90,
  threshFrames: globalSettings.threshFrames ?? 15,
  nightPreview:false,
  roi:[{x:12,y:20},{x:70,y:10},{x:88,y:55},{x:55,y:88},{x:8,y:60}],
  log:[],
  contacts:[
    {name:'김규량', phone:'010-5034-0284', notify:true},
    {name:'박정우', phone:'010-9633-1959', notify:true},
    {name:'이지훈', phone:'010-7719-4482', notify:false},
  ],
  diag:{'카메라':'ok','GPU 서버':'ok','배터리':'ok','모터':'ok','통신':'ok'},
};
document.getElementById('threshConf').value = state.threshConf;
document.getElementById('threshFr').value = state.threshFrames;
document.getElementById('threshConfLbl').textContent = state.threshConf.toFixed(2);
document.getElementById('threshFrLbl').textContent = state.threshFrames+' 프레임';

let simTimer=null, screeningTicks=0;

/* ---------------- LOGGING ---------------- */
function pushLog(text, level){
  const t = new Date().toLocaleTimeString('ko-KR',{hour12:false});
  state.log.push({t, text, level: level||'info'});
  renderLog();
}
function renderLog(){
  const mkItem = (e)=>`<div class="log-item ${e.level==='crit'?'crit':e.level==='warn'?'warn':''}"><span class="t">${e.t}</span>${e.text}</div>`;
  const items = state.log.slice(-40).map(mkItem).join('');
  document.getElementById('logList').innerHTML = items;
  document.getElementById('logListFull').innerHTML = state.log.slice().reverse().map(mkItem).join('');
  document.getElementById('logCount').textContent = state.log.length+'건';
}

/* ---------------- ROI RENDER ---------------- */
function roiPointsStr(){ return state.roi.map(p=>`${p.x},${p.y}`).join(' '); }
function renderRoi(){
  document.getElementById('roiPolyControl').setAttribute('points', roiPointsStr());
  document.getElementById('roiPolyEdit').setAttribute('points', roiPointsStr());
  const svg = document.getElementById('roiSvgEdit');
  svg.querySelectorAll('circle').forEach(c=>c.remove());
  state.roi.forEach((p,i)=>{
    const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
    c.setAttribute('cx',p.x); c.setAttribute('cy',p.y); c.setAttribute('r',2.2);
    c.setAttribute('fill','#2DD9C4'); c.setAttribute('stroke','#080D17'); c.setAttribute('stroke-width','0.6');
    c.style.cursor='grab';
    c.addEventListener('pointerdown', e=>{
      e.preventDefault();
      const move = (ev)=>{
        const rect = svg.getBoundingClientRect();
        let x = (ev.clientX-rect.left)/rect.width*100;
        let y = (ev.clientY-rect.top)/rect.height*100;
        x=Math.max(0,Math.min(100,x)); y=Math.max(0,Math.min(100,y));
        state.roi[i]={x,y}; renderRoi();
      };
      const up = ()=>{ document.removeEventListener('pointermove',move); document.removeEventListener('pointerup',up); };
      document.addEventListener('pointermove',move); document.addEventListener('pointerup',up);
    });
    svg.appendChild(c);
  });
}
function addRoiPoint(){
  const cx = state.roi.reduce((s,p)=>s+p.x,0)/state.roi.length;
  const cy = state.roi.reduce((s,p)=>s+p.y,0)/state.roi.length;
  state.roi.push({x:cx+(Math.random()*10-5), y:cy+(Math.random()*10-5)});
  renderRoi();
  pushLog('감시 ROI 정점 추가됨 · 총 '+state.roi.length+'개','info');
}
function resetRoi(){
  state.roi=[{x:12,y:20},{x:70,y:10},{x:88,y:55},{x:55,y:88},{x:8,y:60}];
  renderRoi();
  pushLog('감시 ROI가 기본값으로 초기화됨','info');
}

/* ---------------- THRESHOLDS ---------------- */
function updateThresh(){
  state.threshConf = parseFloat(document.getElementById('threshConf').value);
  state.threshFrames = parseInt(document.getElementById('threshFr').value);
  document.getElementById('threshConfLbl').textContent = state.threshConf.toFixed(2);
  document.getElementById('threshFrLbl').textContent = state.threshFrames+' 프레임';
}

/* ---------------- SWITCHES ---------------- */
function toggleSwitch(id){ document.getElementById(id).classList.toggle('on'); }
function toggleNightPreview(){
  state.nightPreview=!state.nightPreview;
  document.getElementById('nightForceSwitch').classList.toggle('on', state.nightPreview);
  applyNight();
  pushLog(state.nightPreview? '야간(IR) 모드 미리보기 적용됨' : '주간 모드로 복귀', 'info');
}
function applyNight(){
  document.getElementById('videoPanel').classList.toggle('night', state.nightPreview);
  document.getElementById('irBadge').style.display = state.nightPreview? 'block':'none';
}

/* ---------------- CONTACTS ---------------- */
function renderContacts(){
  const wrap = document.getElementById('contactList');
  wrap.innerHTML = state.contacts.map((c,i)=>`
    <div class="contact-row">
      <input type="checkbox" ${c.notify?'checked':''} onchange="state.contacts[${i}].notify=this.checked">
      <input class="mono name" type="text" value="${c.name}" onchange="state.contacts[${i}].name=this.value">
      <input class="mono phone" type="text" value="${c.phone}" onchange="state.contacts[${i}].phone=this.value">
      <span class="mono" style="font-size:10px; color:var(--text-2);">${c.notify?'알림 ON':'알림 OFF'}</span>
      <button class="del-btn" onclick="removeContact(${i})">✕</button>
    </div>`).join('');
  document.getElementById('contactCount').textContent = state.contacts.length+'명';
}
function addContact(){
  state.contacts.push({name:'신규 관리자', phone:'010-0000-0000', notify:true});
  renderContacts();
}
function removeContact(i){ state.contacts.splice(i,1); renderContacts(); }

/* ---------------- DIAGNOSTICS ---------------- */
function renderDiag(){
  const labels = Object.keys(state.diag);
  document.getElementById('diagGrid').innerHTML = labels.map(k=>`
    <div class="diag-card">
      <div class="name">${k}</div>
      <div class="status ${state.diag[k]}" id="diag-${k}">${diagText(state.diag[k])}</div>
    </div>`).join('');
}
function diagText(s){ return s==='ok'?'● 정상':s==='warn'?'▲ 경고':'검사 중...'; }
function runDiagnostics(){
  const labels = Object.keys(state.diag);
  labels.forEach(k=> state.diag[k]='checking');
  renderDiag();
  labels.forEach((k,i)=>{
    setTimeout(()=>{
      state.diag[k] = (k==='배터리' && state.battery<30) ? 'warn' : 'ok';
      const el = document.getElementById('diag-'+k);
      if(el){ el.className='status '+state.diag[k]; el.textContent=diagText(state.diag[k]); }
      if(i===labels.length-1) pushLog('자기진단 완료 · 전 항목 점검됨','info');
    }, 500+i*400);
  });
}
renderDiag();

/* ---------------- MODE / ESTOP ---------------- */
function toggleMode(){
  if(state.estop) return;
  state.mode = state.mode==='AUTO' ? 'MANUAL' : 'AUTO';
  document.getElementById('modeSwitch').classList.toggle('on', state.mode==='MANUAL');
  document.getElementById('manualPanel').style.display = state.mode==='MANUAL' ? 'block':'none';
  document.getElementById('statMode').textContent = state.mode==='MANUAL' ? '수동':'자율';
  updateModeBadge();
  pushLog(state.mode==='MANUAL' ? '수동 조작 모드로 전환됨 (관리자 명령 우선)' : '자율 모드로 복귀됨', state.mode==='MANUAL'?'warn':'info');
}
function updateModeBadge(){
  const b = document.getElementById('modeBadge');
  b.classList.remove('manual','estop');
  if(state.estop){ b.textContent='⛔ 비상정지'; b.classList.add('estop'); }
  else if(state.mode==='MANUAL'){ b.textContent='수동 모드'; b.classList.add('manual'); }
  else { b.textContent='자율 모드'; }
}
function triggerEstop(){
  state.estop=true; state.running=false;
  clearInterval(simTimer);
  document.getElementById('estopOverlay').style.display='flex';
  document.getElementById('startBtn').disabled=true;
  document.getElementById('pauseBtn').disabled=true;
  updateModeBadge();
  pushLog('🛑 비상정지 발동 — 모든 추진 즉시 정지 (FR-SAF-004)','crit');
  dgAudit('비상정지 발동 · dashboard');
}
function clearEstop(){
  state.estop=false;
  document.getElementById('estopOverlay').style.display='none';
  document.getElementById('startBtn').disabled=false;
  updateModeBadge();
  pushLog('비상정지 해제됨 · 시스템 대기 상태로 복귀','info');
}

/* ---------------- MANUAL CONTROL ---------------- */
function manualMove(dx,dy){
  if(state.estop || state.mode!=='MANUAL') return;
  state.boardPos.x = Math.max(2,Math.min(95, state.boardPos.x+dx*3));
  state.boardPos.y = Math.max(2,Math.min(95, state.boardPos.y+dy*3));
  renderBoard();
  updateDistanceFromPositions();
}
function forceDeploy(){
  if(state.estop) return;
  state.phase='DEPLOYING'; state.stepIndex=4;
  renderStepper(); renderBoard();
  pushLog('관리자 강제 부력체 전개 명령 실행됨 (FR-SAF-003)','warn');
  setTimeout(()=>{ state.phase='COMPLETE'; pushLog('부력체 전개 완료 · 구조대 인계 대기','crit'); },900);
}

/* ---------------- SIM CORE ---------------- */
function startSim(){
  if(state.estop) return;
  state.running=true;
  document.getElementById('startBtn').disabled=true;
  document.getElementById('pauseBtn').disabled=false;
  if(state.phase==='IDLE'){ pushLog('시뮬레이션 시작 · 상시 수면 감시 중','info'); }
  simTimer = setInterval(tick, 750);
}
function pauseSim(){
  state.running=false; clearInterval(simTimer);
  document.getElementById('startBtn').disabled=false;
  document.getElementById('pauseBtn').disabled=true;
  pushLog('시뮬레이션 일시정지됨','info');
}
function resetSim(){
  clearInterval(simTimer); state.running=false; state.estop=false;
  state.phase='IDLE'; state.confidence=0; state.distance=null; screeningTicks=0; state.stepIndex=-1;
  state.battery=87; state.mode='AUTO';
  state.boardPos={x:15,y:78};
  document.getElementById('estopOverlay').style.display='none';
  document.getElementById('modeSwitch').classList.remove('on');
  document.getElementById('manualPanel').style.display='none';
  document.getElementById('startBtn').disabled=false;
  document.getElementById('pauseBtn').disabled=true;
  document.getElementById('alertBanner').style.display='none';
  document.getElementById('targetBox').style.display='none';
  updateModeBadge();
  renderStepper(); renderBoard(); updateSideStats();
  state.log=[]; renderLog();
  pushLog('시스템 리셋됨 · 대기 상태','info');
}

function tick(){
  if(state.estop) return;

  if(state.phase==='IDLE'){
    state.phase='SCREENING'; screeningTicks=0; state.confidence=0.35;
    showTargetBox('screening');
    pushLog('경량 검출기가 이상 후보 포착 · VLM 판정 대상으로 승격','warn');
  }
  else if(state.phase==='SCREENING'){
    screeningTicks++;
    state.confidence = Math.min(0.99, state.confidence + 0.09 + Math.random()*0.05);
    updateAlertConf();
    const neededTicks = Math.max(3, Math.round(state.threshFrames/5));
    if(state.confidence >= state.threshConf && screeningTicks >= neededTicks){
      state.phase='ALERT';
      state.distance=40;
      showTargetBox('alert');
      document.getElementById('alertBanner').style.display='flex';
      pushLog(`⚠ 익수 판정 — ID 02 · 신뢰도 ${(state.confidence*100).toFixed(0)}% · 출동 명령 발행 (3초 이내)`,'crit');
      state.contacts.filter(c=>c.notify).forEach(c=> pushLog(`관리자 알림 발송 → ${c.name} (${c.phone})`,'info'));
      dgAudit(`익수 판정 이벤트 발생 · 신뢰도 ${(state.confidence*100).toFixed(0)}%`);
      state.phase='APPROACHING'; state.stepIndex=1;
    }
  }
  else if(state.phase==='APPROACHING'){
    if(state.mode==='AUTO'){
      state.distance = Math.max(0, state.distance - (1.1+Math.random()*0.4));
      const frac = 1 - Math.min(1, state.distance/40);
      state.boardPos.x = 15 + (state.approachPos.x-15)*frac;
      state.boardPos.y = 78 + (state.approachPos.y-78)*frac;
      renderBoard();
      if(state.distance<=2){
        state.phase='DEPLOYING'; state.stepIndex=2;
        pushLog('초음파 임계 거리 도달 · 추진 정지 · 하부 진입 정렬 시작','info');
      }
    }
  }
  else if(state.phase==='DEPLOYING'){
    state.stepIndex = Math.min(4, state.stepIndex+1);
    if(state.stepIndex===3) pushLog('요구조자 하부 진입 자세 정렬 완료','info');
    if(state.stepIndex>=4){
      state.phase='COMPLETE';
      pushLog('🎈 부력체 전개 완료 · 상체·기도 확보 · 구조대 인계 대기','crit');
      dgAudit('부력체 전개 완료 · 구조 시뮬레이션 종료');
      pauseSim();
    }
    state.battery = Math.max(0, state.battery-1);
  }
  else if(state.phase==='COMPLETE'){
    pauseSim();
  }

  renderStepper(); updateSideStats();
}

function showTargetBox(kind){
  const box = document.getElementById('targetBox');
  box.style.display='block';
  box.style.left = (state.targetPos.x-8)+'%';
  box.style.top = (state.targetPos.y-10)+'%';
  box.style.width='16%'; box.style.height='24%';
  box.className = 'det-box '+(kind==='screening'?'screening':'alertbox');
  document.getElementById('targetLbl').textContent = kind==='screening' ? '후보 02 · 분석중' : `ID 02 · 익수 ${(state.confidence*100).toFixed(0)}%`;
}
function updateAlertConf(){
  document.getElementById('alertConf').textContent = '신뢰도 '+(state.confidence*100).toFixed(0)+'%';
  document.getElementById('targetLbl').textContent = state.phase==='SCREENING' ? '후보 02 · 분석중' : `ID 02 · 익수 ${(state.confidence*100).toFixed(0)}%`;
}
function renderBoard(){
  const el = document.getElementById('boardIcon');
  el.style.left = state.boardPos.x+'%'; el.style.top = state.boardPos.y+'%';
}
function updateDistanceFromPositions(){
  if(state.distance===null) return;
  const dx = state.boardPos.x-state.approachPos.x, dy = state.boardPos.y-state.approachPos.y;
  state.distance = Math.max(0, Math.sqrt(dx*dx+dy*dy)*0.9);
  updateSideStats();
}
function renderStepper(){
  document.querySelectorAll('#stepper .seg').forEach(seg=>{
    const idx = parseInt(seg.dataset.s);
    seg.classList.remove('done','now');
    if(idx < state.stepIndex) seg.classList.add('done');
    else if(idx === state.stepIndex) seg.classList.add(state.phase==='COMPLETE'?'done':'now');
  });
}
function updateSideStats(){
  document.getElementById('statMode').textContent = state.mode==='MANUAL' ? '수동' : '자율';
  document.getElementById('statDist').textContent = state.distance===null ? '— m' : state.distance.toFixed(1)+' m';
  document.getElementById('statSpeed').textContent = (state.phase==='APPROACHING' && state.mode==='AUTO') ? '1.1 m/s' : '0.0 m/s';
  document.getElementById('statBatt').textContent = state.battery+'%';
  document.getElementById('battBar').style.width = state.battery+'%';
  document.getElementById('battBar').style.background = state.battery<25 ? 'var(--red)' : state.battery<50 ? 'var(--amber)' : 'var(--teal)';
}

/* ---------------- INIT ---------------- */
renderRoi();
renderContacts();
renderBoard();
renderStepper();
updateSideStats();
pushLog('시스템 초기화 완료 · 상시 수면 감시 대기 중','info');
