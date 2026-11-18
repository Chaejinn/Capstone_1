/* Settings-only, manually requested signals. Never starts random automation. */
(() => {
  const el=id=>document.getElementById(id),view=el('view-control'),mode=el('signalBridgeMode');
  const buttons=[...document.querySelectorAll('[data-signal-command]')];
  const query='?site_id='+encodeURIComponent(new URLSearchParams(location.search).get('site')||'');
  let version=0,timer=null,abort=null,cursor=null,busy=false,usb=null,autoRunning=false,pending=0;
  let chain=Promise.resolve(),usedHc06=false;
  function history(text){
    const item=document.createElement('li');item.textContent=new Date().toLocaleTimeString('ko-KR')+' · '+text;
    el('signalHistory').prepend(item);while(el('signalHistory').children.length>20)el('signalHistory').lastChild.remove();
  }
  function controls(){
    const isUsb=mode.value==='usb';mode.disabled=busy;el('signalTargetFields').hidden=isUsb;
    el('signalBridgeHelp').textContent=isUsb
      ? 'USB는 직진 10%·최대 0.8초 시험과 정지를 지원합니다. 조향·구조망·복귀는 아직 연결되지 않았습니다.'
      : 'signal_bridge.py 연결 시 실제 보드로 전달됩니다. 출동 신호 후 정지 신호가 필요하며, 복귀 신호는 현재 정지만 수행합니다.';
    for(const button of buttons){
      const cmd=button.dataset.signalCommand;
      button.disabled=(busy&&cmd!=='ESTOP')||(isUsb&&!['DISPATCH','ESTOP','CANCEL'].includes(cmd))||
        (isUsb&&cmd==='DISPATCH'&&(!usb?.connected||usb.last_command!=='STOP'))||(!isUsb&&autoRunning&&cmd!=='ESTOP');
    }
  }
  async function poll(run){
    if(view.hidden||run!==version)return;
    abort=new AbortController();const timeout=setTimeout(()=>abort?.abort(),6000);
    try{
      if(mode.value==='usb'){
        const data=await dgApi('/board-control/status'+query,{signal:abort.signal});if(run!==version)return;
        usb=data;el('signalBridgeStatus').textContent=data.connected?'USB 브릿지 연결됨 · 실제 보드 수신은 브릿지 터미널에서 확인하세요.':'USB 브릿지 연결 대기';
        el('signalServerState').textContent=`서버에 등록된 명령: ${data.last_command||'없음'} · 기록 번호 ${data.revision??0}`;
        el('signalAutoStop').hidden=true;
      }else{
        const [control,signals,auto]=await Promise.all([
          dgApi('/test-control?latest=true',{signal:abort.signal}),
          dgApi('/test-signals?'+(cursor===null?'latest=true':'after_id='+cursor),{signal:abort.signal}),
          dgApi('/test-control/auto',{signal:abort.signal})]);
        if(run!==version)return;
        for(const item of signals.signals||[])history(`${item.source}: ${item.message}`);
        cursor=signals.cursor;autoRunning=auto.running===true;
        el('signalBridgeStatus').textContent='신호 서버 조회 중 · HC-06 연결 여부는 브릿지 터미널에서 확인하세요.';
        el('signalServerState').textContent=`서버 상태: ${control.state?.status||'대기'} · 비상정지 ${control.state?.estop?'켜짐':'꺼짐'}`;
        el('signalAutoStop').hidden=!autoRunning;
        if(autoRunning)el('signalBridgeStatus').textContent='자동 임의 신호가 실행 중입니다. 수동 시험 전에 중지하세요.';
      }
      controls();
    }catch(error){if(run===version&&!view.hidden)el('signalBridgeStatus').textContent='상태 조회 실패: '+error.message;}
    finally{clearTimeout(timeout);if(run===version&&!view.hidden)timer=setTimeout(()=>poll(run),2000);}
  }
  function sync(){version++;clearTimeout(timer);abort?.abort();cursor=null;usb=null;controls();if(!view.hidden)void poll(version);}
  function send(command){
    const selected=mode.value;
    if(selected==='usb'&&!['DISPATCH','ESTOP','CANCEL'].includes(command))return Promise.resolve();
    let body={command};
    if(selected==='hc06'&&command==='DISPATCH'){
      const x=Number(el('signalTargetX').value),y=Number(el('signalTargetY').value);
      if(!el('signalTargetX').value.trim()||!el('signalTargetY').value.trim()||!Number.isFinite(x)||!Number.isFinite(y)){
        el('signalCommandStatus').textContent='유효한 시험 목표 X·Y를 입력하세요.';return Promise.resolve();
      }
      body={command,target_x:x,target_y:y};
    }
    if(selected==='hc06')usedHc06=true;
    pending++;busy=true;controls();
    chain=chain.catch(()=>{}).then(async()=>{
      const request=new AbortController(),timeout=setTimeout(()=>request.abort(),8000);
      try{
        if(selected==='hc06'&&command==='ESTOP'){await dgApi('/test-control/auto/stop',{method:'POST',signal:request.signal}).catch(()=>{});autoRunning=false;}
        const path=selected==='usb'?'/board-control/'+(command==='DISPATCH'?'simulate':'stop')+query:'/test-control';
        const response=await dgApi(path,{method:'POST',...(selected==='hc06'?{body}:{}),signal:request.signal});
        const text=`${selected==='usb'?'USB':'HC-06'} · ${command} 서버 등록 완료 · 실제 동작은 별도 확인`;
        el('signalCommandStatus').textContent=text;history(text);if(selected==='usb'&&response.status)usb=null;
      }catch(error){el('signalCommandStatus').textContent='명령 전송 실패: '+error.message;}
      finally{clearTimeout(timeout);pending--;busy=pending>0;controls();}
    });return chain;
  }
  buttons.forEach(button=>button.addEventListener('click',()=>void send(button.dataset.signalCommand)));
  el('signalAutoStop').addEventListener('click',async()=>{
    try{await dgApi('/test-control/auto/stop',{method:'POST'});autoRunning=false;el('signalAutoStop').hidden=true;controls();}
    catch(error){el('signalCommandStatus').textContent=error.message;}
  });
  mode.addEventListener('change',sync);
  new MutationObserver(sync).observe(view,{attributes:true,attributeFilter:['hidden']});
  window.dgStopSignalTest=()=>{
    if(!usedHc06)return;
    // Same manual test channel; do not let a random generator undo the stop.
    return chain.catch(()=>{}).then(()=>dgApi('/test-control/auto/stop',{method:'POST'})).catch(()=>{}).then(()=>dgApi('/test-control',{method:'POST',body:{command:'ESTOP'},keepalive:true}))
      .catch(error=>{el('signalCommandStatus').textContent='신호 브릿지 정지 전송 실패: '+error.message;});
  };
  el('logoutBtn').addEventListener('click',()=>{if(usedHc06)void dgApi('/test-control',{method:'POST',body:{command:'ESTOP'},keepalive:true}).catch(()=>{});},true);
  window.addEventListener('pagehide',()=>{version++;clearTimeout(timer);abort?.abort();if(usedHc06)void dgApi('/test-control',{method:'POST',body:{command:'ESTOP'},keepalive:true}).catch(()=>{});});
  window.dgPlaceSignalTest=()=>{
    const live=Boolean(window.dgCameraLive),side=el('signalSideHost'),wide=el('signalWideHost'),card=el('dashboardSignalTest');
    const host=live?wide:side;if(card.parentElement!==host)host.appendChild(card);
    side.hidden=live;wide.hidden=!live;
  };
  window.dgPlaceSignalTest();controls();if(!view.hidden)void poll(version);
})();
