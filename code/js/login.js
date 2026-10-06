const idInput=document.getElementById('loginId');
const pwInput=document.getElementById('loginPw');
const errBox=document.getElementById('loginError');
async function attemptLogin(){
 const button=document.getElementById('loginBtn');if(button.disabled)return;button.disabled=true;
 try{
  const user=await dgLogin(idInput.value.trim(),pwInput.value);
  
  location.href=user.role==='admin'?'admin.html':'site-select.html';
 }catch(error){errBox.textContent=error.message;errBox.classList.add('show');}
 finally{button.disabled=false;}
}
document.getElementById('loginBtn').addEventListener('click',attemptLogin);
[idInput,pwInput].forEach(el=>el.addEventListener('keydown',e=>{if(e.key==='Enter')attemptLogin();}));
