/* Display-only geometry. These observations never authorize a command. */
(function(root){
  function project(matrix,p){
    const z=matrix[2][0]*p[0]+matrix[2][1]*p[1]+matrix[2][2];
    if(!Number.isFinite(z)||Math.abs(z)<1e-12)return null;
    const q=[(matrix[0][0]*p[0]+matrix[0][1]*p[1]+matrix[0][2])/z,(matrix[1][0]*p[0]+matrix[1][1]*p[1]+matrix[1][2])/z];
    return q.every(Number.isFinite)?q:null;
  }
  function inverse(m){
    const [[a,b,c],[d,e,f],[g,h,i]]=m;
    const n=[[e*i-f*h,c*h-b*i,b*f-c*e],[f*g-d*i,a*i-c*g,c*d-a*f],[d*h-e*g,b*g-a*h,a*e-b*d]];
    const det=a*n[0][0]+b*n[1][0]+c*n[2][0];
    return Number.isFinite(det)&&Math.abs(det)>1e-15?n.map(row=>row.map(x=>x/det)):null;
  }
  function inside(point,polygon){
    const [x,y]=point;let hit=false;
    for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
      const a=polygon[j],b=polygon[i],cross=(x-a.x)*(b.y-a.y)-(y-a.y)*(b.x-a.x);
      if(Math.abs(cross)<1e-8&&x>=Math.min(a.x,b.x)-1e-8&&x<=Math.max(a.x,b.x)+1e-8&&y>=Math.min(a.y,b.y)-1e-8&&y<=Math.max(a.y,b.y)+1e-8)return true;
      if((a.y>y)!==(b.y>y)&&x<(b.x-a.x)*(y-a.y)/(b.y-a.y)+a.x)hit=!hit;
    }return hit;
  }
  function locate(markers,configuration,width,height){
    const a=configuration.aruco,h=configuration.homography;
    const selected=markers.filter(marker=>marker.id===a.marker_id);
    if(selected.length!==1)return {detected:false,coordinate_status:selected.length?'AMBIGUOUS_MARKER':'MARKER_NOT_FOUND'};
    const p=selected[0].corners.map(v=>[v.x,v.y]),center=p.reduce((sum,v)=>[sum[0]+v[0]/4,sum[1]+v[1]/4],[0,0]);
    const out={detected:true,marker_id:a.marker_id,corners_px:p,center_px:center,coordinate_valid:false,coordinate_status:'UNCALIBRATED',heading_measured:a.heading_measured,heading_deg:null};
    if(!h?.enabled||!configuration.homography_matrix||!h.image_size)return out;
    if(Math.abs((width/height)/(h.image_size[0]/h.image_size[1])-1)>.01){out.coordinate_status='IMAGE_ASPECT_MISMATCH';return out;}
    const percent=p.map(v=>[v[0]/width*100,v[1]/height*100]);
    if(percent.some(v=>!inside(v,h.image_points.slice(0,4)))){out.coordinate_status='OUTSIDE_CALIBRATION';return out;}
    const matrix=configuration.homography_matrix,world=percent.map(v=>project(matrix,v));
    if(world.some(v=>!v)){out.coordinate_status='INVALID_PROJECTION';return out;}
    const mean=world.reduce((sum,v)=>[sum[0]+v[0]/4,sum[1]+v[1]/4],[0,0]);
    Object.assign(out,{x_m:mean[0],y_m:mean[1],coordinate_valid:true,coordinate_status:'VALID'});
    if(a.heading_measured&&Number.isFinite(a.heading_offset_deg)){
      const forward=[(world[0][0]+world[1][0])/2-mean[0],(world[0][1]+world[1][1])/2-mean[1]];
      const angle=Math.atan2(forward[1],forward[0])+a.heading_offset_deg*Math.PI/180;
      out.heading_deg=(angle*180/Math.PI%360+360)%360;
      const back=inverse(matrix),length=Math.hypot(...forward);
      const tip=back&&project(back,[mean[0]+Math.cos(angle)*length,mean[1]+Math.sin(angle)*length]);
      if(tip)out.board_front_px=[tip[0]/100*width,tip[1]/100*height];
    }return out;
  }
  function distances(marker,packet,configuration,now){
    if(!marker?.coordinate_valid||!packet||packet.configuration_revision!==configuration.revision)return [];
    const age=(now-Date.parse(packet.captured_at))/1000;
    // Informational display only. The target is explicitly labelled with its age.
    // Control freshness rules remain in the trusted server; no output feeds control.
    if(!Number.isFinite(age)||age<0||age>10)return [];
    const back=inverse(configuration.homography_matrix);if(!back)return [];
    return (packet.detections||[]).filter(d=>d.confirmed===true&&d.coordinate_valid===true&&
      Number.isFinite(d.target_x_m)&&Number.isFinite(d.target_y_m)&&d.coordinate_frame===configuration.homography.frame_id)
      .map(d=>({track_id:d.track_id,generation:d.track_generation??0,age,
        distance_m:Math.hypot(marker.x_m-d.target_x_m,marker.y_m-d.target_y_m),
        target_percent:project(back,[d.target_x_m,d.target_y_m])}))
      .filter(d=>d.target_percent).sort((a,b)=>a.distance_m-b.distance_m);
  }
  root.DgLiveArucoMath={project,inverse,inside,locate,distances};
})(typeof self==='undefined'?globalThis:self);
