import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const c=vm.createContext({});
vm.runInContext(readFileSync('code/js/live-aruco-math.js','utf8'),c);
const math=c.DgLiveArucoMath;
const conf={revision:7,aruco:{marker_id:0,heading_measured:true,heading_offset_deg:0},
  homography:{enabled:true,image_size:[1000,1000],frame_id:'water',image_points:[{x:0,y:0},{x:100,y:0},{x:100,y:100},{x:0,y:100}]},
  homography_matrix:[[.01,0,0],[0,-.01,1],[0,0,1]]};
const corners=[{x:45,y:45},{x:55,y:45},{x:55,y:55},{x:45,y:55}];
const board=math.locate([{id:0,corners}],conf,100,100);
assert.equal(board.coordinate_valid,true);assert.equal(board.heading_deg,90);
assert.ok(Math.abs(board.x_m-.5)<1e-8);assert.ok(Math.abs(board.y_m-.5)<1e-8);
assert.ok(board.board_front_px[1]<board.center_px[1]);
const now=Date.now(),packet={configuration_revision:7,captured_at:new Date(now-3000).toISOString(),detections:[
  {track_id:8,confirmed:true,coordinate_valid:true,coordinate_frame:'water',target_x_m:.8,target_y_m:.9}]};
const distance=math.distances(board,packet,conf,now);
assert.equal(distance.length,1);assert.ok(Math.abs(distance[0].distance_m-.5)<1e-8);assert.equal(distance[0].age,3);
assert.equal(math.distances(board,packet,conf,now+8000).length,0,'Expired target clears distance');
assert.equal(math.distances(board,{...packet,configuration_revision:8},conf,now).length,0);
assert.equal(math.distances(board,{...packet,detections:[{...packet.detections[0],confirmed:false}]},conf,now).length,0);
assert.equal(math.distances({...board,coordinate_valid:false},packet,conf,now).length,0);
assert.equal(math.locate([{id:0,corners},{id:0,corners}],conf,100,100).coordinate_status,'AMBIGUOUS_MARKER');
assert.equal(math.locate([{id:1,corners}],conf,100,100).detected,false);
assert.equal(math.locate([{id:0,corners}],conf,100,200).coordinate_status,'IMAGE_ASPECT_MISMATCH');
assert.equal(math.locate([{id:0,corners}],{...conf,homography:{enabled:false}},100,100).coordinate_valid,false);
console.log('Live marker geometry, 0.5 m distance, target age/revision, ambiguity and calibration guards passed');
