import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

async function scenario({source='deployed', expired=false, mismatch=false, error=false, deferred=false, poseOnly=false, stalePose=false, missing=false}={}){
  const elements=new Map(), calls=[], timers=new Map(), pending=[]; let nextTimer=0;
  function el(id){
    if(!elements.has(id)) elements.set(id,{value:'',disabled:false,hidden:true,textContent:'',handlers:{},
      addEventListener(type,fn){this.handlers[type]=fn;},click(){this.handlers.click?.();},
      getContext(){return {drawImage(){},strokeRect(){}};}});
    return elements.get(id);
  }
  el('edgeSource').value=source;el('edgeCameraId').value='camera-01';
  const captured_at=new Date(Date.now()-(expired?40000:1000)).toISOString();
  const observation={track_id:7,state:'DROWNING',confidence:1,confirmed:true,frame_id:1,captured_at};
  const context=vm.createContext({document:{getElementById:el},location:{search:'?site=chunjeon'},
    window:{addEventListener(){}},URLSearchParams,AbortController,Date,Number,
    pauseSim(){},updateSimControls(){},dgGetSession:()=>({token:'user-token'}),
    Image:class{naturalWidth=640;naturalHeight=480;async decode(){}},
    setTimeout(fn,delay){const id=++nextTimer;timers.set(id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);},
    dgApi:async(path,options)=>{
      calls.push({path,options});
      if(error)throw new Error('HTTP 404');
      if(missing && path.startsWith('/vision/edge/')){const error=new Error('No telemetry');error.status=404;throw error;}
      if(deferred)return await new Promise(resolve=>{pending.push(resolve);});
      if(path.startsWith('/edge/pose'))return {pose:{timestamp:new Date(Date.now()-(stalePose?1000:50)).toISOString(),
        x:.15,y:.2,heading:90,unit:'m',tracking_valid:!stalePose,status:stalePose?'stale_frame':'tracked'}};
      if(poseOnly)throw new Error('No judgement');
      if(path.includes('/frames/'))return {frame_id:mismatch?2:1,session_id:'session',captured_at,image_base64:'jpeg'};
      return source==='deployed'?{observation,expired}:{analysis:observation,session_id:'session'};
    }});
  vm.runInContext(readFileSync('code/js/edge-camera.js','utf8'),context);
  el('edgeConnectBtn').click();for(let i=0;i<30;i++)await Promise.resolve();
  return {el,calls,timers,context,resolve:()=>pending.forEach(resolve=>resolve({observation}))};
}
const direct=await scenario();
assert.match(direct.calls[0].path,/^\/edge\/latest\?site_id=chunjeon&camera_id=camera-01$/);
assert.match(direct.el('edgeDetails').textContent,/익수 점수 미제공/);
assert.match(direct.el('edgeDetails').textContent,/15프레임 검증 미실시/);
assert.match(direct.el('edgeStatus').textContent,/명령 미발행/);
assert.equal(direct.el('cameraConnectBtn').disabled,true);
assert.equal(direct.context.window.dgCameraLive,true);
direct.el('edgeDisconnectBtn').click();assert.equal(direct.timers.size,0);
assert.equal(direct.el('cameraConnectBtn').disabled,false);
assert.equal(direct.context.window.dgCameraLive,false);
const expired=await scenario({source:'hybrid',expired:true});
assert.equal(expired.calls.length,1);assert.equal(expired.el('edgePreview').hidden,true);
assert.match(expired.el('edgeStatus').textContent,/오래/);
const hybrid=await scenario({source:'hybrid'});
assert.match(hybrid.calls[1].path,/\/frames\/1.*session_id=session/);
assert.equal(hybrid.el('edgePreview').hidden,false);
const mismatched=await scenario({source:'hybrid',mismatch:true});
assert.equal(mismatched.el('edgePreview').hidden,true);
assert.match(mismatched.el('edgeStatus').textContent,/일치하지/);
const failed=await scenario({error:true});
assert.match(failed.el('edgeStatus').textContent,/HTTP 404/);
assert.equal(failed.el('edgePreview').hidden,true);
const disconnected=await scenario({deferred:true});disconnected.el('edgeDisconnectBtn').click();
disconnected.resolve();for(let i=0;i<20;i++)await Promise.resolve();
assert.equal(disconnected.el('edgeStatus').textContent,'로컬 AI 결과 수신 종료');
assert.equal(disconnected.timers.size,0);
const poseOnly=await scenario({poseOnly:true});
assert.match(poseOnly.el('edgePoseDetails').textContent,/X 0.150 m/);
assert.match(poseOnly.el('edgeDetails').textContent,/PC/);
const expiry=[...poseOnly.timers.values()].find(timer=>timer.delay<=250);
assert.ok(expiry);expiry.fn();
assert.match(poseOnly.el('edgePoseDetails').textContent,/관측 만료/);
const stalePose=await scenario({stalePose:true});
assert.match(stalePose.el('edgePoseDetails').textContent,/사용 불가/);
assert.doesNotMatch(stalePose.el('edgePoseDetails').textContent,/X 0.150/);
console.log('Edge viewer: route selection, stale frames, score semantics, frame matching, errors and cancellation passed');

const missing=await scenario({source:'hybrid',missing:true});
assert.equal(missing.el('edgeBrowserConnectBtn').hidden,false);
assert.match(missing.el('edgeStatus').textContent,/별도 PC.*없습니다/);
let submitted=0;missing.el('cameraForm').requestSubmit=()=>submitted++;
missing.el('edgeBrowserConnectBtn').click();
assert.equal(submitted,1);assert.equal(missing.el('cameraConnectBtn').disabled,false);
assert.equal(missing.el('edgeBrowserConnectBtn').hidden,true);
assert.equal(missing.timers.size,0);
