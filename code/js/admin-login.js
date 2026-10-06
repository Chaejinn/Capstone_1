const idInput=document.getElementById('loginId');
const pwInput=document.getElementById('loginPw');
const errBox=document.getElementById('loginError');
async function attemptAdminLogin(){
 const button=document.getElementById('loginBtn');if(button.disabled)return;button.disabled=true;
 try{
  const user=await dgLogin(idInput.value.trim(),pwInput.value);
  if(user.role!=='admin'){dgClearSession();throw new Error('관리자 권한이 필요합니다.');}
  location.href='admin.html';
 }catch(error){errBox.textContent=error.message;errBox.classList.add('show');}
 finally{button.disabled=false;}
}
document.getElementById('loginBtn').addEventListener('click',attemptAdminLogin);
[idInput,pwInput].forEach(el=>el.addEventListener('keydown',e=>{if(e.key==='Enter')attemptAdminLogin();}));
