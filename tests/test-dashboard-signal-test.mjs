import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const elements=new Map(),calls=[],timers=new Map(),observers=[];let next=0;
function el(id){
 if(!elements.has(id))elements.set(id,{id,value:'',hidden:false,disabled:false,children:[],handlers:{},
  addEventListener(type,fn){this.handlers[type]=fn;},
  appendChild(child){if(child.parentElement)child.parentElement.children=child.parentElement.children.filter(c=>c!==child);this.children.push(child);child.parentElement=this;},
  prepend(child){this.children.unshift(child);},get lastChild(){return this.children.at(-1);}});
 return elements.get(id);
}
const commands=['DISPATCH','ESTOP','CLEAR_ESTOP','CANCEL','DEPLOY','RETURN','COMPLETE','RESET'];
const buttons=commands.map(cmd=>Object.assign(el(cmd),{dataset:{signalCommand:cmd}}));
el('view-control').hidden=true;el('signalBridgeMode').value='usb';el('signalTargetX').value='5';el('signalTargetY').value='0';
const context=vm.createContext({document:{getElementById:el,querySelectorAll:()=>buttons,createElement:()=>el('record-'+next++)},window:{dgCameraLive:false,addEventListener(){}},
 location:{search:'?site=chunjeon'},URLSearchParams,AbortController,Date,Number,Promise,JSON,
 MutationObserver:class{constructor(fn){observers.push(fn);}observe(){}},
 setTimeout(fn,ms){const key=++next;timers.set(key,{fn,ms});return key;},clearTimeout(key){timers.delete(key);},
 dgApi:async(path,options={})=>{
  calls.push({path,options});
  if(path.startsWith('/board-control/status'))return {connected:true,last_command:'STOP',revision:1};
  if(path.startsWith('/test-signals'))return {signals:[],cursor:1};
  if(path==='/test-control/auto')return {running:false,available:false};
  if(path.startsWith('/test-control?'))return {state:{status:'IDLE',estop:false}};
  return {status:'ISSUED'};
 }});
vm.runInContext(readFileSync('code/js/dashboard-signal-test.js','utf8'),context);
const flush=async()=>{for(let i=0;i<50;i++)await Promise.resolve();};
assert.equal(calls.length,0);assert.equal(el('dashboardSignalTest').parentElement,el('signalSideHost'));
context.window.dgCameraLive=true;context.window.dgPlaceSignalTest();
assert.equal(el('dashboardSignalTest').parentElement,el('signalWideHost'));assert.equal(el('signalSideHost').hidden,true);
el('view-control').hidden=false;observers[0]();await flush();
assert.ok(calls.every(c=>!c.options.method),'Opening the dashboard is read-only');
assert.equal(el('DISPATCH').disabled,false);assert.equal(el('DEPLOY').disabled,true,'USB does not pretend to support net deployment');
el('DISPATCH').handlers.click();await flush();
assert.ok(calls.some(c=>c.path==='/board-control/simulate?site_id=chunjeon'&&c.options.method==='POST'));
el('signalBridgeMode').value='hc06';el('signalBridgeMode').handlers.change();await flush();
el('RETURN').handlers.click();await flush();
assert.ok(calls.some(c=>c.path==='/test-control'&&c.options.body?.command==='RETURN'));
await context.window.dgStopSignalTest();
assert.ok(calls.some(c=>c.path==='/test-control'&&c.options.body?.command==='ESTOP'));
assert.ok(!calls.some(c=>c.path.includes('/auto/start')),'No random automation is started');
el('view-control').hidden=true;observers[0]();await flush();assert.equal(timers.size,0);
console.log('Dashboard signal panel placement, manual USB/HC-06 routing, read-only startup and stop passed');
