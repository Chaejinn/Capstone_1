/* ============================================================
   auth.js — shared session, user, site & settings storage
   Loaded on every page BEFORE the page-specific script.
   Uses localStorage so state is genuinely shared across pages
   (this is a real multi-page project, not a sandboxed artifact).
   ============================================================ */

const DG = {
  KEYS: {
    session:'dg_session',
    users:'dg_users',
    sites:'dg_sites',
    settings:'dg_global_settings',
    audit:'dg_audit',
  },
  ADMIN: { id:'capstone1', pw:'20262026', name:'시스템 관리자' }, // fixed superuser, not editable via UI
  SITES: [
    {id:'chunjeon', name:'금오천 일대', meta:'CAM-01 · BOARD-01 · 실내 수조 실증', status:'운영중', enabled:true},
    {id:'river-b',  name:'낙동강 체육공원', meta:'다중 노드 확장 · 범위 외 (후속 과제)', status:'준비중', enabled:false},
    {id:'farm-c',   name:'금호강 낚시스팟', meta:'확장 응용 · 범위 외 (후속 과제)', status:'준비중', enabled:false},
    {id:'port-d',   name:'선산대교 밑 낚시스팟', meta:'확장 응용 · 범위 외 (후속 과제)', status:'준비중', enabled:false},
  ],
};

/* ---------- seed default data on first run ---------- */
function dgSeed(){
  if(!localStorage.getItem(DG.KEYS.users)){
    localStorage.setItem(DG.KEYS.users, JSON.stringify([
      {id:'chacha', pw:'guardian2026', name:'차유비', role:'operator', active:true},
      {id:'kyuryang', pw:'guardian2026', name:'김규량', role:'operator', active:true},
      {id:'chaejin',  pw:'guardian2026', name:'김채진', role:'operator', active:true},
    ]));
  }
  if(!localStorage.getItem(DG.KEYS.sites)){
    localStorage.setItem(DG.KEYS.sites, JSON.stringify(DG.SITES));
  } else {
    // 기존 브라우저에 저장된 활성화 상태는 유지하면서 변경된 사이트명을 반영한다.
    const sites = JSON.parse(localStorage.getItem(DG.KEYS.sites));
    const latestNames = Object.fromEntries(DG.SITES.map(site => [site.id, site.name]));
    let changed = false;
    sites.forEach(site => {
      if(latestNames[site.id] && site.name !== latestNames[site.id]){
        site.name = latestNames[site.id];
        changed = true;
      }
    });
    if(changed) localStorage.setItem(DG.KEYS.sites, JSON.stringify(sites));
  }
  if(!localStorage.getItem(DG.KEYS.settings)){
    localStorage.setItem(DG.KEYS.settings, JSON.stringify({ threshConf:0.90, threshFrames:15 }));
  }
  if(!localStorage.getItem(DG.KEYS.audit)){
    localStorage.setItem(DG.KEYS.audit, JSON.stringify([]));
  }
}
dgSeed();

/* ---------- users ---------- */
function dgGetUsers(){ return JSON.parse(localStorage.getItem(DG.KEYS.users) || '[]'); }
function dgSaveUsers(list){ localStorage.setItem(DG.KEYS.users, JSON.stringify(list)); }

/* ---------- sites ---------- */
function dgGetSites(){ return JSON.parse(localStorage.getItem(DG.KEYS.sites) || '[]'); }
function dgSaveSites(list){ localStorage.setItem(DG.KEYS.sites, JSON.stringify(list)); }

/* ---------- global default settings ---------- */
function dgGetSettings(){ return JSON.parse(localStorage.getItem(DG.KEYS.settings) || '{}'); }
function dgSaveSettings(obj){ localStorage.setItem(DG.KEYS.settings, JSON.stringify(obj)); }

/* ---------- audit log ---------- */
function dgAudit(action){
  const log = JSON.parse(localStorage.getItem(DG.KEYS.audit) || '[]');
  log.push({ t: new Date().toLocaleString('ko-KR',{hour12:false}), action });
  localStorage.setItem(DG.KEYS.audit, JSON.stringify(log));
}
function dgGetAudit(){ return JSON.parse(localStorage.getItem(DG.KEYS.audit) || '[]'); }
function dgClearAudit(){ localStorage.setItem(DG.KEYS.audit, JSON.stringify([])); }

/* ---------- session ---------- */
function dgSaveSession(obj){ localStorage.setItem(DG.KEYS.session, JSON.stringify(obj)); }
function dgGetSession(){ try{ return JSON.parse(localStorage.getItem(DG.KEYS.session)); }catch(e){ return null; } }
function dgClearSession(){ localStorage.removeItem(DG.KEYS.session); }

/* Redirects to `fallback` if there's no session, or the session role
   isn't in `roles`. Call at the very top of any protected page. */
function dgRequireRole(roles, fallback){
  const s = dgGetSession();
  if(!s || !roles.includes(s.role)){
    window.location.href = fallback || 'index.html';
    return null;
  }
  return s;
}

/* ---------- factory reset (admin danger zone) ---------- */
function dgFactoryReset(){
  Object.values(DG.KEYS).forEach(k=> localStorage.removeItem(k));
  dgSeed();
}
