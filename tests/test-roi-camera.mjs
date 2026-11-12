import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const elements=new Map(), resizeCallbacks=[];
function el(id){
  if(!elements.has(id)){
    const properties=new Map(), classes=new Set();
    elements.set(id,{hidden:true,disabled:true,textContent:'',handlers:{},srcObject:null,
      style:{setProperty:(k,v)=>properties.set(k,v),removeProperty:k=>properties.delete(k),properties},
      classList:{toggle(k,value){value?classes.add(k):classes.delete(k);},contains:k=>classes.has(k)},
      addEventListener(event,fn){this.handlers[event]=fn;},async play(){this.playing=true;},pause(){this.playing=false;}});
  }
  return elements.get(id);
}
const source=el('localCameraFeed');source.videoWidth=1280;source.videoHeight=720;
const panel=el('videoPanel');panel.clientWidth=800;panel.clientHeight=600;
let stopped=0, acquired=0;
const stream={getTracks:()=>[{stop(){stopped++;}}]};
const context=vm.createContext({document:{getElementById:el},window:{addEventListener(){}},
  navigator:{mediaDevices:{getUserMedia(){acquired++;throw new Error('Do not acquire a second camera');}}},
  ResizeObserver:class{constructor(fn){resizeCallbacks.push(fn);}observe(){}},Math,Boolean});
vm.runInContext(readFileSync('code/js/roi-camera.js','utf8'),context);
context.window.dgSyncRoiCamera(stream);await Promise.resolve();
assert.equal(el('roiCameraFeed').srcObject,stream);
assert.equal(el('roiCameraFeed').hidden,false);
assert.equal(el('roiEditor').classList.contains('has-camera'),true);
assert.equal(el('roiEditor').style.properties.get('--roi-camera-aspect'),'1280 / 720');
assert.equal(el('roiSvgControl').style.top,'75px');
assert.equal(el('roiSvgControl').style.width,'800px');
assert.equal(el('roiSvgControl').style.height,'450px');
source.videoWidth=720;source.videoHeight=1280;source.handlers.resize();
assert.equal(el('roiSvgControl').style.left,'231.25px');
assert.equal(el('roiSvgControl').style.width,'337.5px');
assert.equal(el('roiSvgControl').style.height,'600px');
context.window.dgSyncRoiCamera(null);
assert.equal(el('roiCameraFeed').srcObject,null);
assert.equal(el('roiCameraFeed').hidden,true);
assert.equal(el('roiCameraFeed').playing,false);
assert.equal(el('roiEditor').classList.contains('has-camera'),false);
assert.equal(el('roiEditor').style.properties.has('--roi-camera-aspect'),false);
assert.equal(el('roiSvgControl').style.inset,'0');
assert.equal(stopped,0,'ROI preview must never stop shared tracks');
assert.equal(acquired,0,'ROI preview reuses the camera stream');
console.log('ROI live preview: shared stream, landscape/portrait letterboxing and disconnect cleanup passed');
