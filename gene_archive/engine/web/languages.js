/* Language menu: the link keeps the open person, document, place or tree route (#/…). */
(function () {
  'use strict';
  var links = document.querySelectorAll('[data-site-lang]');
  function update() {
    links.forEach(function (a) {
      var base = a.getAttribute('data-href') || a.getAttribute('href').split('#')[0].split('?')[0];
      a.setAttribute('data-href', base);
      a.href = base + location.search + location.hash;
    });
  }
  update();
  window.addEventListener('hashchange', update);
  // the tree also changes the address with history.replaceState / pushState
  links.forEach(function (a) { a.addEventListener('click', update); });
  // header drop-down menus (language, "More"): only one open; closed by a click elsewhere or Esc
  var menus = document.querySelectorAll('details.more-menu');
  menus.forEach(function (m) {
    m.addEventListener('toggle', function () { if (m.open) menus.forEach(function (o) { if (o !== m) o.open = false; }); });
  });
  document.addEventListener('click', function (e) { menus.forEach(function (m) { if (m.open && !m.contains(e.target)) m.open = false; }); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') menus.forEach(function (m) { m.open = false; }); });
})();
