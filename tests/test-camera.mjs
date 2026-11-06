import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

async function scenario({result, error, deferredCamera=false}){
  const elements=new Map(), calls=[], drawings=[], texts=[], timers=new Map(), intervals=new Map();
  let stopped=false, pendingCamera;
  const context2d={clearRect(){drawings.length=0;},drawImage(){},strokeRect(...args){drawings.push(args);},fillText(text){texts.push(text);}};
  function element(id){
    if(!elements.has(id)) elements.set(id,{hidden:true,disabled:false,textContent:'',width:640,height:480,
      videoWidth:640,videoHeight:480,handlers:{},classList:{add(){},remove(){}},
      addEventListener(type,fn){this.handlers[type]=fn;},getContext(){return context2d;},
      pause(){},async play(){},toBlob(fn){fn(new Blob(['jpeg'],{type:'image/jpeg'}));}});
    return elements.get(id);
  }
  const track={stop(){stopped=true;},onended:null};
  const stream={getTracks:()=>[track],getVideoTracks:()=>[track]};
  const context=vm.createContext({document:{getElementById:element,createElement:()=>element('capture')},
    window:{addEventListener(){},location:{search:"?site=chunjeon"}},navigator:{mediaDevices:{getUserMedia:()=>deferredCamera?new Promise(resolve=>{pendingCamera=resolve;}):Promise.resolve(stream)}},
    updateSimControls(){},pauseSim(){},dgGetSession:()=>({id:'operator'}),
    dgApi:async(path,options={})=>{
      calls.push({path,options});
      if(path.startsWith('/vision/streams?')) return {stream_id:'session-one'};
      if(path.includes('/results')){if(error)throw new Error(error);return {analysis:{...result,frame_id:1}};}
      return {};
    },
    AbortController,FormData,Blob,Number,Math,URLSearchParams,
    setTimeout(fn,delay){const id=timers.size+1;timers.set(id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);},setInterval(fn,delay){const id=intervals.size+1;intervals.set(id,{fn,delay});return id;},clearInterval(id){intervals.delete(id);}});
  vm.runInContext(readFileSync('code/js/camera.js','utf8'),context);
  const start=element('cameraForm').handlers.submit({preventDefault(){}});
  if(deferredCamera){element('cameraDisconnectBtn').handlers.click();pendingCamera(stream);}
  await start;
  for(let i=0;i<40;i++)await Promise.resolve();
  return {elements,calls,drawings,texts,timers,intervals,track,stopped:()=>stopped,disconnect:()=>element('cameraDisconnectBtn').handlers.click()};
}
const live=await scenario({result:{image_size:[640,480],detections:[{bbox:[10,20,110,120],water_state:'DROWNING',confidence:0.8,track_id:42}]}});
assert.equal(live.calls[0].path,'/vision/streams?site_id=chunjeon');
assert.match(live.calls[1].path,/session-one\/frames/);
assert.ok(live.texts.some(text=>text.includes('ID 0-42')));
assert.ok(live.texts.some(text=>text.includes('연속 0/15')));
assert.ok(live.calls[1].options.body.get('image') instanceof Blob);
assert.equal(live.elements.get('cameraBadge').textContent,'CAM LIVE');
assert.equal(live.elements.get('localCameraFeed').hidden,false);
assert.equal(live.elements.get('aiResultPanel').hidden,false);
assert.equal(live.elements.get('aiResultPlaceholder').hidden,true);
assert.match(live.elements.get('aiResultInfo').textContent,/촬영.*초 전.*분석/);
assert.deepEqual(live.drawings[0],[10,20,100,100]);
assert.equal(live.calls.length,3,'Create, upload and poll run sequentially');
const refresh=[...live.timers.values()].find(t=>t.delay===1000);
assert.ok(refresh);for(const [id,t] of live.timers){if(t===refresh)live.timers.delete(id);}refresh.fn();
for(let i=0;i<40;i++)await Promise.resolve();
assert.equal(live.elements.get('localCameraFeed').hidden,false,'Live video stays visible during another inference');
assert.equal(live.elements.get('cameraOverlay').hidden,false,'Last analyzed image stays visible while next analysis runs');
live.disconnect();assert.equal(live.intervals.size,0);assert.equal(live.elements.get('aiResultPanel').hidden,true);assert.equal(live.calls.at(-1).options.method,'DELETE');assert.ok(live.stopped());assert.equal(live.elements.get('cameraOverlay').hidden,true);assert.equal(live.timers.size,0);
const empty=await scenario({result:{image_size:[640,480],detections:[]}});
assert.match(empty.elements.get('cameraStatus').textContent,/대상 없음/);empty.disconnect();
const failed=await scenario({error:'upstream unavailable'});
assert.match(failed.elements.get('cameraStatus').textContent,/upstream unavailable/);
assert.equal(failed.elements.get('cameraBadge').textContent,'CAM LIVE');
assert.equal(failed.elements.get('localCameraFeed').hidden,false,'AI failure must not interrupt live video');failed.disconnect();
const canceled=await scenario({deferredCamera:true});
assert.ok(canceled.stopped());assert.equal(canceled.calls.length,0,'Canceled camera permission must not start inference');
console.log('Camera inference, boxes, empty results, errors, disconnect, and permission cancellation passed');
