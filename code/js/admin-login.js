/* ============================================================
   admin-login.js — admin-only login (admin-login.html)
   ============================================================ */
const idInput = document.getElementById('loginId');
const pwInput = document.getElementById('loginPw');
const errBox  = document.getElementById('loginError');

function attemptAdminLogin(){
  const id = idInput.value.trim();
  const pw = pwInput.value;

  if(id === DG.ADMIN.id && pw === DG.ADMIN.pw){
    errBox.classList.remove('show');
    dgSaveSession({ role:'admin', id:DG.ADMIN.id, name:DG.ADMIN.name });
    dgAudit(`관리자 로그인 성공 · ${DG.ADMIN.name}`);
    window.location.href = 'admin.html';
  } else {
    errBox.classList.add('show');
    dgAudit(`관리자 로그인 실패 시도 · id="${id}"`);
  }
}

document.getElementById('loginBtn').addEventListener('click', attemptAdminLogin);
[idInput, pwInput].forEach(el => el.addEventListener('keydown', e => { if(e.key === 'Enter') attemptAdminLogin(); }));

(function(){
  const s = dgGetSession();
  if(s && s.role === 'admin'){ window.location.href = 'admin.html'; }
})();
