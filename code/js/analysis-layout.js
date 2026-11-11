/* Spend only the existing space below the status card; never extend the camera row. */
(() => {
  const column = document.getElementById('cameraColumn');
  const board = document.getElementById('boardStatusCard');
  const panels = ['aiResultPanel','edgeResultPanel'].map(id => document.getElementById(id));
  const gap = 14;
  let scheduled = false;
  function update(){
    scheduled = false;
    const panel = panels.find(item => !item.hidden);
    const available = Math.max(0, column.getBoundingClientRect().height - board.getBoundingClientRect().height - gap);
    board.style.marginTop = panel && available > 0 ? `${available + gap}px` : '';
    for(const item of panels){
      item.style.height = item === panel ? `${available}px` : '0px';
      item.style.visibility = item === panel && available > 0 ? 'visible' : 'hidden';
    }
  }
  function schedule(){
    if(!scheduled){scheduled = true;requestAnimationFrame(update);}
  }
  const sizes = new ResizeObserver(schedule);
  sizes.observe(column);sizes.observe(board);
  const visibility = new MutationObserver(schedule);
  panels.forEach(panel => visibility.observe(panel,{attributes:true,attributeFilter:['hidden']}));
  window.addEventListener('resize',schedule);
  schedule();
})();
