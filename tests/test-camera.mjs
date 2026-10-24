import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

async function scenario({result, error, deferredCamera=false}){
  const elements=new Map(), calls=[], drawings=[], timers=new Map();
  let stopped=false, pendingCamera;
  const context2d={clearRect(){drawings.length=0;},drawImage(){},strokeRect(...args){drawings.push(args);},fillText(){}};
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
    window:{addEventListener(){}},navigator:{mediaDevices:{getUserMedia:()=>deferredCamera?new Promise(resolve=>{pendingCamera=resolve;}):Promise.resolve(stream)}},
    updateSimControls(){},pauseSim(){},dgGetSession:()=>({id:'operator'}),
    dgApi:async(path,options)=>{calls.push({path,options});if(error)throw new Error(error);return result;},
    AbortController,FormData,Blob,Number,Math,
    setTimeout(fn,delay){const id=timers.size+1;timers.set(id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);}});
  vm.runInContext(readFileSync('code/js/camera.js','utf8'),context);
  const start=element('cameraForm').handlers.submit({preventDefault(){}});
  if(deferredCamera){element('cameraDisconnectBtn').handlers.click();pendingCamera(stream);}
  await start;
  for(let i=0;i<10;i++)await Promise.resolve();
  return {elements,calls,drawings,timers,track,stopped:()=>stopped,disconnect:()=>element('cameraDisconnectBtn').handlers.click()};
}
const live=await scenario({result:{image_size:[640,480],detections:[{bbox:[10,20,110,120],water_state:'DROWNING',confidence:0.8}]}});
assert.equal(live.calls[0].path,'/camera/analyze');
assert.ok(live.calls[0].options.body.get('image') instanceof Blob);
assert.equal(live.elements.get('cameraBadge').textContent,'AI LIVE');
assert.deepEqual(live.drawings[0],[10,20,100,100]);
assert.equal(live.calls.length,1,'Only one inference request runs at a time');
live.disconnect();assert.ok(live.stopped());assert.equal(live.elements.get('cameraOverlay').hidden,true);assert.equal(live.timers.size,0);
const empty=await scenario({result:{image_size:[640,480],detections:[]}});
assert.match(empty.elements.get('cameraStatus').textContent,/대상 없음/);empty.disconnect();
const failed=await scenario({error:'upstream unavailable'});
assert.match(failed.elements.get('cameraStatus').textContent,/upstream unavailable/);
assert.equal(failed.elements.get('cameraBadge').textContent,'AI 연결 대기');failed.disconnect();
const canceled=await scenario({deferredCamera:true});
assert.ok(canceled.stopped());assert.equal(canceled.calls.length,0,'Canceled camera permission must not start inference');
console.log('Camera inference, boxes, empty results, errors, disconnect, and permission cancellation passed');
