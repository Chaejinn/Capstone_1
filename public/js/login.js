/* ============================================================
   login.js — operator login (index.html)
   ============================================================ */
const idInput = document.getElementById('loginId');
const pwInput = document.getElementById('loginPw');
const errBox  = document.getElementById('loginError');

function attemptLogin(){
  const id = idInput.value.trim();
  const pw = pwInput.value;
  const user = dgGetUsers().find(u => u.id === id && u.pw === pw);

  if(user && user.active){
    errBox.classList.remove('show');
    dgSaveSession({ role:'operator', id:user.id, name:user.name });
    dgAudit(`로그인 성공 · ${user.name} (${user.id})`);
    window.location.href = 'site-select.html';
  } else {
    errBox.classList.add('show');
    dgAudit(`로그인 실패 시도 · id="${id}"`);
  }
}

document.getElementById('loginBtn').addEventListener('click', attemptLogin);
[idInput, pwInput].forEach(el => el.addEventListener('keydown', e => { if(e.key === 'Enter') attemptLogin(); }));

/* if already logged in as operator, skip straight to site select */
(function(){
  const s = dgGetSession();
  if(s && s.role === 'operator'){
    window.location.href = 'site-select.html';
  }
})();
