import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

async function scenario(protocol, address){
  const elements = new Map();
  const element = id => {
    if(!elements.has(id)) elements.set(id, {value:'', hidden:false, disabled:false,
      classList:{add(){},remove(){}}, handlers:{},
      addEventListener(type, fn){this.handlers[type]=fn;}, removeAttribute(){}});
    return elements.get(id);
  };
  const storage = new Map(), calls = [];
  const jpeg = new Uint8Array([255,216,1,2,255,217]);
  const header = new TextEncoder().encode(`--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${jpeg.length}\r\n\r\n`);
  const packet = new Uint8Array(header.length + jpeg.length + 2);
  packet.set(header); packet.set(jpeg, header.length); packet.set([13,10], packet.length-2);
  let reads = 0, sawLive = false;
  const reader = {async read(){
    reads++;
    if(reads === 1) return {value:packet.slice(0,10),done:false};
    if(reads === 2) return {value:packet.slice(10),done:false};
    sawLive = element('cameraBadge').textContent === 'AI LIVE';
    return {done:true};
  }, async cancel(){}, releaseLock(){}};
  const context = vm.createContext({document:{getElementById:element},
    window:{addEventListener(){}}, location:{protocol, search:'?site=chunjeon'},
    localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
    dgGetSession:()=>({id:'operator'}),updateSimControls(){},pauseSim(){},
    URL,URLSearchParams,AbortController,TextDecoder,Uint8Array,Blob,setTimeout,clearTimeout,
    fetch:async(url, options)=>{calls.push({url,options});return {ok:true,
      headers:new Headers({'content-type':'multipart/x-mixed-replace; boundary=frame'}),body:{getReader:()=>reader}};}
  });
  vm.runInContext(readFileSync('code/js/camera.js','utf8'), context);
  element('cameraServer').value = address;
  element('cameraPassword').value = 'private-stream-key';
  await element('cameraForm').handlers.submit({preventDefault(){}});
  return {elements,storage,calls,sawLive};
}

const model = await scenario('https:', 'https://camera.test');
assert.equal(model.calls.length, 1);
assert.equal(model.calls[0].url, 'https://camera.test/stream');
assert.equal(model.calls[0].options.headers.Authorization, 'Bearer private-stream-key');
assert.equal(model.elements.get('cameraPassword').value, '');
assert.ok(![...model.storage.values()].join('').includes('private-stream-key'));
assert.ok(model.sawLive, 'Split MJPEG packets render the AI video');
assert.match(model.elements.get('cameraStatus').textContent, /終了|종료/);
assert.equal(model.elements.get('cameraFeed').hidden, true);
const mixed = await scenario('https:', 'http://camera.test');
assert.equal(mixed.calls.length, 0);
assert.match(mixed.elements.get('cameraStatus').textContent, /HTTPS/);
console.log('AI video connection, split frames, disconnect, and HTTPS checks passed');
