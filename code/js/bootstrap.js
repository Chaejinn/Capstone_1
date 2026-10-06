/* Load classic page scripts only after server session verification. */
const dgPageScripts=document.currentScript.dataset.scripts.split(',');
(async()=>{
 try{
  await dgReady;
  for(const src of dgPageScripts){
   await new Promise((resolve,reject)=>{
    const script=document.createElement('script');script.src=src;
    script.onload=resolve;script.onerror=reject;document.body.appendChild(script);
   });
  }
 }catch(error){
  const box=document.createElement('div');box.setAttribute('role','alert');
  box.style.cssText='position:fixed;inset:0;z-index:9999;background:#080d17;color:white;display:grid;place-content:center;padding:24px;gap:16px';
  const message=document.createElement('p');message.textContent=error.message||'서버에 연결하지 못했습니다.';
  const retry=document.createElement('button');retry.textContent='다시 시도';retry.onclick=()=>location.reload();
  box.append(message,retry);document.body.append(box);
 }
})();
