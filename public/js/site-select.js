/* ============================================================
   site-select.js — site-select.html
   ============================================================ */
const session = dgRequireRole(['operator','admin'], 'index.html');

document.getElementById('welcomeText').textContent =
  session.role === 'admin' ? '환영합니다, 관리자님' : `환영합니다, ${session.name}님`;

function renderSites(){
  const sites = dgGetSites();
  const grid = document.getElementById('siteGrid');
  grid.innerHTML = sites.map(s => {
    if(s.enabled){
      return `<button class="site-card enabled" onclick="enterSite('${s.id}')">
        <div class="site-status">${s.status}</div>
        <div class="site-name">${s.name}</div>
        <div class="site-meta">${s.meta}</div>
      </button>`;
    }
    return `<div class="site-card disabled">
      <div class="site-status">${s.status}</div>
      <div class="site-name">${s.name}</div>
      <div class="site-meta">${s.meta}</div>
    </div>`;
  }).join('');
}
renderSites();

function enterSite(siteId){
  dgAudit(`사이트 진입 · ${siteId} · ${session.name}`);
  window.location.href = `dashboard.html?site=${encodeURIComponent(siteId)}`;
}

document.getElementById('backBtn').addEventListener('click', () => {
  dgAudit(`로그아웃 · ${session.name}`);
  dgClearSession();
  window.location.href = 'index.html';
});
