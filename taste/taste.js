/* The page around Daf's taste: Reset the demo starts the sample library over, here and in the frame. */
(function(){
  'use strict';
  const frame = document.getElementById('app');
  document.getElementById('reset').addEventListener('click', () => {
    const w = frame.contentWindow;
    try { w.DafTaste.reset(); } catch(e){
      try { Object.keys(localStorage).filter(k => k.startsWith('daf.') || k.startsWith('daftaste.')).forEach(k => localStorage.removeItem(k)); } catch(x){}
    }
    try { w.location.hash = '#today'; w.location.reload(); } catch(e){ frame.src = 'app/#today'; }
  });
})();
