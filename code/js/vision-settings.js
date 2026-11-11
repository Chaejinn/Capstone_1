/* Independent settings; full-image percentages survive proportional upload resizing. */
(() => {
  const el=id=>document.getElementById(id);
  const site=new URLSearchParams(location.search).get('site');
  const query='?site_id='+encodeURIComponent(site||'');
  const video=el('homographyCameraFeed'), source=el('localCameraFeed'), svg=el('homographySvg');
  let current=null, points=[], imageSize=null, picking=false, revision=0, ready=false, appliedRevision=null;
  const admin=dgGetSession()?.role==='admin';
  const number=id=>el(id).value.trim()===''?null:Number(el(id).value);
  function render(){
    svg.replaceChildren();
    if(points.length>1){
      const shape=document.createElementNS('http://www.w3.org/2000/svg','polygon');
      shape.setAttribute('points',points.map(p=>`${p.x},${p.y}`).join(' '));
      shape.setAttribute('fill','rgba(45,217,196,.12)');shape.setAttribute('stroke','#2dd9c4');shape.setAttribute('stroke-width','.5');svg.appendChild(shape);
    }
    points.forEach((p,i)=>{
      const circle=document.createElementNS('http://www.w3.org/2000/svg','circle');
      circle.setAttribute('cx',p.x);circle.setAttribute('cy',p.y);circle.setAttribute('r','1.8');circle.setAttribute('fill','#ffd166');
      circle.addEventListener('pointerdown',event=>{
        if(!admin||!current||picking)return;event.preventDefault();event.stopPropagation();
        const move=e=>{points[i]=position(e);render();};
        const up=()=>{document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',up);document.removeEventListener('pointercancel',up);};
        document.addEventListener('pointermove',move);document.addEventListener('pointerup',up);document.addEventListener('pointercancel',up);
      });
      svg.appendChild(circle);
      const label=document.createElementNS('http://www.w3.org/2000/svg','text');
      label.setAttribute('x',p.x+2);label.setAttribute('y',Math.max(3,p.y-2));label.setAttribute('fill','#ffd166');label.setAttribute('font-size','3');label.textContent=String(i+1);svg.appendChild(label);
    });
    el('homographyPointCount').textContent=`${points.length} / 4점${picking?' · 순서대로 클릭하세요':''}`;
  }
  function position(e){
    const r=svg.getBoundingClientRect();
    return {x:Math.max(0,Math.min(100,(e.clientX-r.left)/r.width*100)),y:Math.max(0,Math.min(100,(e.clientY-r.top)/r.height*100))};
  }
  function dimensions(){
    if(current&&source.videoWidth&&source.videoHeight){
      el('homographyEditor').style.setProperty('--homography-aspect',`${source.videoWidth}/${source.videoHeight}`);
    }
  }
  window.dgSyncVisionCamera=stream=>{
    current=stream;video.hidden=!stream;el('homographyCameraHint').hidden=Boolean(stream);
    if(stream){video.srcObject=stream;void video.play().catch(()=>{el('homographyStatus').textContent='카메라 미리보기를 재생할 수 없습니다.';});dimensions();}
    else{video.pause();video.srcObject=null;picking=false;render();}
  };
  source.addEventListener('loadedmetadata',dimensions);source.addEventListener('resize',dimensions);
  svg.addEventListener('click',e=>{
    if(!picking||!current||!admin||points.length>=4)return;
    points.push(position(e));if(points.length===4)picking=false;render();
  });
  el('homographyPickBtn').addEventListener('click',()=>{
    if(!admin){el('homographyStatus').textContent='설정 변경은 관리자 계정이 필요합니다.';return;}
    if(!current||!source.videoWidth){el('homographyStatus').textContent='먼저 관제 화면에서 카메라를 연결하세요.';return;}
    points=[];imageSize=[source.videoWidth,source.videoHeight];picking=true;render();
  });
  function aruco(){return {enabled:el('arucoEnabled').checked,dictionary:el('arucoDictionary').value,
    marker_id:number('arucoId'),marker_size_m:Number(el('arucoSize').value)/100,
    heading_offset_deg:number('arucoOffset'),heading_measured:el('arucoHeadingMeasured').checked};}
  function apply(data,part=null){
    const h=data.homography,a=data.aruco;revision=data.revision;ready=true;
    if(!part||part==='homography'){
    points=h.image_points;imageSize=h.image_size;
    el('homographyEnabled').checked=h.enabled;el('poolWidth').value=h.pool_width_m??'';el('poolHeight').value=h.pool_height_m??'';el('poolFrame').value=h.frame_id;
    el('homographyStatus').textContent=h.enabled?'저장된 호모그래피 설정을 불러왔습니다.':'호모그래피가 꺼져 있습니다.';
    }
    if(!part||part==='aruco'){
    el('arucoEnabled').checked=a.enabled;el('arucoDictionary').value=a.dictionary;el('arucoId').value=a.marker_id;el('arucoSize').value=a.marker_size_m*100;
    el('arucoOffset').value=a.heading_offset_deg??'';el('arucoHeadingMeasured').checked=a.heading_measured;
    el('arucoStatus').textContent=a.enabled?'저장된 ArUco 설정을 불러왔습니다.':'ArUco 검출이 꺼져 있습니다.';
    }
    el('cameraConfigurationStatus').textContent=appliedRevision===revision?`카메라 설정 v${revision} · 추적 서버 적용 확인`:`저장된 카메라 설정 v${revision}`;
    render();
  }
  window.dgReportVisionApplied=applied=>{
    appliedRevision=applied;
    el('cameraConfigurationStatus').textContent=applied===revision?`카메라 설정 v${revision} · 추적 서버 적용 확인`:'카메라 설정 버전을 확인할 수 없습니다.';
  };
  async function save(part,body,status,button){
    if(!ready||!admin)return;button.disabled=true;
    try{
      const data=await dgApi('/vision/configuration/'+part+query,{method:'PUT',body});apply(data,part);
      el(status).textContent='저장했습니다. 연결된 카메라의 추적을 새 설정으로 다시 시작합니다.';
      window.dgRestartCameraTracking?.();
    }catch(error){el(status).textContent=error.message;}finally{button.disabled=!admin;}
  }
  el('homographySaveBtn').addEventListener('click',()=>{
    if(el('homographyEnabled').checked&&current&&imageSize&&
       Math.abs((source.videoWidth/source.videoHeight)/(imageSize[0]/imageSize[1])-1)>.01){
      el('homographyStatus').textContent='영상 방향·비율이 바뀌었습니다. 기준점 4개를 다시 지정하세요.';return;
    }
    void save('homography',{enabled:el('homographyEnabled').checked,image_points:points,image_size:imageSize,
      pool_width_m:number('poolWidth'),pool_height_m:number('poolHeight'),frame_id:el('poolFrame').value.trim()},'homographyStatus',el('homographySaveBtn'));
  });
  el('arucoSaveBtn').addEventListener('click',()=>void save('aruco',aruco(),'arucoStatus',el('arucoSaveBtn')));
  el('arucoImageBtn').addEventListener('click',async()=>{
    const button=el('arucoImageBtn');button.disabled=true;
    try{
      const data=await dgApi('/vision/aruco/marker'+query,{method:'POST',body:aruco()});
      const url='data:image/png;base64,'+data.image_base64;
      el('arucoMarkerImage').src=url;el('arucoMarkerImage').hidden=false;
      el('arucoMarkerDownload').href=url;el('arucoMarkerDownload').download=`${data.dictionary}-id${data.marker_id}.png`;el('arucoMarkerDownload').hidden=false;
    }catch(error){el('arucoStatus').textContent=error.message;}finally{button.disabled=false;}
  });
  el('arucoInspectBtn').addEventListener('click',async()=>{
    if(!current||!source.videoWidth){el('arucoInspectionStatus').textContent='먼저 카메라를 연결하세요.';return;}
    const button=el('arucoInspectBtn');button.disabled=true;
    const canvas=document.createElement('canvas');canvas.width=Math.min(960,source.videoWidth);canvas.height=Math.round(canvas.width*source.videoHeight/source.videoWidth);
    canvas.getContext('2d').drawImage(source,0,0,canvas.width,canvas.height);
    const captured=Date.now();el('arucoInspection').hidden=true;
    try{
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.85));if(!blob)throw new Error('이미지를 생성하지 못했습니다.');
      const body=new FormData();body.append('image',blob,'frame.jpg');
      const data=await dgApi('/vision/configuration/inspect'+query,{method:'POST',body});
      if(data.configuration_revision!==revision || data.image_size?.[0]!==canvas.width || data.image_size?.[1]!==canvas.height)throw new Error('설정 또는 영상 크기가 변경되었습니다. 다시 확인하세요.');
      const marker=data.marker_observation;
      const output=el('arucoInspection');output.width=canvas.width;output.height=canvas.height;const ctx=output.getContext('2d');ctx.drawImage(canvas,0,0);
      window.dgDrawMarker?.(ctx,marker);output.hidden=false;
      el('arucoInspectionStatus').textContent=`촬영 ${new Date(captured).toLocaleTimeString('ko-KR')} · 설정 v${data.configuration_revision} · `+
        (!marker.enabled?'ArUco가 꺼져 있습니다.':!marker.detected?'지정한 마커가 검출되지 않았습니다.':
          `마커 ID ${marker.marker_id} 검출 · ${marker.coordinate_valid?`X ${marker.x_m.toFixed(3)} m, Y ${marker.y_m.toFixed(3)} m`:'실좌표 사용 불가: '+marker.coordinate_status} · 방향 ${marker.heading_deg==null?'미측정':marker.heading_deg.toFixed(1)+'°'}`);
    }catch(error){el('arucoInspectionStatus').textContent=error.message;}finally{button.disabled=false;}
  });
  window.dgDrawMarker=(ctx,marker)=>{
    if(!marker?.detected||!Array.isArray(marker.corners_px)||marker.corners_px.length!==4)return;
    ctx.strokeStyle='#ffd166';ctx.fillStyle='#ffd166';ctx.lineWidth=3;ctx.beginPath();
    marker.corners_px.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.stroke();ctx.font='16px sans-serif';
    const p=marker.corners_px[0];ctx.fillText(`ArUco ID ${marker.marker_id}`,Math.max(0,p[0]),Math.max(18,p[1]-8));
    if(marker.coordinate_valid&&Number.isFinite(marker.x_m)&&Number.isFinite(marker.y_m)){
      const heading=Number.isFinite(marker.heading_deg)?` · 방향 ${marker.heading_deg.toFixed(1)}°`:' · 방향 미측정';
      ctx.fillText(`X ${marker.x_m.toFixed(3)} m · Y ${marker.y_m.toFixed(3)} m${heading}`,Math.max(0,p[0]),Math.min((ctx.canvas?.height??100000)-8,p[1]+22));
    }
  };
  el('homographySaveBtn').disabled=el('arucoSaveBtn').disabled=!admin;
  void dgApi('/vision/configuration'+query).then(apply).catch(error=>{
    el('homographyStatus').textContent=el('arucoStatus').textContent='설정 조회 실패: '+error.message;
  });
})();
