/* ============================================================
   signup.js — signup.html
   실제로 dg_users 저장소에 계정을 생성하고, 관리자 패널 목록에도
   즉시 반영되며, 가입 직후 자동 로그인까지 이어진다.
   ============================================================ */
const nameInput = document.getElementById('suName');
const idInput   = document.getElementById('suId');
const pwInput   = document.getElementById('suPw');
const pw2Input  = document.getElementById('suPw2');
const errBox    = document.getElementById('signupError');

function showError(msg){
  errBox.textContent = msg;
  errBox.classList.add('show');
}

async function attemptSignup(){
  const name = nameInput.value.trim();
  const id   = idInput.value.trim();
  const pw   = pwInput.value;
  const pw2  = pw2Input.value;

  if(!name || !id || !pw || !pw2){
    showError('모든 항목을 입력해주세요.');
    return;
  }
  if(id.length < 6 || !/^[a-zA-Z0-9_]+$/.test(id)){
    showError('아이디는 영문/숫자/밑줄로 6자 이상이어야 합니다.');
    return;
  }
  if(pw.length < 8){
    showError('비밀번호는 8자 이상이어야 합니다.');
    return;
  }
  if(pw !== pw2){
    showError('비밀번호가 일치하지 않습니다.');
    return;
  }
  const button=document.getElementById('signupBtn');
  if(button.disabled) return;
  button.disabled=true;
  try {
    const user=await dgApi('/auth/signup', {method:'POST', body:{username:id, password:pw, name}});
    dgSaveSession({token:user.access_token, id:user.username, name:user.name, role:user.role});
    window.location.href='site-select.html';
  } catch(error){ showError(error.message); }
  finally { button.disabled=false; }

}

document.getElementById('signupBtn').addEventListener('click', attemptSignup);
[nameInput, idInput, pwInput, pw2Input].forEach(el =>
  el.addEventListener('keydown', e => { if(e.key === 'Enter') attemptSignup(); })
);
