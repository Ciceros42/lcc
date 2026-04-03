(function () {
  var btn = document.createElement('button');
  btn.id        = 'scroll-top-btn';
  btn.title     = 'Back to top';
  btn.innerHTML = '&#8679;';
  document.body.appendChild(btn);

  var lastY   = window.scrollY;
  var visible = false;

  function setVisible(show) {
    if (show === visible) return;
    visible = show;
    btn.classList.toggle('scroll-top-visible', show);
  }

  window.addEventListener('scroll', function () {
    var y = window.scrollY;
    if (y < 120) {
      setVisible(false);
    } else if (y < lastY) {
      setVisible(true);
    }
    lastY = y;
  }, { passive: true });

  btn.addEventListener('click', function () {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
})();
