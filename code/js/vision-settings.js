/* Independent settings; full-image percentages survive proportional upload resizing. */
(() => {
  const el=id=>document.getElementById(id);
  const site=new URLSearchParams(location.search).get('site');
  const query='?site_id='+encodeURIComponent(site||'');
  const video=el('homographyCameraFeed'), source=el('localCameraFeed'), svg=el('homographySvg');
  let current=null, points=[], worldPoints=[], fitReport=null, imageSize=null, picking=false, revision=0, ready=false, appliedRevision=null;
  const admin=dgGetSession()?.role==='admin';
  const number=id=>el(id).value.trim()===''?null:Number(el(id).value);
  function worldCoordinates(){
    const w=number('poolWidth'),h=number('poolHeight');
    const corners=[{x:0,y:h},{x:w,y:h},{x:w,y:0},{x:0,y:0}];
    return points.map((_,i)=>i<4?corners[i]:worldPoints[i]||{x:null,y:null});
  }
  function invalidateFit(){
    fitReport=null;
    el('homographyFitStatus').textContent='기준점이 변경됐습니다. 저장하면 전체 기준점의 오차를 다시 계산합니다.';
    el('homographyPointsBody').querySelectorAll('[data-fit-error]').forEach(cell=>{cell.textContent='—';});
  }
  function renderPointTable(){
    const tbody=el('homographyPointsBody');tbody.replaceChildren();
    const world=worldCoordinates();
    points.forEach((_,i)=>{
      const row=document.createElement('tr'),label=document.createElement('td');
      label.textContent=i<4?`${i+1} · ${['좌상','우상','우하','좌하'][i]}`:String(i+1);row.appendChild(label);
      for(const axis of ['x','y']){
        const cell=document.createElement('td'),input=document.createElement('input');
        input.type='number';input.min='0';input.step='0.001';input.value=world[i][axis]??'';input.disabled=!admin||i<4;
        input.setAttribute('aria-label',`${i+1}번 실제 ${axis.toUpperCase()} 좌표`);
        input.addEventListener('input',()=>{
          worldPoints[i]={...(worldPoints[i]||{x:null,y:null}),[axis]:input.value.trim()===''?null:Number(input.value)};
          invalidateFit();
        });
        cell.appendChild(input);row.appendChild(cell);
      }
      const error=document.createElement('td');error.setAttribute('data-fit-error','');
      error.textContent=Number.isFinite(fitReport?.point_errors_m?.[i])?(fitReport.point_errors_m[i]*100).toFixed(3):'—';row.appendChild(error);
      const action=document.createElement('td');
      if(i>=4){
        const remove=document.createElement('button');remove.type='button';remove.className='btn';remove.textContent='삭제';remove.disabled=!admin;
        remove.addEventListener('click',()=>{points.splice(i,1);worldPoints.splice(i,1);invalidateFit();render();});action.appendChild(remove);
      }
      row.appendChild(action);tbody.appendChild(row);
    });
  }
  function render(table=true){
    svg.replaceChildren();
    if(points.length>1){
      const shape=document.createElementNS('http://www.w3.org/2000/svg','polygon');
      shape.setAttribute('points',points.slice(0,4).map(p=>`${p.x},${p.y}`).join(' '));
      shape.setAttribute('fill','rgba(45,217,196,.12)');shape.setAttribute('stroke','#2dd9c4');shape.setAttribute('stroke-width','.5');svg.appendChild(shape);
    }
    points.forEach((p,i)=>{
      const circle=document.createElementNS('http://www.w3.org/2000/svg','circle');
      circle.setAttribute('cx',p.x);circle.setAttribute('cy',p.y);circle.setAttribute('r','1.8');circle.setAttribute('fill',i<4?'#ffd166':'#2dd9c4');
      circle.addEventListener('click',event=>event.stopPropagation());
      circle.addEventListener('pointerdown',event=>{
        if(!admin||!current||picking)return;event.preventDefault();event.stopPropagation();
        invalidateFit();
        const move=e=>{points[i]=position(e);render(false);};
        const up=()=>{document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',up);document.removeEventListener('pointercancel',up);};
        document.addEventListener('pointermove',move);document.addEventListener('pointerup',up);document.addEventListener('pointercancel',up);
      });
      svg.appendChild(circle);
      const label=document.createElementNS('http://www.w3.org/2000/svg','text');
      label.setAttribute('x',p.x+2);label.setAttribute('y',Math.max(3,p.y-2));label.setAttribute('fill','#ffd166');label.setAttribute('font-size','3');label.textContent=String(i+1);svg.appendChild(label);
    });
    el('homographyPointCount').textContent=`총 ${points.length}점${points.length>=4?` · 추가 ${points.length-4}점`: ' · 모서리 4점 필요'}${picking?' · 영상에서 클릭하세요':''}`;
    el('homographyAddBtn').textContent=picking==='extra'?'추가 선택 멈추기':'추가 기준점 계속 찍기';
    if(table)renderPointTable();
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
    if(!picking||!current||!admin)return;
    const point=position(e);
    if(points.some(p=>Math.hypot(p.x-point.x,p.y-point.y)<1e-6))return;
    points.push(point);worldPoints.push({x:null,y:null});invalidateFit();
    if(picking==='corners'&&points.length===4)picking=false;render();
  });
  el('homographyPickBtn').addEventListener('click',()=>{
    if(!admin){el('homographyStatus').textContent='설정 변경은 관리자 계정이 필요합니다.';return;}
    if(!current||!source.videoWidth){el('homographyStatus').textContent='먼저 관제 화면에서 카메라를 연결하세요.';return;}
    points=[];worldPoints=[];imageSize=[source.videoWidth,source.videoHeight];picking='corners';invalidateFit();render();
  });
  el('homographyAddBtn').addEventListener('click',()=>{
    if(!admin||!current||!source.videoWidth){el('homographyStatus').textContent='관리자 계정으로 카메라를 연결하세요.';return;}
    if(points.length<4){el('homographyStatus').textContent='호모그래피 기준점은 최소 4개 이상 필요합니다. 먼저 보정 영역의 기준점 4개를 지정하세요.';return;}
    picking=picking==='extra'?false:'extra';render();
  });
  for(const id of ['poolWidth','poolHeight'])el(id).addEventListener('input',()=>{invalidateFit();renderPointTable();});
  let savedAruco=null;
  function aruco(){return {enabled:el('arucoEnabled').checked,dictionary:el('arucoDictionary').value,
    marker_id:number('arucoId'),marker_size_m:Number(el('arucoSize').value)/100,
    heading_offset_deg:number('arucoOffset'),heading_measured:el('arucoHeadingMeasured').checked};}
  for(const id of ['arucoEnabled','arucoDictionary','arucoId','arucoSize','arucoOffset','arucoHeadingMeasured']){
    const update=()=>{
      if(!ready)return;
      const changed=JSON.stringify(aruco())!==savedAruco;
      el('arucoStatus').textContent=changed
        ? `변경 사항 미저장 · 검출 ${el('arucoEnabled').checked?'사용':'사용 안 함'} 선택. ‘ArUco 저장 · 적용’을 눌러 반영하세요.`
        : `저장된 설정: ArUco 검출 ${el('arucoEnabled').checked?'사용':'사용 안 함'}.`;
    };
    el(id).addEventListener('input',update);el(id).addEventListener('change',update);
  }
  function apply(data,part=null){
    const h=data.homography,a=data.aruco;revision=data.revision;ready=true;
    if(!part||part==='homography'){
    points=h.image_points;worldPoints=h.world_points||points.map(()=>({x:null,y:null}));imageSize=h.image_size;fitReport=data.homography_report||null;
    el('homographyEnabled').checked=h.enabled;el('poolWidth').value=h.pool_width_m??'';el('poolHeight').value=h.pool_height_m??'';el('poolFrame').value=h.frame_id;
    el('homographyStatus').textContent=h.enabled?'저장된 호모그래피 설정을 불러왔습니다.':'호모그래피가 꺼져 있습니다.';
    el('homographyFitStatus').textContent=fitReport?`총 ${fitReport.point_count}점 · 입력 기준점 재투영 RMS ${(fitReport.rms_error_m*100).toFixed(3)} cm · 최대 ${(fitReport.max_error_m*100).toFixed(3)} cm`:'저장하면 전체 기준점의 재투영 오차를 계산합니다.';
    }
    if(!part||part==='aruco'){
    el('arucoEnabled').checked=a.enabled;el('arucoDictionary').value=a.dictionary;el('arucoId').value=a.marker_id;el('arucoSize').value=a.marker_size_m*100;
    el('arucoOffset').value=a.heading_offset_deg??'';el('arucoHeadingMeasured').checked=a.heading_measured;
    savedAruco=JSON.stringify(aruco());
    el('arucoStatus').textContent=a.enabled?'저장된 설정: ArUco 검출 사용. 현재 영상의 검출 여부는 영상 확인으로 확인하세요.':'저장된 설정: ArUco 검출 사용 안 함.';
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
    const world=worldCoordinates();
    if(points.length>4&&world.some(p=>!Number.isFinite(p.x)||!Number.isFinite(p.y))){
      el('homographyStatus').textContent='보정 영역 크기와 모든 추가 기준점의 실제 X·Y 좌표를 입력하세요.';return;
    }
    void save('homography',{enabled:el('homographyEnabled').checked,image_points:points,
      world_points:points.length>4?world:null,image_size:imageSize,
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
