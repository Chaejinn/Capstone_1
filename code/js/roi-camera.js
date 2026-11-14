/* Reuse the existing MediaStream. This preview never acquires or stops a camera. */
(() => {
  const el = id => document.getElementById(id);
  const source = el('localCameraFeed'), preview = el('roiCameraFeed');
  const editor = el('roiEditor'), panel = el('videoPanel'), overlay = el('roiSvgControl');
  let current = null;
  function fit(){
    window.dgResizeDefaultRoi?.();
    if(!current || !source.videoWidth || !source.videoHeight) return;
    editor.style.setProperty('--roi-camera-aspect',`${source.videoWidth} / ${source.videoHeight}`);
    // The live video uses object-fit:contain. Keep percentage ROI coordinates
    // on its actual image, excluding black bars and the container's border.
    const width = panel.clientWidth, height = panel.clientHeight;
    if(!width || !height) return;
    const scale = Math.min(width/source.videoWidth,height/source.videoHeight);
    const imageWidth = source.videoWidth*scale, imageHeight = source.videoHeight*scale;
    overlay.style.inset = 'auto';
    overlay.style.left = `${(width-imageWidth)/2}px`;
    overlay.style.top = `${(height-imageHeight)/2}px`;
    overlay.style.width = `${imageWidth}px`;
    overlay.style.height = `${imageHeight}px`;
  }
  window.dgSyncRoiCamera = stream => {
    current = stream;
    editor.classList.toggle('has-camera',Boolean(stream));
    preview.hidden = !stream;
    if(stream){
      preview.srcObject = stream;
      el('roiCameraStatus').textContent = '실시간 카메라 영상입니다. 정점을 드래그한 뒤 감시 구역을 저장하세요.';
      void preview.play().catch(() => {
        if(current === stream) el('roiCameraStatus').textContent = '미리보기를 재생하지 못했습니다. 카메라를 다시 연결해 주세요.';
      });
      fit();
    }else{
      preview.pause();preview.srcObject = null;
      editor.style.removeProperty('--roi-camera-aspect');
      overlay.style.inset = '0';
      overlay.style.left = overlay.style.top = '';
      overlay.style.width = overlay.style.height = '100%';
      el('roiCameraStatus').textContent = '카메라를 연결하면 실제 영상을 보며 정점을 드래그할 수 있습니다.';
    }
  };
  source.addEventListener('loadedmetadata',fit);
  source.addEventListener('resize',fit);
  const sizes = new ResizeObserver(fit);
  sizes.observe(panel);
  window.addEventListener('resize',fit);
})();
