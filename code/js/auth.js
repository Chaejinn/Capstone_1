/* Server-backed authentication. Passwords stay out of browser storage. */
const DG = {KEYS:{session:'dg_api_session'}};
const dgData = {users:[], sites:[], settings:{}, audit:[], roi:[]};
function dgGetSession(){try{return JSON.parse(sessionStorage.getItem(DG.KEYS.session));}catch{return null;}}
function dgSaveSession(value){sessionStorage.setItem(DG.KEYS.session,JSON.stringify(value));}
function dgClearSession(){sessionStorage.removeItem(DG.KEYS.session);}
function dgRequireRole(roles,fallback='index.html'){
 const session=dgGetSession();
 if(!session || !roles.includes(session.role)){location.replace(fallback);throw new Error('로그인이 필요합니다.');}
 return session;
}
async function dgApi(path,options={}){
 const headers=new Headers(options.headers), session=dgGetSession();
 if(session?.token) headers.set('Authorization',`Bearer ${session.token}`);
 let body=options.body;
 if(body && !(body instanceof URLSearchParams) && !(body instanceof FormData)){
  headers.set('Content-Type','application/json');body=JSON.stringify(body);
 }
 const response=await fetch(`/api${path}`,{...options,headers,body});
 const data=await response.json().catch(()=>null);
 if(!response.ok){
  if(response.status===401 && path!=='/auth/login') dgClearSession();
  const detail=data?.detail;
  throw new Error(typeof detail==='string'?detail:'요청을 처리하지 못했습니다. 입력 값과 서버 연결을 확인하세요.');
 }
 return data;
}
async function dgLogin(username,password){
 const data=await dgApi('/auth/login',{method:'POST',body:new URLSearchParams({username,password})});
 dgSaveSession({token:data.access_token,id:data.username,name:data.name,role:data.role});return data;
}
async function dgRefresh(){
 if(!dgGetSession()) return;
 const me=await dgApi('/auth/me');
 dgSaveSession({...dgGetSession(),id:me.username,name:me.name,role:me.role});
 const [sites,settings]=await Promise.all([dgApi('/sites'),dgApi('/settings')]);
 dgData.sites=sites;dgData.settings={threshConf:settings.thresh_conf,threshFrames:settings.thresh_frames};
 const siteId=new URLSearchParams(location.search).get('site');
 if(siteId && sites.some(site=>site.id===siteId)){
  dgData.roi=(await dgApi(`/sites/${encodeURIComponent(siteId)}/roi`)).points;
 }
 if(me.role==='admin'){
  const [users,audit]=await Promise.all([dgApi('/users'),dgApi('/audit')]);
  dgData.users=users.filter(u=>u.role!=='admin').map(u=>({...u,dbId:u.id,id:u.username}));
  dgData.audit=audit.reverse().map(a=>({t:new Date(a.timestamp+'Z').toLocaleString('ko-KR',{hour12:false}),action:a.action}));
 }
}
function dgGetUsers(){return dgData.users;}
function dgGetSites(){return dgData.sites;}
function dgGetSettings(){return dgData.settings;}
function dgGetAudit(){return dgData.audit;}
// API mutations write their own server audit records.
function dgAudit(){}
async function dgSaveSettings(value){
 const saved=await dgApi('/settings',{method:'PUT',body:{thresh_conf:value.threshConf,thresh_frames:value.threshFrames}});
 dgData.settings={threshConf:saved.thresh_conf,threshFrames:saved.thresh_frames};
}
async function dgClearAudit(){await dgApi('/audit',{method:'DELETE'});dgData.audit=[];}
const dgReady=dgRefresh().catch(error=>{if(dgGetSession())throw error;});

function dgEscape(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
