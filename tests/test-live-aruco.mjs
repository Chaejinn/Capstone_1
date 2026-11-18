import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const nodes=new Map(),frames=new Map(),timers=new Map(),workers=[];let clock=1000,id=0;
const drawing={clearRect(){},drawImage(){},getImageData(){return {data:new Uint8ClampedArray(640*360*4)};},beginPath(){},moveTo(){},lineTo(){},stroke(){},setLineDash(){}};
function el(key){
 if(!nodes.has(key))nodes.set(key,{hidden:false,style:{},textContent:'',clientWidth:1000,clientHeight:700,videoWidth:1280,videoHeight:720,readyState:4,currentTime:1,
  getContext(){return drawing;},addEventListener(){}});
 return nodes.get(key);
}
const context=vm.createContext({document:{currentScript:{src:'https://example.test/js/live-aruco.js'},hidden:false,getElementById:el,createElement:()=>el('capture'),addEventListener(){}},
 window:{dgCameraLive:true,addEventListener(){},dgDrawMarker(){}},performance:{now:()=>clock},Date,Math,Number,JSON,URL,Uint8ClampedArray,
 ResizeObserver:class{observe(){}},Worker:class{constructor(){workers.push(this);this.messages=[];}postMessage(m){this.messages.push(m);}terminate(){this.terminated=true;}},
 requestAnimationFrame(fn){const key=++id;frames.set(key,fn);return key;},cancelAnimationFrame(key){frames.delete(key);},
 setTimeout(fn,ms){const key=++id;timers.set(key,{fn,ms});return key;},clearTimeout(key){timers.delete(key);}});
vm.runInContext(readFileSync('code/js/live-aruco-math.js','utf8'),context);
vm.runInContext(readFileSync('code/js/live-aruco.js','utf8'),context);
const configuration={revision:7,aruco:{enabled:true,dictionary:'DICT_4X4_50',marker_id:0},homography:{enabled:true,frame_id:'water'},homography_matrix:[[.01,0,0],[0,-.01,1],[0,0,1]]};
context.window.dgSetLiveArucoConfiguration(configuration);context.window.dgSyncLiveAruco({});
context.window.dgUpdateLiveTargets({configuration_revision:7,captured_at:new Date(Date.now()-3000).toISOString(),detections:[{track_id:8,confirmed:true,coordinate_valid:true,coordinate_frame:'water',target_x_m:.8,target_y_m:.9}]});
const worker=workers.at(-1);frames.values().next().value(clock);
assert.equal(worker.messages.length,1);const sent=worker.messages[0];
const marker={detected:true,marker_id:0,coordinate_valid:true,x_m:.5,y_m:.5,corners_px:[[250,150],[350,150],[350,250],[250,250]],center_px:[300,200]};
function result(change={}){worker.onmessage({data:{token:sent.token,capturedAt:clock,width:640,height:360,marker,...change}});}
result();
assert.equal(el('liveMarkerOverlay').hidden,false);assert.match(el('liveMarkerReadout').textContent,/0.50 m/);
assert.match(el('liveMarkerReadout').textContent,/익수자 좌표 3/);assert.equal(el('statDist').textContent,'0.50 m');
clock+=100;frames.values().next().value(clock);
assert.equal(worker.messages.length,1,'A frozen video frame is not relabelled as a fresh observation');
const expiry=[...timers.values()][0];assert.ok(expiry.ms<=200);expiry.fn();
assert.equal(el('liveMarkerOverlay').hidden,true);assert.equal(context.window.dgLiveDistance,null);
result({capturedAt:clock-201});assert.equal(el('liveMarkerOverlay').hidden,true,'Stale worker observation must never be overlaid');
result({marker:{detected:false}});assert.equal(el('statDist').textContent,'— m');
context.window.dgUpdateLiveTargets(null);result();assert.doesNotMatch(el('liveMarkerReadout').textContent,/익수자 ID/);assert.equal(context.window.dgLiveDistance,null);
context.window.dgSyncLiveAruco(null);assert.equal(worker.terminated,true);assert.equal(el('liveMarkerReadout').hidden,true);
result();assert.equal(el('liveMarkerOverlay').hidden,true,'Closed stream ignores worker replies');
console.log('Live ArUco shared video, worker lifecycle, distance HUD, stale expiry, target clearing and disconnect passed');
