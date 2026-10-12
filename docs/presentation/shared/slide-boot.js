(function () {
  var inIframe = window.self !== window.top;
  var params = new URLSearchParams(location.search);
  var motion = params.get('motion');
  var full = motion === 'full';
  var staticExport = motion === 'off' || motion === 'static' || motion === 'none';

  if (staticExport) {
    document.documentElement.classList.add('export-static');
    document.addEventListener('DOMContentLoaded', function () {
      document.body.classList.add('motion-lite');
      document.body.classList.remove('motion-full');
      freezeReveals();
    });
  } else if (inIframe && !full) {
    document.documentElement.classList.add('embed-thumb');
    document.addEventListener('DOMContentLoaded', function () {
      document.body.classList.add('embed-thumb');
    });
  } else {
    document.addEventListener('DOMContentLoaded', function () {
      document.body.classList.add('motion-full');
    });
  }

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) document.body.classList.add('motion-lite');
    else if (!inIframe || full) document.body.classList.remove('motion-lite');
  });

  function freezeReveals() {
    document.querySelectorAll(
      '.reveal-up, .reveal-fade, .reveal-left, .reveal-scale, .reveal-line'
    ).forEach(function (el) {
      el.style.animation = 'none';
      el.style.opacity = '1';
      el.style.transform = 'none';
    });
    document.querySelectorAll('.pipeline-draw').forEach(function (el) {
      el.style.animation = 'none';
      el.style.strokeDashoffset = '0';
    });
    document.querySelectorAll('.flow-connector').forEach(function (el) {
      el.style.animation = 'none';
    });
  }

  window.__deckFreezeReveals = freezeReveals;
  if (!staticExport) {
    document.addEventListener('DOMContentLoaded', function () {
      setTimeout(freezeReveals, 2800);
    });
  }
})();
