/* Fixture path is produced by OpenCV, not by the detector being tested. */
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const c=vm.createContext({});
for(const path of ['cv.js','aruco.js','opencv-dictionaries.js'])vm.runInContext(readFileSync('code/js/vendor/js-aruco2/'+path,'utf8'),c);
const fixtures=JSON.parse(readFileSync(process.argv[2]||join(tmpdir(),'dg-live-marker-fixtures.json'),'utf8'));
const started=performance.now();
for(const f of fixtures){
 const detector=new c.AR.Detector({dictionaryName:f.dictionary,maxHammingDistance:1});
 const found=detector.detect({width:f.width,height:f.height,data:new Uint8ClampedArray(Buffer.from(f.rgba,'base64'))});
 assert.equal(found.length,1,`${f.dictionary}/${f.id}/${f.rotation}`);assert.equal(found[0].id,f.id);
 found[0].corners.forEach((p,i)=>assert.ok(Math.hypot(p.x-f.expected_corners[i][0],p.y-f.expected_corners[i][1])<3,'Front orientation must match OpenCV'));
}
console.log(`${fixtures.length} OpenCV-generated dictionary/id/rotation cases passed in ${(performance.now()-started).toFixed(1)} ms`);
