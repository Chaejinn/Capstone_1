/* ============================================================
   admin.js — admin.html
   ============================================================ */
const session = dgRequireRole(['admin'], 'admin-login.html');
document.getElementById('userLabel').textContent = '관리자님';

function tickClock(){ document.getElementById('clock').textContent = new Date().toLocaleString('ko-KR',{hour12:false}); }
tickClock(); setInterval(tickClock,1000);

document.getElementById('logoutBtn').addEventListener('click', () => {
  dgAudit(`관리자 로그아웃 · ${session.name}`);
  dgClearSession();
  window.location.href = 'admin-login.html';
});

/* ---------------- NAV ---------------- */
function switchView(v){
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active', b.dataset.view===v));
  document.querySelectorAll('.view').forEach(el=>el.hidden = el.id!=='view-'+v);
  if(v==='overview') renderOverview();
  if(v==='users') renderUsers();
  if(v==='sites') renderSites();
  if(v==='config') renderConfig();
  if(v==='audit') renderAuditFull();
}

/* ---------------- OVERVIEW ---------------- */
function renderOverview(){
  const users = dgGetUsers(), sites = dgGetSites(), audit = dgGetAudit();
  document.getElementById('kpiUsers').textContent = users.length;
  document.getElementById('kpiSites').textContent = sites.length;
  document.getElementById('kpiSitesActive').textContent = sites.filter(s=>s.enabled).length;
  document.getElementById('kpiAudit').textContent = audit.length;
  document.getElementById('recentAudit').innerHTML = audit.slice(-8).map(a=>
    `<div class="audit-item"><span class="t">${a.t}</span>${a.action}</div>`).join('') || '<div class="audit-item">기록 없음</div>';
}

/* ---------------- USERS ---------------- */
function renderUsers(){
  const users = dgGetUsers();
  document.getElementById('userTableBody').innerHTML = users.map((u,i)=>`
    <tr>
      <td class="mono">${u.id}</td>
      <td>${u.name}</td>
      <td><span class="role-pill">${u.role}</span></td>
      <td><span class="active-pill ${u.active?'':'off'}" style="cursor:pointer;" onclick="toggleUserActive(${i})">${u.active?'● 활성':'○ 비활성'}</span></td>
      <td><button class="del-btn" onclick="removeUser(${i})">✕</button></td>
    </tr>`).join('') || '<tr><td colspan="5" class="mono">등록된 계정이 없습니다.</td></tr>';
}
function toggleUserActive(i){
  const users = dgGetUsers();
  users[i].active = !users[i].active;
  dgSaveUsers(users);
  dgAudit(`계정 ${users[i].active?'활성화':'비활성화'} · ${users[i].id}`);
  renderUsers();
}
function removeUser(i){
  const users = dgGetUsers();
  const removed = users.splice(i,1)[0];
  dgSaveUsers(users);
  dgAudit(`계정 삭제 · ${removed.id} (${removed.name})`);
  renderUsers();
}
function addUser(){
  const id = document.getElementById('newUserId').value.trim();
  const pw = document.getElementById('newUserPw').value.trim();
  const name = document.getElementById('newUserName').value.trim() || id;
  if(!id || !pw){ alert('아이디와 비밀번호를 입력하세요.'); return; }
  const users = dgGetUsers();
  if(users.some(u=>u.id===id)){ alert('이미 존재하는 아이디입니다.'); return; }
  users.push({id, pw, name, role:'operator', active:true});
  dgSaveUsers(users);
  dgAudit(`계정 생성 · ${id} (${name})`);
  document.getElementById('newUserId').value='';
  document.getElementById('newUserPw').value='';
  document.getElementById('newUserName').value='';
  renderUsers();
}

/* ---------------- SITES ---------------- */
function renderSites(){
  const sites = dgGetSites();
  document.getElementById('siteManageCard').innerHTML = sites.map((s,i)=>`
    <div class="site-manage-row">
      <div class="sname">${s.name}</div>
      <div class="smeta">${s.meta} · ${s.status}</div>
      <div class="switch-wrap">비활성<div class="switch ${s.enabled?'on':''}" onclick="toggleSite(${i})"></div>활성</div>
    </div>`).join('');
}
function toggleSite(i){
  const sites = dgGetSites();
  sites[i].enabled = !sites[i].enabled;
  sites[i].status = sites[i].enabled ? '운영중' : '준비중';
  dgSaveSites(sites);
  dgAudit(`사이트 ${sites[i].enabled?'활성화':'비활성화'} · ${sites[i].name}`);
  renderSites();
}

/* ---------------- GLOBAL CONFIG ---------------- */
function renderConfig(){
  const s = dgGetSettings();
  document.getElementById('gConf').value = s.threshConf ?? 0.90;
  document.getElementById('gFr').value = s.threshFrames ?? 15;
  document.getElementById('gConfLbl').textContent = (s.threshConf ?? 0.90).toFixed(2);
  document.getElementById('gFrLbl').textContent = (s.threshFrames ?? 15)+' 프레임';
}
function updateGlobal(){
  const threshConf = parseFloat(document.getElementById('gConf').value);
  const threshFrames = parseInt(document.getElementById('gFr').value);
  document.getElementById('gConfLbl').textContent = threshConf.toFixed(2);
  document.getElementById('gFrLbl').textContent = threshFrames+' 프레임';
  dgSaveSettings({threshConf, threshFrames});
  document.getElementById('gSavedNote').textContent = '저장됨 · '+new Date().toLocaleTimeString('ko-KR',{hour12:false});
}

/* ---------------- DANGER ZONE ---------------- */
function dangerLogoutAll(){
  dgAudit('관리자가 세션 강제 종료 실행');
  dgClearSession();
  window.location.href = 'admin-login.html';
}
function dangerClearAudit(){
  if(!confirm('감사 로그를 모두 삭제할까요?')) return;
  dgClearAudit();
  dgAudit('감사 로그 초기화 실행됨');
  renderAuditFull();
}
function dangerFactoryReset(){
  if(!confirm('계정·사이트·설정·로그를 모두 초기화합니다. 계속할까요?')) return;
  dgFactoryReset();
  dgAudit('플랫폼 전체 초기화 실행됨');
  alert('초기화되었습니다. 로그인 화면으로 이동합니다.');
  window.location.href = 'admin-login.html';
}

/* ---------------- AUDIT ---------------- */
function renderAuditFull(){
  const audit = dgGetAudit();
  document.getElementById('auditCount').textContent = audit.length+'건';
  document.getElementById('auditList').innerHTML = audit.slice().reverse().map(a=>
    `<div class="audit-item"><span class="t">${a.t}</span>${a.action}</div>`).join('') || '<div class="audit-item">기록 없음</div>';
}
function exportAudit(){
  const audit = dgGetAudit();
  const text = audit.map(a=>`[${a.t}] ${a.action}`).join('\n');
  const blob = new Blob([text], {type:'text/plain'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'drown-guardian-audit-log.txt';
  a.click();
  URL.revokeObjectURL(url);
  dgAudit('감사 로그 내보내기 실행됨');
}

/* ---------------- INIT ---------------- */
renderOverview();
