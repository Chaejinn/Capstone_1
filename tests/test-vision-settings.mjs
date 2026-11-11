import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const elements=new Map(), calls=[];let restarts=0,stops=0;
const ctx={drawImage(){},strokeRect(){},beginPath(){},moveTo(){},lineTo(){},closePath(){},stroke(){},fillText(){}};
function element(id){
  if(!elements.has(id))elements.set(id,{value:'',checked:false,hidden:true,disabled:false,style:{setProperty(){}},handlers:{},children:[],
    addEventListener(type,fn){this.handlers[type]=fn;},appendChild(child){this.children.push(child);},replaceChildren(){this.children=[];},
    setAttribute(name,value){this[name]=value;},getBoundingClientRect(){return {left:0,top:0,width:800,height:450};},
    async play(){},pause(){},getContext(){return ctx;},toBlob(fn){fn(new Blob(['jpeg'],{type:'image/jpeg'}));}});
  const node=elements.get(id);
  if(!Object.getOwnPropertyDescriptor(node,'value').get){
    let value=String(node.value);
    Object.defineProperty(node,'value',{get:()=>value,set:v=>{value=String(v);},configurable:true});
  }
  return node;
}
element('localCameraFeed').videoWidth=1280;element('localCameraFeed').videoHeight=720;
let settings={revision:0,homography:{enabled:false,image_points:[],image_size:null,pool_width_m:null,pool_height_m:null,frame_id:'pool-01'},
  aruco:{enabled:false,dictionary:'DICT_4X4_50',marker_id:0,marker_size_m:.05,heading_offset_deg:null,heading_measured:false}};
const context=vm.createContext({document:{getElementById:element,createElement:()=>element('capture'),
  createElementNS:()=>({setAttribute(){},addEventListener(){}}),addEventListener(){},removeEventListener(){}},
  window:{dgRestartCameraTracking(){restarts++;}},location:{search:'?site=chunjeon'},dgGetSession:()=>({role:'admin'}),
  URLSearchParams,Math,Number,Boolean,Date,Blob,FormData,
  dgApi:async(path,options={})=>{
    calls.push({path,options});
    if(options.method==='PUT'){
      const part=path.includes('/homography')?'homography':'aruco';
      settings={...settings,revision:settings.revision+1,[part]:structuredClone(options.body)};
    }
    if(path.includes('/aruco/marker'))return {image_base64:'png',dictionary:'DICT_4X4_50',marker_id:3};
    if(path.includes('/inspect'))return {image_size:[960,540],configuration_revision:settings.revision,
      marker_observation:{enabled:true,detected:true,marker_id:3,corners_px:[[1,1],[2,1],[2,2],[1,2]],coordinate_valid:false,coordinate_status:'UNCALIBRATED'}};
    return structuredClone(settings);
  }});
vm.runInContext(readFileSync('code/js/vision-settings.js','utf8'),context);
const flush=async()=>{for(let i=0;i<40;i++)await Promise.resolve();};await flush();
const stream={getTracks:()=>[{stop(){stops++;}}]};context.window.dgSyncVisionCamera(stream);
assert.equal(element('homographyCameraFeed').srcObject,stream);
element('homographyPickBtn').handlers.click();
for(const [clientX,clientY] of [[80,45],[720,45],[720,405],[80,405]])element('homographySvg').handlers.click({clientX,clientY});
assert.match(element('homographyPointCount').textContent,/4 \/ 4/);
element('poolWidth').value='.8';element('poolHeight').value='.8';element('homographyEnabled').checked=true;
element('arucoId').value='3';
element('homographySaveBtn').handlers.click();await flush();
assert.equal(restarts,1);assert.equal(element('arucoId').value,'3','Saving homography preserves unsaved marker inputs');
const saved=calls.find(call=>call.path.includes('/configuration/homography'));
assert.equal(saved.options.body.image_points[0].x,10);assert.equal(saved.options.body.image_points[0].y,10);
assert.equal(saved.options.body.image_size[0],1280);assert.equal(saved.options.body.pool_width_m,.8);
context.window.dgReportVisionApplied(1);assert.match(element('cameraConfigurationStatus').textContent,/적용 확인/);
element('arucoEnabled').checked=true;element('arucoDictionary').value='DICT_4X4_50';element('arucoSize').value='5';
element('arucoSaveBtn').handlers.click();await flush();assert.equal(restarts,2);
const marker=calls.find(call=>call.path.includes('/configuration/aruco'));
assert.equal(marker.options.body.marker_size_m,.05);assert.equal(marker.options.body.heading_offset_deg,null);
assert.equal(settings.homography.enabled,true);
await element('arucoImageBtn').handlers.click();assert.equal(element('arucoMarkerImage').hidden,false);
await element('arucoInspectBtn').handlers.click();assert.equal(element('arucoInspection').hidden,false);
assert.match(element('arucoInspectionStatus').textContent,/마커 ID 3 검출/);
context.window.dgSyncVisionCamera(null);assert.equal(element('homographyCameraFeed').srcObject,null);assert.equal(stops,0);
console.log('Camera settings: live stream, four image points, independent saves, revision, marker preview and inspection passed');
