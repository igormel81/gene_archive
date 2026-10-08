/* gene-archive: interactive family tree, person cards, documents, places and relatives' comments.
   Data — data.json (built by `gene build`), comments — api/comments (optional server).
   UI strings are wrapped in T(): the Russian source text is the key, translations come from
   window.GENE_LOCALE (i18n/<lang>.js, written by the build). MIT License. */
(function () {
  'use strict';

  // ---------- i18n and site settings
  var LOCALE = window.GENE_LOCALE || { lang: 'ru', locale: 'ru-RU', strings: {} };
  function T(s) { var x = LOCALE.strings[s]; return x == null ? s : x; }
  // path from this page to the site root ('' for the main language, '../' for /en/ etc.)
  var ROOT = window.GENE_ROOT || '';
  var SITE = {};

  // ---------- helpers
  function el(tag, attrs) {
    var node = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        var v = attrs[k];
        if (v == null || v === false) continue;
        if (k === 'class') node.className = v;
        else if (k === 'text') node.textContent = v;
        else if (k.slice(0, 2) === 'on') node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v === true ? '' : v);
      }
    }
    for (var i = 2; i < arguments.length; i++) append(node, arguments[i]);
    return node;
  }
  function append(node, child) {
    if (child == null || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { append(node, c); }); return; }
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  function $(id) { return document.getElementById(id); }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }
  function store(key, value) {
    try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (e) { return null; }
  }

  var MONTHS = [T('января'), T('февраля'), T('марта'), T('апреля'), T('мая'), T('июня'), T('июля'), T('августа'), T('сентября'), T('октября'), T('ноября'), T('декабря')];
  function fmtDate(v) {
    if (!v) return '';
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
    if (m) return +m[3] + ' ' + MONTHS[+m[2] - 1] + ' ' + m[1];
    var STAND = [T('январь'), T('февраль'), T('март'), T('апрель'), T('май'), T('июнь'), T('июль'), T('август'), T('сентябрь'), T('октябрь'), T('ноябрь'), T('декабрь')];
    m = /^(\d{4})-(\d{2})$/.exec(v);
    if (m) return STAND[+m[2] - 1] + ' ' + m[1];
    // GEDCOM forms: 9 OCT 1899, OCT 1899, ABT/EST/CAL, BEF, AFT, BET … AND …, FROM … TO …
    var GM = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
    m = /^(\d{1,2}) ([A-Z]{3}) (\d{3,4})$/.exec(v);
    if (m && GM.indexOf(m[2]) >= 0) return +m[1] + ' ' + MONTHS[GM.indexOf(m[2])] + ' ' + m[3];
    m = /^([A-Z]{3}) (\d{3,4})$/.exec(v);
    if (m && GM.indexOf(m[1]) >= 0) return STAND[GM.indexOf(m[1])] + ' ' + m[2];
    m = /^(?:ABT|EST|CAL) (.+)$/.exec(v);
    if (m) return T('около ') + fmtDate(m[1]);
    m = /^BEF (.+)$/.exec(v);
    if (m) return T('до ') + fmtDate(m[1]);
    m = /^AFT (.+)$/.exec(v);
    if (m) return T('после ') + fmtDate(m[1]);
    m = /^(?:BET|FROM) (.+?) (?:AND|TO) (.+)$/.exec(v);
    if (m) return fmtDate(m[1]) + ' – ' + fmtDate(m[2]);
    m = /^FROM (.+)$/.exec(v);
    if (m) return T('с ') + fmtDate(m[1]);
    return v;
  }
  function year(v) {
    if (!v) return '';
    var m = /\d{4}/.exec(v);
    return m ? (v.indexOf('ABT') === 0 ? T('ок. ') : v.indexOf('AFT') === 0 ? T('после ') : '') + m[0] : '';
  }
  function lifespan(p) {
    var b = year(p.birth && p.birth.date);
    if (!b && p.birth_alternatives && p.birth_alternatives.length) b = year(p.birth_alternatives[0].date);
    var d = year(p.death && p.death.date);
    if (b && d) return b + ' – ' + d;
    if (b) return T('р. ') + b;
    if (d) return '† ' + d;
    return '';
  }
  function fmtStamp(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString(LOCALE.locale, { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  function plural(n, one, few, many) {
    if (LOCALE.plural === 'one_other') return n === 1 ? one : few;
    if (LOCALE.plural === 'ro') return n === 1 ? one : (n === 0 || (n % 100 >= 2 && n % 100 <= 19) ? few : many);
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }

  // ---------- state
  var D, P = {}, F = {}, S = {}, parentFam = {}, spouseFams = {};
  var comments = [], byPerson = {};
  var focusId = null, selectedId = null, selectedPlace = null;
  var view = { x: 0, y: 0, k: 1 };
  var cardPos = {};
  var peopleMode = 'list', calendarEvents = [], bioOpen = null, biosHtml = null;
  var calendarNow = new Date();
  var calendar = { year: calendarNow.getFullYear(), month: calendarNow.getMonth(), kind: 'all', day: null };
  var WEEKDAYS = [T('воскресенье'), T('понедельник'), T('вторник'), T('среда'), T('четверг'), T('пятница'), T('суббота')];
  var CALENDAR_MONTHS = [T('Январь'), T('Февраль'), T('Март'), T('Апрель'), T('Май'), T('Июнь'), T('Июль'), T('Август'), T('Сентябрь'), T('Октябрь'), T('Ноябрь'), T('Декабрь')];
  var zodiacSelection = null, zodiacPeople = [], zodiacLimit = 24;
  var ZODIAC = [
    { id: 'aries', name: T('Овен'), symbol: '♈\uFE0E', from: 321, to: 419, element: 'fire' },
    { id: 'taurus', name: T('Телец'), symbol: '♉\uFE0E', from: 420, to: 520, element: 'earth' },
    { id: 'gemini', name: T('Близнецы'), symbol: '♊\uFE0E', from: 521, to: 620, element: 'air' },
    { id: 'cancer', name: T('Рак'), symbol: '♋\uFE0E', from: 621, to: 722, element: 'water' },
    { id: 'leo', name: T('Лев'), symbol: '♌\uFE0E', from: 723, to: 822, element: 'fire' },
    { id: 'virgo', name: T('Дева'), symbol: '♍\uFE0E', from: 823, to: 922, element: 'earth' },
    { id: 'libra', name: T('Весы'), symbol: '♎\uFE0E', from: 923, to: 1022, element: 'air' },
    { id: 'scorpio', name: T('Скорпион'), symbol: '♏\uFE0E', from: 1023, to: 1121, element: 'water' },
    { id: 'sagittarius', name: T('Стрелец'), symbol: '♐\uFE0E', from: 1122, to: 1221, element: 'fire' },
    { id: 'capricorn', name: T('Козерог'), symbol: '♑\uFE0E', from: 1222, to: 119, element: 'earth' },
    { id: 'aquarius', name: T('Водолей'), symbol: '♒\uFE0E', from: 120, to: 218, element: 'air' },
    { id: 'pisces', name: T('Рыбы'), symbol: '♓\uFE0E', from: 219, to: 320, element: 'water' }
  ];
  var ZODIAC_ELEMENTS = { fire: T('Огонь'), earth: T('Земля'), air: T('Воздух'), water: T('Вода') };

  function index() {
    D.people.forEach(function (p) { P[p.id] = p; });
    D.families.forEach(function (f) {
      F[f.id] = f;
      f.children.forEach(function (c) { parentFam[c] = f; });
      f.partners.forEach(function (p) { (spouseFams[p] = spouseFams[p] || []).push(f); });
    });
    D.sources.forEach(function (s) { S[s.id] = s; });
    indexCalendar();
    indexZodiac();
    indexCertain();
    indexStory();
  }
  // Who is linked to the root person only through an unproven link. Exactly they are drawn dashed,
  // not the person whose own parents are unproven.
  var certain = {}, linked = {};
  function indexCertain() {
    function walk(seen, strict) {
      var todo = [D.root_person_id]; seen[D.root_person_id] = true;
      function go(x) { if (P[x] && !seen[x]) { seen[x] = true; todo.push(x); } }
      while (todo.length) {
        var id = todo.pop(), f = parentFam[id];
        if (f && !(strict && (f.probable_children || []).indexOf(id) >= 0)) f.partners.forEach(go);
        (spouseFams[id] || []).forEach(function (g) {
          g.partners.forEach(go);
          g.children.forEach(function (c) { if (!(strict && (g.probable_children || []).indexOf(c) >= 0)) go(c); });
        });
      }
    }
    walk(certain, true); walk(linked, false);
  }

  function parentsOf(id) { var f = parentFam[id]; return f ? f.partners.slice() : []; }
  function siblingsOf(id) { var f = parentFam[id]; return f ? f.children.filter(function (c) { return c !== id; }) : []; }
  function spousesOf(id) {
    var out = [];
    (spouseFams[id] || []).forEach(function (f) { f.partners.forEach(function (x) { if (x !== id && out.indexOf(x) < 0) out.push(x); }); });
    return out;
  }
  function childrenOf(id) {
    var out = [];
    (spouseFams[id] || []).forEach(function (f) { f.children.forEach(function (c) { if (out.indexOf(c) < 0) out.push(c); }); });
    return out;
  }
  // связь с собственными родителями не доказана (пояснение в карточке, в строке «Родители»)
  function parentsProbable(id) { var f = parentFam[id]; return P[id].research_status === 'unlinked_candidate' || !!(f && (f.probable_children || []).indexOf(id) >= 0); }
  // dashed card: the relation to the root person rests on probable links only
  function isProbable(id) { return P[id].research_status === 'unlinked_candidate' || (!!linked[id] && !certain[id]); }
  function probableNote(id) { if (P[id].research_status === 'unlinked_candidate') return P[id].research_note; var f = parentFam[id]; return f && parentsProbable(id) ? (f.probable_note || T('Связь с родителями вероятная, документом не подтверждена.')) : ''; }
  function sexClass(id) { var s = P[id].sex; return s === 'M' ? 'm' : s === 'F' ? 'f' : 'u'; }

  // ---------- tree layout (hourglass around the focus person)
  var CW = 200, CH = 86, GX = 20, GY = 64, SW = CW + GX, RH = CH + GY;
  var ANC = 5, DESC = 3;
  var line = null, lineKey = null;   // страница фамилии: её носители; древо раскрывается вниз на все поколения

  function buildAnc(id, depth) {
    var node = { id: id, depth: depth, parents: [] };
    if (depth >= ANC) return node;
    var f = parentFam[id];
    if (!f || !f.partners.length) {
      if (depth < 2) node.parents.push({ ghost: T('родители не установлены'), of: id, depth: depth + 1, parents: [] });
      return node;
    }
    var father = f.partners.filter(function (x) { return P[x].sex === 'M'; })[0];
    var mother = f.partners.filter(function (x) { return P[x].sex !== 'M'; })[0];
    // Заглушку для неизвестного родителя рисуем только в ближних поколениях: в дальних она лишь раздвигает цепочку.
    if (father) node.parents.push(buildAnc(father, depth + 1));
    else if (depth < 2) node.parents.push({ ghost: T('отец не установлен'), of: id, depth: depth + 1, parents: [] });
    if (mother) node.parents.push(buildAnc(mother, depth + 1));
    else if (depth < 2) node.parents.push({ ghost: T('мать не установлена'), of: id, depth: depth + 1, parents: [] });
    return node;
  }
  function placeAnc(node, cursor) {
    if (!node.parents.length) { node.x = cursor.x; cursor.x += 1; return; }
    node.parents.forEach(function (p) { placeAnc(p, cursor); });
    node.x = (node.parents[0].x + node.parents[node.parents.length - 1].x) / 2;
  }

  // descendant unit: person + spouses side by side (второй супруг слева, как в ряду центра),
  // дети каждого брака — отдельной группой под своей парой
  function buildDesc(id, depth) {
    var sp = spousesOf(id);
    var unit = { id: id, depth: depth, left: sp[1] ? [sp[1]] : [], right: sp.slice(0, 1).concat(sp.slice(2)), groups: [], kids: [] };
    unit.slots = 1 + sp.length;
    // на странице фамилии видны все потомки её старшего носителя
    if (depth < DESC || (line && depth < 12)) {
      var seen = {};
      unit.groups = (spouseFams[id] || []).map(function (f) {
        var other = f.partners.filter(function (x) { return x !== id; })[0] || null;
        var kids = f.children.concat(f.adopted_children || []).filter(function (c) { if (seen[c]) return false; seen[c] = true; return true; });
        return { other: other, units: kids.map(function (c) { return buildDesc(c, depth + 1); }) };
      }).filter(function (g) { return g.units.length; });
      function side(g) { return g.other === null ? 0 : g.other === unit.left[0] ? -1 : 1 + unit.right.indexOf(g.other); }
      unit.groups.sort(function (a, b) { return side(a) - side(b); });
      unit.groups.forEach(function (g) { unit.kids = unit.kids.concat(g.units); });
    }
    contourDesc(unit);
    return unit;
  }
  // Плотная раскладка потомков: у каждого поддерева запоминаем, какие слоты оно занимает в каждом поколении,
  // и придвигаем следующего брата вплотную — так, чтобы карточки не пересекались ни в одном поколении.
  // Иначе ветка занимает полосу по самому широкому поколению, и старшие поколения разъезжаются.
  function contourDesc(unit) {
    var c = {}, acc = {}, offs = [];
    function add(m, d, lo, hi) { if (!m[d]) m[d] = [lo, hi]; else { m[d][0] = Math.min(m[d][0], lo); m[d][1] = Math.max(m[d][1], hi); } }
    unit.kids.forEach(function (k) {
      var off = offs.length ? offs[offs.length - 1] + 1 : 0, d;
      for (d in k.contour) if (acc[d]) off = Math.max(off, acc[d][1] + 1 - k.contour[d][0]);
      offs.push(off);
      for (d in k.contour) add(acc, d, k.contour[d][0] + off, k.contour[d][1] + off);
    });
    var shift = offs.length ? -(offs[0] + offs[offs.length - 1]) / 2 : 0;
    unit.offs = offs.map(function (o) { return o + shift; });
    add(c, unit.depth, -unit.left.length, unit.right.length);
    for (var d in acc) add(c, d, acc[d][0] + shift, acc[d][1] + shift);
    var lo = Infinity, hi = -Infinity;
    for (d in c) { lo = Math.min(lo, c[d][0]); hi = Math.max(hi, c[d][1]); }
    unit.contour = c; unit.lo = lo; unit.w = hi - lo + 1;
  }
  function placeDescAt(unit, x) {
    unit.x = x;
    var i = 0;
    unit.groups.forEach(function (g) { g.xs = []; g.units.forEach(function (k) { placeDescAt(k, x + unit.offs[i++]); g.xs.push(k.x); }); });
  }
  function placeDesc(unit, x0) { placeDescAt(unit, x0 - unit.lo); }

  function layout(focus) {
    var cards = [], links = [];
    function card(id, x, row, extra) {
      var c = { id: id, x: x, row: row };
      for (var k in extra || {}) c[k] = extra[k];
      cards.push(c);
      return c;
    }

    // ancestors
    var root = buildAnc(focus, 0);
    placeAnc(root, { x: 0 });
    var fx = root.x;
    (function walk(node) {
      if (node.depth > 0) card(node.id || null, node.x, -node.depth, node.ghost ? { ghost: node.ghost, of: node.of } : { kind: 'anc' });
      node.parents.forEach(walk);
      if (node.depth > 0 && node.parents.length) {
        links.push({ type: 'up', child: { x: node.x, row: -node.depth }, parents: node.parents.map(function (p) { return { x: p.x, row: -p.depth, ghost: !!p.ghost }; }) });
      }
    })(root);

    // focus row: [siblings] [2nd spouse] focus [1st spouse] [others]
    card(focus, fx, 0, { focus: true });
    var sp = spousesOf(focus);
    var spX = {};
    if (sp[0]) spX[sp[0]] = fx + 1;
    if (sp[1]) spX[sp[1]] = fx - 1;
    for (var i = 2; i < sp.length; i++) spX[sp[i]] = fx + i;
    sp.forEach(function (s) {
      card(s, spX[s], 0, { kind: 'spouse' });
      links.push({ type: 'couple', a: Math.min(fx, spX[s]), b: Math.max(fx, spX[s]), row: 0 });
    });
    var sibs = siblingsOf(focus);
    var leftmost = sp[1] ? fx - 1 : fx;
    sibs.forEach(function (s, j) { card(s, leftmost - sibs.length + j, 0, { kind: 'sib' }); });
    if (root.parents.length) {
      var sibXs = sibs.map(function (s, j) { return leftmost - sibs.length + j; }).concat([fx]);
      var parentPts = root.parents.map(function (p) { return { x: p.x, ghost: !!p.ghost }; });
      links.push({ type: 'sibs', parents: parentPts, kids: sibXs, row: 0 });
    }

    // children of the focus, grouped by family
    var fams = (spouseFams[focus] || []).slice();
    fams.sort(function (a, b) {
      var sa = a.partners.filter(function (x) { return x !== focus; })[0], sb = b.partners.filter(function (x) { return x !== focus; })[0];
      return (sa ? spX[sa] : fx) - (sb ? spX[sb] : fx);
    });
    var blocks = fams.map(function (f) {
      var units = f.children.map(function (c) { return buildDesc(c, 1); });
      var other = f.partners.filter(function (x) { return x !== focus; })[0];
      // дети одного брака пакуются так же плотно, как внуки: узкий брат встаёт рядом с широкой веткой
      var pack = { depth: 0, left: [], right: [], kids: units };
      contourDesc(pack);
      return { units: units, pack: pack, w: pack.w, from: other ? (fx + spX[other]) / 2 : fx, couple: !!other };
    }).filter(function (b) { return b.units.length; });
    // браки тоже пакуются по контуру: ребёнок второго брака встаёт рядом с братом, а не за краем его ветки
    var acc = {}, bOffs = [];
    blocks.forEach(function (b) {
      var off = bOffs.length ? bOffs[bOffs.length - 1] : 0, d;
      for (d in b.pack.contour) if (+d > 0 && acc[d]) off = Math.max(off, acc[d][1] + 1.3 - b.pack.contour[d][0]);
      bOffs.push(off);
      for (d in b.pack.contour) if (+d > 0) acc[d] = acc[d] ? [Math.min(acc[d][0], b.pack.contour[d][0] + off), Math.max(acc[d][1], b.pack.contour[d][1] + off)] : [b.pack.contour[d][0] + off, b.pack.contour[d][1] + off];
    });
    var bLo = Infinity, bHi = -Infinity;
    for (var dd in acc) { bLo = Math.min(bLo, acc[dd][0]); bHi = Math.max(bHi, acc[dd][1]); }
    var anchor = blocks.length ? blocks.reduce(function (a, b) { return a + b.from; }, 0) / blocks.length : fx;
    var bShift = blocks.length ? anchor + 0.5 - (bHi - bLo + 1) / 2 - bLo : 0;
    blocks.forEach(function (b, bi) {
      var kidXs = [];
      var mid = bOffs[bi] + bShift;
      b.units.forEach(function (u, i) { placeDescAt(u, mid + b.pack.offs[i]); kidXs.push(u.x); });
      links.push({ type: 'down', from: b.from, couple: b.couple, row: 0, kids: kidXs });
      b.units.forEach(function walk(u) {
        card(u.id, u.x, u.depth, { kind: 'desc' });
        u.left.forEach(function (s) {
          card(s, u.x - 1, u.depth, { kind: 'desc-spouse' });
          links.push({ type: 'couple', a: u.x - 1, b: u.x, row: u.depth });
        });
        u.right.forEach(function (s, j) {
          card(s, u.x + 1 + j, u.depth, { kind: 'desc-spouse' });
          links.push({ type: 'couple', a: u.x + j, b: u.x + 1 + j, row: u.depth });
        });
        u.groups.forEach(function (g) {
          var from = g.other === null ? u.x : g.other === u.left[0] ? u.x - 0.5 : u.x + u.right.indexOf(g.other) + 0.5;
          links.push({ type: 'down', from: from, couple: g.other !== null, row: u.depth, kids: g.xs });
          g.units.forEach(walk);
        });
      });
    });
    return { cards: cards, links: links };
  }

  function hiddenRelatives(id, shown) {
    var rel = parentsOf(id).concat(spousesOf(id), childrenOf(id));
    return rel.filter(function (r) { return !shown[r]; }).length;
  }

  // Ориентация «Древа»: вертикальная (предки сверху) или горизонтальная (предки слева).
  // Раскладка считает в абстрактных осях: слот (поперёк поколений) и ряд (поколение).
  // В горизонтальном режиме карточки шире и ниже: поколение занимает колонку, и по высоте помещается больше людей.
  var horiz = store('gene.treeHoriz') === '1';
  var HCW = 260, HCH = 52;
  function cardW() { return horiz ? HCW : CW; }
  function cardH() { return horiz ? HCH : CH; }
  function geom() {
    return horiz
      ? { CS: HCH, MS: HCW, SS: HCH + 16, RS: HCW + 56, GM: 56 }
      : { CS: CW, MS: CH, SS: SW, RS: RH, GM: GY };
  }

  function renderTree() {
    var L = layout(focusId), G = geom();
    var minX = Infinity, minR = Infinity, maxX = -Infinity, maxR = -Infinity;
    L.cards.forEach(function (c) { minX = Math.min(minX, c.x); maxX = Math.max(maxX, c.x); minR = Math.min(minR, c.row); maxR = Math.max(maxR, c.row); });
    var PAD = 40;
    function cs(x) { return (x - minX) * G.SS + PAD; }   // начало карточки поперёк поколений
    function ms(r) { return (r - minR) * G.RS + PAD; }   // начало карточки вдоль поколений
    var crossLen = (maxX - minX) * G.SS + G.CS + PAD * 2, mainLen = (maxR - minR) * G.RS + G.MS + PAD * 2;
    var W = horiz ? mainLen : crossLen, H = horiz ? crossLen : mainLen;
    function at(x, r) { return horiz ? { x: ms(r), y: cs(x) } : { x: cs(x), y: ms(r) }; }

    var shown = {};
    L.cards.forEach(function (c) { if (c.id) shown[c.id] = true; });

    var stage = $('stage'), host = clear($('cards'));
    stage.classList.toggle('horiz', horiz);
    stage.style.width = W + 'px';
    stage.style.height = H + 'px';
    cardPos = {};
    L.cards.forEach(function (c) {
      var pt = at(c.x, c.row), x = pt.x, y = pt.y;
      var node;
      if (c.label) {
        node = el('div', { class: 'card candidate-label', style: 'left:' + x + 'px;top:' + y + 'px' },
          el('span', { class: 'nm', text: c.label }), el('span', { class: 'yr', text: c.detail }));
      } else if (c.ghost) {
        node = el('button', { class: 'card ghost', style: 'left:' + x + 'px;top:' + y + 'px', title: T('Знаете, кто это? Напишите в карточке'), onclick: guard(function () { openPerson(c.of, { compose: true }); }) },
          el('span', { class: 'yr', text: c.ghost }), el('span', { class: 'yr', text: T('+ подсказать') }));
      } else {
        var p = P[c.id];
        var n = (byPerson[c.id] || []).length;
        var more = hiddenRelatives(c.id, shown);
        node = el('button', {
          class: 'card ' + sexClass(c.id) + (isProbable(c.id) ? ' probable' : '') + (c.focus ? ' focus' : '') + (c.kind === 'sib' ? ' sib' : '') + (c.id === selectedId ? ' selected' : ''),
          style: 'left:' + x + 'px;top:' + y + 'px', 'data-id': c.id, title: p.display_name,
          onclick: guard(function () { openPerson(c.id); }),
          ondblclick: function () { setFocus(c.id); }
        },
          el('span', { class: 'nm', text: p.display_name }),
          el('span', { class: 'yr', text: lifespan(p) || p.relation }),
          n ? el('span', { class: 'badge', title: n + ' ' + plural(n, T('комментарий'), T('комментария'), T('комментариев')), text: String(n) }) : null,
          more && !c.focus ? el('span', { class: 'more', text: '+' + more + ' ' + plural(more, T('родственник'), T('родственника'), T('родственников')) }) : null);
        cardPos[c.id] = { x: x, y: y };
      }
      host.appendChild(node);
    });

    // links: пути строятся в осях (поперёк, вдоль) и переводятся в SVG-команды
    var svg = $('links');
    svg.setAttribute('width', W);
    svg.setAttribute('height', H);
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    function path(d, cls) {
      var e = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      e.setAttribute('d', d);
      if (cls) e.setAttribute('class', cls);
      svg.appendChild(e);
    }
    function M(c, m) { return horiz ? 'M' + m + ' ' + c : 'M' + c + ' ' + m; }
    function C(c) { return (horiz ? 'V' : 'H') + c; }   // линия поперёк поколений
    function A(m) { return (horiz ? 'H' : 'V') + m; }   // линия вдоль поколений
    function cc(x) { return cs(x) + G.CS / 2; }
    // у человека с несколькими браками полки «пара → дети» на одной высоте сливаются в одну линию,
    // и дети одного брака выглядят детьми другого: перекрывающиеся полки разводим по дорожкам
    var lane = new Map();
    var byRow = {};
    // линия от пары, выходящая ровно напротив ребёнка из другого брака, сливается с его линией в одну прямую:
    // такую точку выхода сдвигаем на 10 px к своим детям (в пределах линии брака)
    var dropC = new Map();
    L.links.forEach(function (l) {
      if (l.type !== 'down') return;
      (byRow[l.row] = byRow[l.row] || []).push({ l: l });
    });
    Object.keys(byRow).forEach(function (r) {
      byRow[r].forEach(function (it) {
        var sc = cc(it.l.from);
        var clash = byRow[r].some(function (o) { return o !== it && o.l.kids.some(function (k) { return Math.abs(cc(k) - sc) < 2; }); });
        if (clash) {
          var own = it.l.kids.map(cc), mid = own.reduce(function (a, b) { return a + b; }, 0) / own.length;
          sc += mid < sc ? -10 : 10;
        }
        dropC.set(it.l, sc);
        var xs = it.l.kids.map(cc).concat([sc]);
        it.lo = Math.min.apply(null, xs); it.hi = Math.max.apply(null, xs);
      });
    });
    Object.keys(byRow).forEach(function (r) {
      // группы перекрывающихся полок; внутри группы полка, над которой стоят чужие дети,
      // уходит выше (дальше от детей) — тогда ничья линия к ребёнку её не пересекает
      var items = byRow[r].sort(function (a, b) { return a.lo - b.lo; }), group = [], end = -Infinity;
      function flush() {
        group.forEach(function (it) {
          it.score = group.filter(function (o) { return o !== it && o.l.kids.some(function (k) { var x = cc(k); return x > it.lo && x < it.hi; }); }).length;
        });
        group.sort(function (a, b) { return a.score - b.score || (a.hi - a.lo) - (b.hi - b.lo); })
          .forEach(function (it, k) { lane.set(it.l, k); });
        group = [];
      }
      items.forEach(function (it) {
        if (it.lo > end + 1) flush();
        group.push(it); end = Math.max(end, it.hi);
      });
      flush();
    });
    L.links.forEach(function (l) {
      if (l.type === 'couple') {
        var mM = ms(l.row) + G.MS / 2;
        path(M(cs(l.a) + G.CS, mM) + C(cs(l.b)), 'marr');
      } else if (l.type === 'up' || l.type === 'sibs') {
        var prow = l.type === 'up' ? l.parents[0].row : -1;
        var crow = l.type === 'up' ? l.child.row : 0;
        var ghost = l.parents.every(function (p) { return p.ghost; });
        var startC, startM;
        if (l.parents.length === 2) {
          var a = l.parents[0].x, b = l.parents[1].x, mm = ms(prow) + G.MS / 2;
          path(M(cs(a) + G.CS, mm) + C(cs(b)), 'marr' + (l.parents[0].ghost || l.parents[1].ghost ? ' ghost' : ''));
          startC = (cc(a) + cc(b)) / 2; startM = mm;
        } else {
          startC = cc(l.parents[0].x); startM = ms(prow) + G.MS;
        }
        var kids = l.type === 'up' ? [l.child.x] : l.kids;
        var mBar = ms(crow) - G.GM / 2;
        var xs = kids.map(cc);
        var lo = Math.min.apply(null, xs.concat([startC])), hi = Math.max.apply(null, xs.concat([startC]));
        path(M(startC, startM) + A(mBar) + (hi > lo ? M(lo, mBar) + C(hi) : '') + xs.map(function (x) { return M(x, mBar) + A(ms(crow)); }).join(''), ghost ? 'ghost' : '');
      } else if (l.type === 'down') {
        var sm = l.couple ? ms(l.row) + G.MS / 2 : ms(l.row) + G.MS;
        var sc = dropC.has(l) ? dropC.get(l) : cc(l.from);
        var mB = ms(l.row + 1) - G.GM / 2 - (lane.get(l) || 0) * 8;
        var kx = l.kids.map(cc);
        var lo2 = Math.min.apply(null, kx.concat([sc])), hi2 = Math.max.apply(null, kx.concat([sc]));
        path(M(sc, sm) + A(mB) + M(lo2, mB) + C(hi2) + kx.map(function (x) { return M(x, mB) + A(ms(l.row + 1)); }).join(''));
      }
    });
    var ob = $('orient');
    if (ob) { ob.innerHTML = orientIcon(horiz) + '<span>' + (horiz ? T('Вертикально') : T('Горизонтально')) + '</span>'; ob.title = horiz ? T('Предки сверху, потомки снизу') : T('Предки слева, потомки справа'); }
  }
  // значки переключателя — SVG в стиле остальных кнопок (символы ↔ ↕ системы рисуют по-разному, на iPhone — эмодзи)
  function orientIcon(vertical) {
    return '<svg class="orient-ic" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'
      + (vertical ? 'M12 4v16M8 8l4-4 4 4M8 16l4 4 4-4' : 'M4 12h16M8 8l-4 4 4 4M16 8l4 4-4 4') + '"></path></svg>';
  }
  function toggleOrient() {
    horiz = !horiz;
    store('gene.treeHoriz', horiz ? '1' : '0');
    renderTree();
    fit(true);
  }

  // ---------- pan & zoom
  var canvas, stageEl, treeDrag = { moved: false }, treeMinK = 0.25;
  function apply(animate) {
    stageEl.classList.toggle('animate', !!animate);
    stageEl.style.transform = 'translate(' + view.x + 'px,' + view.y + 'px) scale(' + view.k + ')';
  }
  function zoomAt(factor, cx, cy) {
    var k = Math.min(1.6, Math.max(treeMinK, view.k * factor));
    var f = k / view.k;
    view.x = cx - (cx - view.x) * f;
    view.y = cy - (cy - view.y) * f;
    view.k = k;
    apply(false);
  }
  // whole=true (кнопка «Вписать») — всё древо целиком, как бы мелко ни вышло;
  // иначе большое древо показывается в читаемом масштабе вокруг центрального человека.
  function fit(animate, whole) {
    var r = canvas.getBoundingClientRect();
    var w = stageEl.offsetWidth, h = stageEl.offsetHeight;
    var k = Math.min(1, (r.width - 16) / w, (r.height - 16) / h);
    treeMinK = Math.min(0.25, k);
    if (whole) k = Math.max(k, 0.05);
    else if (k < 0.55) {
      // Древо целиком не влезает: читаемый масштаб, центральный человек у края, а кадр повёрнут туда,
      // где у древа больше людей — к предкам (обычно) или к потомкам (когда в центре старший предок).
      var pos = cardPos[focusId], G = geom();
      var vm = horiz ? r.width : r.height, vc = horiz ? r.height : r.width;   // экран вдоль и поперёк поколений
      var sm = horiz ? w : h, sc = horiz ? h : w;                               // древо вдоль и поперёк
      // горизонтально — масштаб такой, чтобы по возможности уместились все поколения (вверх-вниз древо листается)
      // на телефоне — масштаб, при котором имена на карточках читаются (≈10 px), остальное листается пальцем
      var phone = r.width < 600;
      var kk = Math.max(phone ? 0.75 : 0.45, Math.min(phone ? 0.85 : 0.8, Math.max(k * 1.5, horiz ? (vm - 40) / sm : 0)));
      var pm = horiz ? pos.x : pos.y, pc = horiz ? pos.y : pos.x;
      var before = pm, after = sm - (pm + G.MS);                               // до карточки — предки, после — потомки
      var m = after > before
        ? 16 - (pm - Math.min(before, G.RS * 0.8)) * kk                         // потомков больше: человек у начала
        : vm - 24 - (pm + G.MS + Math.min(after, G.RS * (horiz ? 1.2 : 2))) * kk; // предков больше: у конца
      var c = vc / 2 - (pc + G.CS / 2) * kk;
      // не показывать пустоту за краями древа
      var clamp = function (v, view, size) { return size * kk + 32 <= view ? (view - size * kk) / 2 : Math.min(16, Math.max(v, view - 16 - size * kk)); };
      m = clamp(m, vm, sm); c = clamp(c, vc, sc);
      view.k = kk;
      view.x = horiz ? m : c;
      view.y = horiz ? c : m;
      apply(animate);
      return;
    }
    view.k = k;
    view.x = (r.width - w * k) / 2;
    view.y = (r.height - h * k) / 2;
    apply(animate);
  }
  function centerOn(id, k, animate) {
    var pos = cardPos[id];
    if (!pos) return;
    var r = canvas.getBoundingClientRect();
    view.k = k || view.k;
    view.x = r.width / 2 - (pos.x + cardW() / 2) * view.k;
    view.y = r.height / 2 - (pos.y + cardH() / 2) * view.k;
    apply(animate);
  }
  function guard(fn) { return function (e) { if (treeDrag.moved) { e.preventDefault(); return; } fn(e); }; }

  // Кнопка «Сохранить картинкой»: текущее древо перерисовывается на холст в высоком разрешении
  // (карточки, линии, пунктир вероятных) — цвета и шрифты берутся из стилей страницы.
  function saveTreeImage() {
    var stage = $('stage'), W = stage.offsetWidth, H = stage.offsetHeight, TOP = 56;
    // до 3× от экранного размера, но не больше ~16 млн точек (предел холста в Safari)
    var s = Math.max(1, Math.min(3, Math.sqrt(16e6 / (W * (H + TOP)))));
    var cv = document.createElement('canvas');
    cv.width = Math.round(W * s); cv.height = Math.round((H + TOP) * s);
    var g = cv.getContext('2d'), root = getComputedStyle(document.body);
    g.scale(s, s);
    g.fillStyle = root.backgroundColor && root.backgroundColor !== 'rgba(0, 0, 0, 0)' ? root.backgroundColor : '#fff';
    g.fillRect(0, 0, W, H + TOP);
    var head = getComputedStyle($('canvas'));
    g.fillStyle = root.color;
    g.font = '600 20px ' + root.fontFamily;
    g.textBaseline = 'top';
    var fp = P[focusId];
    g.fillText((SITE.title || document.title) + (fp ? ' — ' + fp.display_name : ''), 40, 18);
    g.font = '13px ' + head.fontFamily;
    var stamp = (SITE.base_url ? SITE.base_url.replace(/^https?:\/\//, '').replace(/\/$/, '') + ' · ' : '') + new Date().toLocaleDateString(LOCALE.locale);
    g.fillText(stamp, Math.max(40, W - 40 - g.measureText(stamp).width), 22);
    g.translate(0, TOP);
    // линии
    Array.prototype.forEach.call($('links').querySelectorAll('path'), function (p) {
      var cs = getComputedStyle(p);
      g.strokeStyle = cs.stroke;
      g.lineWidth = parseFloat(cs.strokeWidth) || 1.6;
      var dash = cs.strokeDasharray;
      g.setLineDash(dash && dash !== 'none' ? dash.split(/[\s,]+/).map(parseFloat) : []);
      g.stroke(new Path2D(p.getAttribute('d')));
    });
    g.setLineDash([]);
    function wrap(text, maxW, maxLines) {
      var words = text.split(/\s+/), lines = [], cur = '';
      words.forEach(function (w) {
        var t = cur ? cur + ' ' + w : w;
        if (cur && g.measureText(t).width > maxW) { lines.push(cur); cur = w; } else cur = t;
      });
      if (cur) lines.push(cur);
      if (lines.length > maxLines) { lines = lines.slice(0, maxLines); lines[maxLines - 1] += '…'; }
      return lines;
    }
    function fitLine(text, maxW) {
      if (g.measureText(text).width <= maxW) return text;
      while (text.length > 1 && g.measureText(text + '…').width > maxW) text = text.slice(0, -1);
      return text + '…';
    }
    // карточки
    Array.prototype.forEach.call($('cards').children, function (c) {
      var cs = getComputedStyle(c), x = c.offsetLeft, y = c.offsetTop, w = c.offsetWidth, h = c.offsetHeight;
      var r = parseFloat(cs.borderTopLeftRadius) || 0, bw = parseFloat(cs.borderTopWidth) || 0;
      g.beginPath();
      if (g.roundRect) g.roundRect(x, y, w, h, r); else g.rect(x, y, w, h);
      if (cs.backgroundColor !== 'rgba(0, 0, 0, 0)') { g.fillStyle = cs.backgroundColor; g.fill(); }
      if (bw) {
        g.lineWidth = bw; g.strokeStyle = cs.borderTopColor;
        g.setLineDash(cs.borderTopStyle === 'dashed' ? [5, 4] : []);
        g.stroke(); g.setLineDash([]);
      }
      if (c.classList.contains('focus')) {
        g.lineWidth = 3; g.strokeStyle = cs.outlineColor;
        g.beginPath();
        if (g.roundRect) g.roundRect(x - 3.5, y - 3.5, w + 7, h + 7, r + 3); else g.rect(x - 3.5, y - 3.5, w + 7, h + 7);
        g.stroke();
      }
      var padL = parseFloat(cs.paddingLeft) || 0, inner = w - padL - (parseFloat(cs.paddingRight) || 0);
      var center = cs.textAlign === 'center';
      var blocks = [];
      Array.prototype.forEach.call(c.querySelectorAll('.nm, .yr'), function (t) {
        var ts = getComputedStyle(t), lh = parseFloat(ts.lineHeight) || parseFloat(ts.fontSize) * 1.2;
        g.font = ts.fontWeight + ' ' + ts.fontSize + ' ' + ts.fontFamily;
        var lines = ts.whiteSpace === 'nowrap' ? [fitLine(t.textContent, inner)] : wrap(t.textContent, inner, Math.max(1, Math.floor((h - 8) / lh) - 1));
        blocks.push({ font: g.font, color: ts.color, lines: lines, lh: lh });
      });
      var total = blocks.reduce(function (a, b) { return a + b.lines.length * b.lh; }, 0);
      var ty = y + (h - total) / 2;
      g.textBaseline = 'middle';
      blocks.forEach(function (b) {
        g.font = b.font; g.fillStyle = b.color;
        b.lines.forEach(function (line) {
          var tw = g.measureText(line).width;
          g.fillText(line, center ? x + (w - tw) / 2 : x + padL, ty + b.lh / 2);
          ty += b.lh;
        });
      });
      if (c.classList.contains('probable')) {
        g.font = '700 13px ' + root.fontFamily; g.fillStyle = cs.getPropertyValue('--accent') || '#a0522d';
        g.fillText('≈', x + w - 16, y + 11);
      }
    });
    var name = 'drevo-' + (fp ? fp.id : 'family') + '.png';
    cv.toBlob(function (blob) {
      if (!blob) return;
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = name;
      document.body.appendChild(a);
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
    }, 'image/png');
  }

  // Жесты холста: палец/мышь — сдвиг, два пальца — щипок, колесо и тачпад.
  // Опорная точка жеста пересчитывается при каждой смене числа пальцев (иначе после щипка картинка прыгает),
  // а перерисовка идёт не чаще кадра экрана.
  function gestures(cv, v, draw, minK, st) {
    var pts = {}, base = null, raf = 0;
    var mk = typeof minK === 'function' ? minK : function () { return minK; };
    function frame() { if (!raf) raf = requestAnimationFrame(function () { raf = 0; draw(); }); }
    function snapshot() {
      var ids = Object.keys(pts);
      if (!ids.length) return null;
      var a = pts[ids[0]], b = pts[ids[1]] || a, r = cv.getBoundingClientRect();
      return { x: (a.x + b.x) / 2 - r.left, y: (a.y + b.y) / 2 - r.top, d: Math.hypot(a.x - b.x, a.y - b.y) || 1, two: ids.length > 1 };
    }
    function rebase() { var g = snapshot(); base = g && { g: g, vx: v.x, vy: v.y, k: v.k }; }
    function startDrag(e) {
      if (e.pointerId !== undefined) try { cv.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      if (!st.moved) { st.moved = true; cv.classList.add('dragging'); }
    }
    // Палец на телефоне — через touch-события: в Safari на iPhone захват указателя при начале сдвига
    // шлёт lostpointercapture/pointercancel, и древо, чуть сдвинувшись, замирает. Мышь и перо — через pointer-события.
    var touchUI = 'ontouchstart' in window;
    function own(e) { return !(touchUI && e.pointerType === 'touch'); }
    function begin() { if (!Object.keys(pts).length) st.moved = false; }
    function moveTo(e) {
      var g = snapshot(), b = base.g;
      if (b.two && g.two) {
        var k = Math.min(1.6, Math.max(mk(), base.k * g.d / b.d)), f = k / base.k;
        v.x = g.x - (b.x - base.vx) * f;
        v.y = g.y - (b.y - base.vy) * f;
        v.k = k;
      } else {
        var dx = g.x - b.x, dy = g.y - b.y;
        if (!st.moved && Math.hypot(dx, dy) < 6) return;
        startDrag(e);
        v.x = base.vx + dx; v.y = base.vy + dy;
      }
      frame();
    }
    function finish() {
      rebase();
      if (!base) { cv.classList.remove('dragging'); setTimeout(function () { st.moved = false; }, 0); }
    }
    cv.addEventListener('pointerdown', function (e) {
      if (!own(e) || (e.pointerType === 'mouse' && e.button !== 0)) return;
      // мышь: без этого браузер начинает выделять текст карточек и «тащить» картинки — древо скачет
      if (e.pointerType === 'mouse') e.preventDefault();
      begin();
      pts[e.pointerId] = { x: e.clientX, y: e.clientY };
      rebase();
      if (base.g.two) Object.keys(pts).forEach(function (id) { startDrag({ pointerId: +id }); });
    });
    cv.addEventListener('pointermove', function (e) {
      if (!own(e) || !pts[e.pointerId] || !base) return;
      pts[e.pointerId] = { x: e.clientX, y: e.clientY };
      e.preventDefault();
      moveTo(e);
    });
    function end(e) {
      if (!own(e) || !pts[e.pointerId]) return;
      // lostpointercapture всплывает от карточки, у которой холст забрал захват, — это не конец жеста
      if (e.type === 'lostpointercapture' && e.target !== cv) return;
      delete pts[e.pointerId];
      finish();
    }
    cv.addEventListener('pointerup', end);
    cv.addEventListener('pointercancel', end);
    cv.addEventListener('lostpointercapture', end);
    function syncTouches(list) {
      pts = {};
      for (var i = 0; i < list.length; i++) pts['t' + list[i].identifier] = { x: list[i].clientX, y: list[i].clientY };
    }
    cv.addEventListener('touchstart', function (e) {
      begin();
      syncTouches(e.touches);
      rebase();
      if (base && base.g.two) startDrag({});
    }, { passive: true });
    // preventDefault на touchmove: страница не прокручивается и Safari не забирает жест себе.
    // На touchstart его нет — иначе короткий тап не откроет карточку.
    cv.addEventListener('touchmove', function (e) {
      if (e.cancelable) e.preventDefault();
      if (!base) return;
      var before = Object.keys(pts).length;
      syncTouches(e.touches);
      if (Object.keys(pts).length !== before) { rebase(); return; }
      moveTo({});
    }, { passive: false });
    function touchEnd(e) { syncTouches(e.touches); finish(); }
    cv.addEventListener('touchend', touchEnd);
    cv.addEventListener('touchcancel', touchEnd);
    var idle = 0;
    cv.addEventListener('wheel', function (e) {
      e.preventDefault();
      // на время прокрутки и щипка тачпадом древо живёт на отдельном слое видеокарты (как при перетаскивании):
      // иначе Chrome на каждом кадре заново рисует все карточки; после жеста слой снимается, чтобы текст был чётким
      cv.classList.add('moving');
      clearTimeout(idle);
      idle = setTimeout(function () { cv.classList.remove('moving'); }, 200);
      var r = cv.getBoundingClientRect();
      if (e.ctrlKey || e.metaKey) {
        var k = Math.min(1.6, Math.max(mk(), v.k * Math.exp(-e.deltaY * 0.01))), f = k / v.k, cx = e.clientX - r.left, cy = e.clientY - r.top;
        v.x = cx - (cx - v.x) * f; v.y = cy - (cy - v.y) * f; v.k = k;
      } else { v.x -= e.deltaX; v.y -= e.deltaY; }
      frame();
    }, { passive: false });
    cv.addEventListener('dragstart', function (e) { e.preventDefault(); });
    // жест Safari «щипок» на тачпаде Mac не должен масштабировать всю страницу
    cv.addEventListener('gesturestart', function (e) { e.preventDefault(); });
  }

  function initPanZoom() {
    canvas = $('canvas'); stageEl = $('stage');
    gestures(canvas, view, function () { apply(false); }, function () { return treeMinK; }, treeDrag);
    $('zoom-in').onclick = function () { var r = canvas.getBoundingClientRect(); zoomAt(1.25, r.width / 2, r.height / 2); };
    $('zoom-out').onclick = function () { var r = canvas.getBoundingClientRect(); zoomAt(0.8, r.width / 2, r.height / 2); };
    $('zoom-fit').onclick = function () { fit(true, true); };
    $('zoom-save').onclick = saveTreeImage;
    // На телефоне адресная строка прячется при прокрутке и шлёт resize по высоте — это не повод сдвигать древо.
    var lastW = window.innerWidth;
    window.addEventListener('resize', function () {
      if (window.innerWidth === lastW) return;
      lastW = window.innerWidth;
      if (currentView === 'tree') centerOn(focusId, null, false);
    });
    $('orient').onclick = toggleOrient;
    // На телефоне ветви и фамилии прячутся под кнопку и открываются поверх древа.
    $('branches-toggle').onclick = function () {
      var open = !document.querySelector('.tree-side').classList.contains('open');
      document.querySelector('.tree-side').classList.toggle('open', open);
      this.setAttribute('aria-expanded', String(open));
    };
    $('canvas').addEventListener('pointerdown', function () {
      var side = document.querySelector('.tree-side');
      if (side.classList.contains('open')) { side.classList.remove('open'); $('branches-toggle').setAttribute('aria-expanded', 'false'); }
    });
    $('branches').addEventListener('click', function (e) {
      if (e.target.closest('button') && window.matchMedia('(max-width: 720px)').matches) {
        document.querySelector('.tree-side').classList.remove('open'); $('branches-toggle').setAttribute('aria-expanded', 'false');
      }
    });
  }

  function setFocus(id, opts) {
    focusId = id;
    lineKey = null; line = null;
    var g = opts && opts.line ? surnameGroups().filter(function (x) { return x.key === opts.line; })[0] : null;
    if (g) { lineKey = g.key; line = {}; g.ids.forEach(function (x) { line[x] = true; }); }
    renderTree();
    if (!opts || !opts.keepView) fit(true);
    syncUrl();
  }
  // ---------- person panel
  function srcChip(id) {
    var s = S[id];
    if (!s) return null;
    return el('button', { class: 'src', title: s.title, text: id, onclick: function () { showSource(id); } });
  }
  // Текст записи с кнопками документов: «(S27, S136)» — только кнопки, без скобок, одной неразрывной группой
  function noteText(n) {
    var out = [];
    n.split(/\s*\(((?:S\d+[,;\s]*)+)\)/g).forEach(function (part, i) {
      if (i % 2) {
        var ids = part.match(/S\d+/g).filter(function (x) { return S[x]; });
        if (ids.length) out.push(' ', el('span', { class: 'src-group' }, ids.map(srcChip)));
        return;
      }
      part.split(/(\bS\d+\b)/g).forEach(function (t) { out.push(S[t] ? srcChip(t) : t); });
    });
    return out;
  }
  function personChip(id, note) {
    var p = P[id];
    return el('button', { class: 'chip', onclick: function () { openPerson(id); } }, p.display_name, lifespan(p) ? el('small', { text: lifespan(p) }) : null, note ? el('small', { text: note }) : null);
  }
  function eventText(ev) {
    var parts = [];
    if (ev.date) parts.push(fmtDate(ev.date));
    // номер документа в тексте места («повторное свидетельство, S232») уже стоит кнопкой рядом — из текста убираем
    if (ev.place_as_recorded) parts.push(ev.place_as_recorded.replace(/,?\s*\bS\d+\b/g, '').replace(/\(\s*\)/g, '').replace(/\s+\)/g, ')').trim());
    return [parts.join(', ') || T('дата неизвестна'), ' '].concat((ev.source_ids || []).map(srcChip));
  }
  function personSources(p) {
    var ids = [];
    function collect(value) {
      if (typeof value === 'string') {
        (value.match(/\bS\d+\b/g) || []).forEach(function (id) { if (S[id] && ids.indexOf(id) < 0) ids.push(id); });
      } else if (Array.isArray(value)) value.forEach(collect);
      else if (value && typeof value === 'object') Object.keys(value).forEach(function (key) { collect(value[key]); });
    }
    collect(p);
    (spouseFams[p.id] || []).forEach(function (f) { collect(f.source_ids); collect(f.marriage); });
    if (parentFam[p.id]) collect(parentFam[p.id].source_ids);
    return ids.sort(function (a, b) { return Number(a.slice(1)) - Number(b.slice(1)); });
  }
  function thumbs(ids) {
    var files = ids.map(function (id) { return S[id]; }).filter(function (s) { return s.file; });
    if (!files.length) return null;
    return el('div', { class: 'thumbs' }, files.map(function (s) {
      if (/\.(jpe?g|png)$/i.test(s.file) || s.thumb) {
        // PDF с превью — как фотография, с меткой «PDF» в углу
        return el('button', { class: /\.pdf$/i.test(s.file) ? 'is-pdf' : null, title: s.title, onclick: function () { openDoc(s.id); } }, el('img', { src: s.thumb || s.file, alt: s.title, loading: 'lazy' }));
      }
      return el('a', { class: 'pdf', href: s.file, target: '_blank', rel: 'noopener', title: s.title, text: 'PDF · ' + s.id });
    }));
  }

  function openPerson(id, opts) {
    opts = opts || {};
    var p = P[id];
    selectedId = id;
    selectedPlace = null;
    document.querySelectorAll('.card.selected').forEach(function (c) { c.classList.remove('selected'); });
    var cardEl = document.querySelector('.card[data-id="' + id + '"]');
    if (cardEl) cardEl.classList.add('selected');

    var body = clear($('panel-body'));
    body.appendChild(el('p', { class: 'p-rel', text: p.relation ? T('Родство: ') + p.relation : '' }));
    body.appendChild(el('h2', { class: 'p-name', text: p.display_name }));
    // вариант имени, все слова которого уже есть в заголовке («Иванова Анна Петровна» при «Петрова (Иванова) Анна…»), не повторяем
    var titleWords = p.display_name.toLowerCase().replace(/[()]/g, ' ').split(/\s+/);
    var aliases = (p.aliases || []).filter(function (a) { return a.toLowerCase().replace(/[()]/g, ' ').split(/\s+/).filter(Boolean).some(function (w) { return titleWords.indexOf(w) < 0; }); });
    if (aliases.length) body.appendChild(el('p', { class: 'p-alias', text: T('Также: ') + aliases.join('; ') }));
    if (p.profiles && p.profiles.length) body.appendChild(el('p', { class: 'p-alias' }, T('Профиль: '), p.profiles.map(function (x, i) {
      return [i ? ', ' : '', el('a', { href: x.url, target: '_blank', rel: 'noopener noreferrer', text: x.site }), x.match === 'вероятно' ? T(' (сопоставлено по имени, проверьте)') : ''];
    })));
    body.appendChild(el('div', { class: 'p-actions' },
      id !== focusId ? el('button', { class: 'btn primary', text: T('Поставить в центр древа'), onclick: function () { showView('tree'); setFocus(id); } }) : el('span', { class: 'btn', text: T('Сейчас в центре древа') }),
      (D.bios || []).indexOf(id) >= 0 ? el('button', { class: 'btn', text: T('Биография'), onclick: function () { openBio(id); } }) : null,
      el('button', { class: 'btn', text: T('Добавить сведения'), onclick: function () { var t = body.querySelector('textarea'); if (t) { t.scrollIntoView({ behavior: 'smooth', block: 'center' }); t.focus({ preventScroll: true }); } } }),
      el('button', { class: 'btn', text: T('Поделиться'), title: T('Ссылка на эту карточку — с именем и фото в превью'), onclick: function (e) { shareLink(e.currentTarget, id); } })));

    var facts = el('dl', { class: 'facts' });
    function fact(label, value) { facts.appendChild(el('dt', { text: label })); facts.appendChild(el('dd', null, value)); }
    if (p.birth && (p.birth.date || p.birth.place_as_recorded)) fact(T('Рождение'), eventText(p.birth));
    (p.birth_alternatives || []).forEach(function (a) { fact(T('Рождение (по другому документу)'), eventText(a)); });
    if (p.death && p.death.date) fact(T('Смерть'), eventText(p.death));
    (spouseFams[id] || []).forEach(function (f) {
      if (f.marriage) {
        var other = f.partners.filter(function (x) { return x !== id; })[0];
        fact(T('Брак') + (other ? T(' с ') + P[other].given_names.split(' ')[0] : ''), eventText(f.marriage));
      }
    });
    // все места жизни — одним блоком, глагол по полу человека
    if ((p.residences || []).length) fact(p.sex === 'F' ? T('Жила') : p.sex === 'M' ? T('Жил') : T('Жил(а)'), el('ul', { class: 'lived-list' }, p.residences.map(function (r) {
      return el('li', null, [r.place, r.date ? ' · ' + r.date : '', r.note ? ' — ' + r.note : '']);
    })));
    if (!facts.childNodes.length) fact(T('Даты'), el('span', { class: 'empty', text: T('пока неизвестны — подскажите, если знаете') }));
    body.appendChild(facts);

    body.appendChild(el('h3', { class: 'p-sec', text: T('Семья') }));
    var fam = el('dl', { class: 'facts' });
    function relRow(label, ids, empty) {
      fam.appendChild(el('dt', { text: label }));
      fam.appendChild(el('dd', null, ids.length ? el('div', { class: 'rel-chips' }, ids.map(function (x) { return personChip(x); })) : el('span', { class: 'empty', text: empty })));
    }
    relRow(T('Родители'), parentsOf(id), T('не установлены'));
    if (parentsProbable(id)) fam.appendChild(el('dd', { class: 'probable-note' }, el('b', { text: P[id].research_status === 'unlinked_candidate' ? T('≈ Возможная родня. ') : T('≈ Вероятная связь. ') }), probableNote(id)));
    var sibs = siblingsOf(id);
    if (sibs.length) relRow(T('Братья и сёстры'), sibs);
    var sps = spousesOf(id);
    if (sps.length) relRow(T('Супруги'), sps);
    var kids = childrenOf(id);
    if (kids.length) relRow(T('Дети'), kids);
    body.appendChild(fam);
    body.appendChild(el('h3', { class: 'p-sec', text: T('Как мы связаны') }));
    body.appendChild(kinBlock(id));

    if (p.notes && p.notes.length) {
      body.appendChild(el('h3', { class: 'p-sec', text: T('Что известно') }));
      body.appendChild(el('ul', { class: 'notes' }, p.notes.map(function (n) {
        return el('li', null, noteText(n));
      })));
    }
    var srcIds = personSources(p);
    if (srcIds.length) {
      body.appendChild(el('h3', { class: 'p-sec', text: T('Документы и источники') }));
      // сразу видны только первые снимки; полный список свёрнут, чтобы до комментариев было близко
      var withFile = srcIds.filter(function (id) { return S[id].file; });
      var th = thumbs(withFile.slice(0, 6));
      if (th) body.appendChild(th);
      var more = el('details', { class: 'src-more' }, el('summary', { text: T('Все документы и источники · ') + srcIds.length }));
      body.appendChild(more);
      var thRest = thumbs(withFile.slice(6));
      if (thRest) more.appendChild(thRest);
      more.appendChild(el('ul', { class: 'person-sources' }, srcIds.map(function (id) {
        var s = S[id], links = [];
        if (s.url) links.push(el('a', { href: s.url, target: '_blank', rel: 'noopener', text: T('Оригинал') }));
        if (s.file) links.push(el('a', { href: s.file, target: '_blank', rel: 'noopener', text: T('Сохранённая копия') }));
        return el('li', null, srcChip(id), ' ', el('span', { text: s.title }),
          s.locator ? el('p', { class: 'where', text: s.locator }) : null,
          links.length ? el('p', { class: 'doc-links' }, links.map(function (link, i) { return [i ? ' · ' : '', link]; })) : null);
      })));
    }

    body.appendChild(el('h3', { class: 'p-sec cm', text: T('Комментарии и уточнения') }));
    var list = el('div', { class: 'comments' });
    body.appendChild(list);
    renderCommentList(list, byPerson[id] || [], T('Пока никто ничего не добавил. Помните что-то о ') + (p.sex === 'F' ? T('ней') : p.sex === 'M' ? T('нём') : T('этом человеке')) + T('? Даты, места, истории, фотографии — всё пригодится.'));
    body.appendChild(commentForm(id, opts.placeholder));
    body.appendChild(proposalForm(id));

    var panel = $('panel');
    panel.classList.add('open');
    panel.setAttribute('aria-hidden', 'false');
    panel.scrollTop = 0;
    if (window.matchMedia('(max-width: 720px)').matches) $('scrim').hidden = false;
    syncUrl();
    if (opts.compose) setTimeout(function () { var t = body.querySelector('textarea'); if (t) { t.scrollIntoView({ block: 'center' }); t.focus({ preventScroll: true }); } }, 260);
  }
  function closePanel() {
    $('panel').classList.remove('open');
    $('panel').setAttribute('aria-hidden', 'true');
    $('scrim').hidden = true;
    selectedId = null;
    selectedPlace = null;
    document.querySelectorAll('.card.selected').forEach(function (c) { c.classList.remove('selected'); });
    syncUrl();
  }

  // ---------- kinship: «Как мы связаны» (start; tests/test_engine.py runs this block in node)
  // g: { parents(id) → [ids], spouses(id) → [ids], children(id) → [ids], sex(id) → 'M'|'F'|'U',
  //      sameParents(a, b) → bool, probable(child) → bool (link to own parents not proven) }
  var Kinship = (function () {
    function ancestors(g, id) {   // id → {ancestor: [generations up, child on the way down]}
      var out = {}, todo = [[id, 0, null]];
      out[id] = [0, null];
      while (todo.length) {
        var cur = todo.shift();
        g.parents(cur[0]).forEach(function (p) { if (!(p in out)) { out[p] = [cur[1] + 1, cur[0]]; todo.push([p, cur[1] + 1, cur[0]]); } });
      }
      return out;
    }
    function chainUp(anc, from, to) {   // from … to, following the stored child links back down
      var ids = [to];
      while (to !== from) { to = anc[to][1]; ids.unshift(to); }
      return ids;
    }
    // blood relation: generations from a up to the nearest common ancestor and from it down to b
    function blood(g, a, b) {
      if (a === b) return null;
      var A = ancestors(g, a), B = ancestors(g, b), best = null;
      Object.keys(A).forEach(function (x) {
        if (!(x in B)) return;
        var d = A[x][0] + B[x][0];
        if (!best || d < best.d) best = { d: d, ca: x, up: A[x][0], down: B[x][0] };
      });
      if (!best) return null;
      var path = chainUp(A, a, best.ca).concat(chainUp(B, b, best.ca).reverse().slice(1));
      var probable = path.some(function (x, i) { var n = path[i + 1]; return n != null && (g.parents(x).indexOf(n) >= 0 ? g.probable(x) : g.probable(n)); });
      var half = best.up === 1 && best.down === 1 && !g.sameParents(a, b);
      return { type: 'blood', up: best.up, down: best.down, ca: best.ca, path: path, probable: probable, half: half };
    }
    function relation(g, a, b) {
      if (a === b) return { type: 'self', path: [a] };
      var r = blood(g, a, b);
      if (r) return r;
      if (g.spouses(a).indexOf(b) >= 0) return { type: 'spouse', path: [a, b] };
      var best = null;
      g.spouses(b).forEach(function (s) { var k = blood(g, a, s); if (k && (!best || k.up + k.down < best.rel.up + best.rel.down)) best = { type: 'spouse_of', via: s, rel: k, path: k.path.concat([b]) }; });
      g.spouses(a).forEach(function (s) { var k = blood(g, s, b); if (k && (!best || k.up + k.down < best.rel.up + best.rel.down)) best = { type: 'of_spouse', via: s, rel: k, path: [a].concat(k.path) }; });
      if (best) return best;
      // anything else: the shortest chain through parents, children and spouses
      var prev = {}, todo = [a];
      prev[a] = null;
      while (todo.length) {
        var x = todo.shift();
        if (x === b) break;
        g.parents(x).concat(g.children(x), g.spouses(x)).forEach(function (y) { if (!(y in prev)) { prev[y] = x; todo.push(y); } });
      }
      if (!(b in prev)) return { type: 'none', path: [] };
      var path = [b];
      while (prev[path[0]] != null) path.unshift(prev[path[0]]);
      return { type: 'chain', path: path };
    }
    // what y is to x, one step: 'parent' | 'child' | 'spouse'
    function step(g, x, y) { return g.parents(x).indexOf(y) >= 0 ? 'parent' : g.children(x).indexOf(y) >= 0 ? 'child' : 'spouse'; }

    // ----- names of relations: what b is to a; sex of b
    function rep(s, n) { return n > 0 ? new Array(n + 1).join(s) : ''; }
    var RU_ADJ = ['', 'двоюродн', 'троюродн', 'четвероюродн', 'пятиюродн', 'шестиюродн', 'семиюродн', 'восьмиюродн'];
    function ruAdj(i, sex) {
      var stem = RU_ADJ[i] || ((i + 1) + '-юродн');
      return stem + (sex === 'F' ? 'ая ' : sex === 'M' ? 'ый ' : 'ый(ая) ');
    }
    function ru(up, down, sex, half, parentSex) {
      var w = function (m, f) { return sex === 'M' ? m : sex === 'F' ? f : m + ' / ' + f; };
      if (down === 0) {
        if (up === 1) return w('отец', 'мать');
        if (up === 2) return w('дед', 'бабушка');
        return rep('пра', up - 2) + w('дед', 'бабушка').replace(/(^|\/ )/g, '$1' + rep('пра', up - 2)).slice((up - 2) * 3);
      }
      if (up === 0) {
        if (down === 1) return w('сын', 'дочь');
        return rep('пра', down - 2) + w('внук', 'внучка').replace(/\/ /, '/ ' + rep('пра', down - 2));
      }
      var k = Math.min(up, down) - 1, r = Math.abs(up - down);
      if (r === 0) {
        if (k === 0) return half ? (parentSex === 'M' ? w('единокровный брат', 'единокровная сестра') : parentSex === 'F' ? w('единоутробный брат', 'единоутробная сестра') : w('брат по одному из родителей', 'сестра по одному из родителей')) : w('брат', 'сестра');
        return ruAdj(k, sex) + w('брат', 'сестра');
      }
      if (up > down) {   // b is of an older generation: uncle, great-uncle…
        var noun = r === 1 ? w('дядя', 'тётя') : r === 2 ? w('дед', 'бабушка') : w(rep('пра', r - 2) + 'дед', rep('пра', r - 2) + 'бабушка');
        var i = k + (r >= 2 ? 1 : 0);   // брат деда — двоюродный дед, двоюродный брат деда — троюродный
        return i ? ruAdj(i, sex) + noun : noun;
      }
      var pre = r === 1 ? '' : r === 2 ? 'внучат' : rep('пра', r - 3) + 'правнучат';
      var nephew = pre ? w(pre + 'ый племянник', pre + 'ая племянница') : w('племянник', 'племянница');
      return k ? ruAdj(k, sex) + nephew : nephew;
    }
    var EN_ORD = ['', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth'];
    function en(up, down, sex, half) {
      var w = function (m, f, u) { return sex === 'M' ? m : sex === 'F' ? f : u; };
      var great = function (n) { return rep('great-', n); };
      if (down === 0) return up === 1 ? w('father', 'mother', 'parent') : great(up - 2) + w('grandfather', 'grandmother', 'grandparent');
      if (up === 0) return down === 1 ? w('son', 'daughter', 'child') : great(down - 2) + w('grandson', 'granddaughter', 'grandchild');
      var k = Math.min(up, down) - 1, r = Math.abs(up - down);
      if (k === 0) {
        if (r === 0) return (half ? 'half-' : '') + w('brother', 'sister', 'sibling');
        if (up > down) return w(great(r - 1) + 'uncle', great(r - 1) + 'aunt', great(r - 1) + 'uncle or ' + great(r - 1) + 'aunt');
        return w(great(r - 1) + 'nephew', great(r - 1) + 'niece', great(r - 1) + 'nephew or ' + great(r - 1) + 'niece');
      }
      var times = ['', 'once', 'twice', 'three times', 'four times', 'five times'][r] || r + ' times';
      return (EN_ORD[k] || k + 'th') + ' cousin' + (r ? ' ' + times + ' removed' : '');
    }
    function ro(up, down, sex, half) {
      var w = function (m, f) { return sex === 'M' ? m : sex === 'F' ? f : m + ' / ' + f; };
      var stra = function (n) { return rep('stră', n); };
      if (down === 0) return up === 1 ? w('tată', 'mamă') : stra(up - 2) + w('bunic', 'bunică').replace('/ ', '/ ' + stra(up - 2));
      if (up === 0) return down === 1 ? w('fiu', 'fiică') : stra(down - 2) + w('nepot', 'nepoată').replace('/ ', '/ ' + stra(down - 2));
      var k = Math.min(up, down) - 1, r = Math.abs(up - down);
      if (k === 0) {
        if (r === 0) return w('frate', 'soră') + (half ? ' (după un singur părinte)' : '');
        if (up > down) return r === 1 ? w('unchi', 'mătușă') : w('fratele', 'sora') + ' ' + stra(r - 2) + 'bunicului';
        return r === 1 ? w('nepot de frate', 'nepoată de frate') : stra(r - 1) + w('nepot de frate', 'nepoată de frate').replace('/ ', '/ ' + stra(r - 1));
      }
      var cousin = k === 1 ? w('văr primar', 'vară primară') : w('văr de gradul ', 'vară de gradul ').replace(/ \//, ' ' + (k) + ' /') + (sex === 'M' || sex === 'F' ? k : '');
      if (sex !== 'M' && sex !== 'F' && k > 1) cousin = 'văr / vară de gradul ' + k;
      return cousin + (r ? ', cu ' + r + (r === 1 ? ' generație' : ' generații') + (up > down ? ' mai sus' : ' mai jos') : '');
    }
    function name(lang, up, down, sex, half, parentSex) {
      return (lang === 'en' ? en : lang === 'ro' ? ro : ru)(up, down, sex, half, parentSex);
    }
    return { relation: relation, step: step, name: name };
  })();
  // ---------- kinship (end)

  var kinGraph = {
    parents: parentsOf, spouses: spousesOf, children: childrenOf,
    sex: function (x) { return P[x].sex; },
    sameParents: function (a, b) { return !!parentFam[a] && parentFam[a] === parentFam[b]; },
    probable: function (x) { return parentsProbable(x); }
  };
  function stepWord(kind, sex) {
    var w = { parent: [T('отец'), T('мать'), T('родитель')], child: [T('сын'), T('дочь'), T('ребёнок')], spouse: [T('муж'), T('жена'), T('супруг(а)')] }[kind];
    return sex === 'M' ? w[0] : sex === 'F' ? w[1] : w[2];
  }
  // what b is to a, in the site language
  function kinText(a, b) {
    var r = Kinship.relation(kinGraph, a, b), lang = LOCALE.lang;
    var name = function (k, sex, x) { return Kinship.name(lang, k.up, k.down, sex, k.half, k.half ? P[k.ca].sex : null) + (x || ''); };
    var text = r.type === 'self' ? T('это тот же человек')
      : r.type === 'blood' ? name(r, P[b].sex)
      : r.type === 'spouse' ? stepWord('spouse', P[b].sex)
      : r.type === 'spouse_of' ? stepWord('spouse', P[b].sex) + ' · ' + P[r.via].display_name + ' — ' + name(r.rel, P[r.via].sex)
      : r.type === 'of_spouse' ? name(r.rel, P[b].sex) + ' · ' + T('по линии супруга: ') + P[r.via].display_name
      : r.type === 'chain' ? T('свойственник (родство через браки)') : T('связь в древе не найдена');
    var probable = r.probable || (r.rel && r.rel.probable);
    return { text: text + (probable ? T(' — вероятно: одно из звеньев не доказано') : ''), path: r.path };
  }
  function kinBlock(id) {
    var box = el('div', { class: 'kin' });
    var labels = {}, opts = el('datalist', { id: 'kin-people' });
    D.people.forEach(function (p) {
      var l = p.display_name + (lifespan(p) ? ' (' + lifespan(p) + ')' : '');
      if (labels[l]) l += ' · ' + p.id;
      labels[l] = p.id;
      opts.appendChild(el('option', { value: l }));
    });
    var other = id !== D.root_person_id ? D.root_person_id : (focusId && focusId !== id ? focusId : null);
    var input = el('input', { type: 'text', list: 'kin-people', 'aria-label': T('С кем сравнить'), placeholder: T('Выберите человека…') });
    var out = el('div', { class: 'kin-out' });
    function show(a) {
      clear(out);
      if (!a || !P[a]) return;
      input.value = Object.keys(labels).filter(function (l) { return labels[l] === a; })[0] || '';
      var k = kinText(a, id);
      out.appendChild(el('p', { class: 'kin-res' }, el('b', { text: P[id].display_name }), ' — ', el('b', { class: 'kin-term', text: k.text }), ' ', T('для'), ' ', personChip(a)));
      if (k.path.length > 2) {
        var steps = el('p', { class: 'kin-path' }, el('span', { class: 'kin-lbl', text: T('Цепочка: ') }));
        k.path.forEach(function (x, i) {
          if (i) steps.appendChild(el('span', { class: 'kin-arrow', text: ' → ' + stepWord(Kinship.step(kinGraph, k.path[i - 1], x), P[x].sex) + ': ' }));
          steps.appendChild(el('a', { href: '#/tree/' + x + '?person=' + x, text: P[x].display_name, onclick: function (e) { e.preventDefault(); openPerson(x); } }));
        });
        out.appendChild(steps);
      }
    }
    input.addEventListener('change', function () { show(labels[input.value]); });
    box.appendChild(el('label', { class: 'kin-q' }, T('Кем приходится для:'), ' ', input));
    box.appendChild(opts);
    box.appendChild(out);
    show(other);
    return box;
  }

  // ---------- comments
  function renderCommentList(host, items, emptyText, withAbout) {
    clear(host);
    if (!SITE.comments) return;
    if (!items.length) { host.appendChild(el('p', { class: 'empty', text: emptyText })); return; }
    items.forEach(function (c) {
      var about = null;
      if (withAbout) {
        about = c.person_id === 'general' ? el('span', { class: 'about', text: T('· общее') })
          : P[c.person_id] ? el('span', { class: 'about' }, T('· о '), el('a', { href: '#/tree/' + c.person_id + '?person=' + c.person_id, text: P[c.person_id].display_name, onclick: function (e) { e.preventDefault(); openPerson(c.person_id); } }))
          : S[c.person_id] ? el('span', { class: 'about' }, S[c.person_id].kind === 'family_photo' ? T('· о снимке ') : T('· о документе '), el('a', { href: '#/sources?doc=' + c.person_id, text: S[c.person_id].title, onclick: function (e) { e.preventDefault(); showSource(c.person_id); } })) : null;
      }
      host.appendChild(el('div', { class: 'comment' },
        el('div', { class: 'meta' }, el('b', { text: c.author }), el('span', { text: fmtStamp(c.created_at) }), about),
        el('div', { class: 'body', text: c.text }),
        c.processed_at ? el('div', { class: 'done' }, el('b', { text: T('✓ Учтено ') + fmtDate(c.processed_at.slice(0, 10)) }), c.processed_note ? ' — ' + c.processed_note : '') : null));
    });
  }
  function commentForm(personId, placeholder) {
    if (!SITE.comments) return el('span');
    var name = el('input', { type: 'text', maxlength: '80', placeholder: T('Ваше имя (например, тётя Анна)'), required: true, value: store('gene-author') || '' });
    var text = el('textarea', { maxlength: '4000', required: true, placeholder: placeholder || T('Что вы знаете или помните? Можно исправить ошибку, дописать даты, места, истории.') });
    var status = el('span', { class: 'status' });
    // hidden field: people never see it, bots fill it in — such comments are kept hidden
    var trap = el('input', { type: 'text', name: 'website', class: 'hp', tabindex: '-1', autocomplete: 'off', 'aria-hidden': 'true' });
    var btn = el('button', { type: 'submit', text: T('Отправить') });
    var form = el('form', { class: 'cform', onsubmit: function (e) {
      e.preventDefault();
      var author = name.value.trim(), t = text.value.trim();
      if (!author || !t) { status.className = 'status err'; status.textContent = T('Укажите имя и текст.'); return; }
      btn.disabled = true; status.className = 'status'; status.textContent = T('Отправляю…');
      fetch(ROOT + 'api/comments', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-Gene-Client': '1' }, body: JSON.stringify({ person_id: personId, author: author, text: t, website: trap.value }) })
        .then(function (r) {
          if (r.status === 401) { location.reload(); throw new Error(T('Нужно снова ввести PIN.')); }
          return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || T('Ошибка ') + r.status); return j; });
        })
        .then(function (c) {
          store('gene-author', author);
          if (c.pending) { text.value = ''; status.textContent = T('Спасибо! Комментарий появится после проверки.'); return; }
          comments.push(c);
          groupComments();
          text.value = '';
          status.textContent = T('Спасибо! Комментарий сохранён.');
          refreshAfterComment(personId);
        })
        .catch(function (err) { status.className = 'status err'; status.textContent = err.message || T('Не удалось отправить. Проверьте интернет и попробуйте ещё раз.'); })
        .then(function () { btn.disabled = false; });
    } }, name, text, trap, el('div', { class: 'row' }, status, btn));
    return form;
  }
  // «Предложить исправление»: структурированная правка уходит администратору в редактор (gene serve --editor)
  var canPropose = false;
  function proposalForm(personId) {
    var fieldSel = el('select', { 'aria-label': T('Что исправить') }, [['birth.date', T('Дата рождения')], ['birth.place', T('Место рождения')], ['death.date', T('Дата смерти')],
      ['death.place', T('Место смерти')], ['display_name', T('Имя')], ['other', T('Другое')]].map(function (o) { return el('option', { value: o[0], text: o[1] }); }));
    var value = el('input', { type: 'text', maxlength: '500', placeholder: T('Как правильно (например, 12.03.1899)') });
    var note = el('textarea', { maxlength: '4000', placeholder: T('Откуда это известно? Документ, рассказ, фотография…') });
    var name = el('input', { type: 'text', maxlength: '80', placeholder: T('Ваше имя (например, тётя Анна)'), required: true, value: store('gene-author') || '' });
    var trap = el('input', { type: 'text', name: 'website', class: 'hp', tabindex: '-1', autocomplete: 'off', 'aria-hidden': 'true' });
    var status = el('span', { class: 'status' });
    var btn = el('button', { type: 'submit', text: T('Отправить') });
    var form = el('form', { class: 'cform', onsubmit: function (e) {
      e.preventDefault();
      if (!name.value.trim() || !(value.value.trim() || note.value.trim())) { status.className = 'status err'; status.textContent = T('Укажите имя и исправление.'); return; }
      btn.disabled = true; status.className = 'status'; status.textContent = T('Отправляю…');
      fetch(ROOT + 'api/proposals', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-Gene-Client': '1' },
        body: JSON.stringify({ target: personId, field: fieldSel.value, value: value.value, note: note.value, author: name.value, website: trap.value }) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || T('Ошибка ') + r.status); return j; }); })
        .then(function () { store('gene-author', name.value.trim()); value.value = ''; note.value = ''; status.textContent = T('Спасибо! Исправление ушло составителю архива.'); })
        .catch(function (err) { status.className = 'status err'; status.textContent = err.message || T('Не удалось отправить. Проверьте интернет и попробуйте ещё раз.'); })
        .then(function () { btn.disabled = false; });
    } }, fieldSel, value, note, name, trap, el('div', { class: 'row' }, status, btn));
    return el('details', { class: 'propose', hidden: !canPropose }, el('summary', { text: T('Предложить исправление') }), form);
  }
  function groupComments() {
    byPerson = {};
    comments.forEach(function (c) { (byPerson[c.person_id] = byPerson[c.person_id] || []).push(c); });
    $('c-count').textContent = comments.length ? String(comments.length) : '';
    if ($('c-count2')) $('c-count2').textContent = comments.length ? String(comments.length) : '';
  }
  function refreshAfterComment(personId) {
    if (docOpen === personId) renderCommentList($('doc-meta').querySelector('.comments'), byPerson[personId] || [], '');
    if (personId !== 'general' && $('panel').classList.contains('open') && selectedId === personId) {
      var list = $('panel-body').querySelector('.comments');
      renderCommentList(list, byPerson[personId] || [], '');
    }
    if (focusId) renderTree();
    if (wide.built) renderWide();
    renderFeed();
    renderPeople();
    renderQuestions();
    if (S[personId]) renderSources();
  }
  function loadComments() {
    var early = window.genePrefetch && window.genePrefetch.comments;
    if (early) window.genePrefetch.comments = null;
    if (!SITE.comments) return Promise.resolve().then(function () { comments = []; groupComments(); });
    fetch(ROOT + 'api/features', { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : {}; }).then(function (f) {
      canPropose = !!(f && f.proposals);
      document.querySelectorAll('.propose').forEach(function (d) { d.hidden = !canPropose; });
    }).catch(function () {});
    return (early || fetch(ROOT + 'api/comments', { credentials: 'same-origin' }))
      .then(function (r) { if (r.status === 401) { location.reload(); return []; } return r.ok ? r.json() : []; })
      .catch(function () { return []; })
      .then(function (list) { comments = list || []; groupComments(); });
  }

  // ---------- other views
  var currentView = 'tree';
  function showView(name) {
    currentView = name;
    document.body.classList.toggle('tree-mode', name === 'tree');
    document.body.classList.toggle('places-mode', name === 'places');
    document.querySelectorAll('.tabs button').forEach(function (b) { b.setAttribute('aria-selected', String(b.dataset.view === (name === 'wide' ? 'sources' : name))); });
    syncHeader(name);
    document.querySelectorAll('.view').forEach(function (v) { v.classList.toggle('active', v.id === 'view-' + name); });
    var up = document.querySelector('.story-up'); if (up && name !== 'story') up.hidden = true;
    document.querySelectorAll('.pl-status').forEach(function (x) { if (name !== 'story') x.hidden = true; else if (document.querySelector('#story.filtering')) x.hidden = false; });
    // древо ещё не рисовали (сайт открыли с другого раздела) — начинаем с «Нашей семьи»
    if (name === 'tree' && !focusId && D) setFocus(D.start_focus && P[D.start_focus] ? D.start_focus : D.root_person_id, { keepView: true });
    if (name === 'tree') requestAnimationFrame(function () { fit(false); });
    if (name === 'wide' && !document.documentElement.classList.contains('print-wide')) requestAnimationFrame(function () { renderWide(); wideFit(); });
    if (name !== 'story') storyAnchor = null;
    if (name === 'places') setTimeout(updatePlaceMap, 0);
    window.scrollTo({ top: 0, behavior: 'instant' });
    syncUrl();
  }

  // ---------- URL routing: #/вид[/аргумент][?person=ID&place=Место]
  var VIEWS = ['tree', 'wide', 'story', 'people', 'questions', 'places', 'sources'];
  var routing = false, booted = false, storyAnchor = null, storyPlace = null, storyReady = false, pendingStory = null;
  function buildHash() {
    var h = '#/' + currentView;
    if (currentView === 'tree' && focusId) h += '/' + focusId;
    if (currentView === 'story' && storyAnchor) h += '/' + storyAnchor;
    var q = [];
    if (currentView === 'story' && storyPlace) q.push('place=' + encodeURIComponent(storyPlace));
    if (currentView === 'places' && selectedPlace) q.push('place=' + encodeURIComponent(selectedPlace));
    if (currentView === 'tree' && lineKey) q.push('line=' + encodeURIComponent(lineKey));
    if (currentView === 'people' && peopleMode === 'calendar') {
      q.push('mode=calendar', 'month=' + calendar.year + '-' + String(calendar.month + 1).padStart(2, '0'));
      if (calendar.kind !== 'all') q.push('type=' + calendar.kind);
      if (calendar.day) q.push('day=' + calendar.day);
    }
    if (currentView === 'people' && peopleMode === 'surnames') q.push('mode=surnames');
    if (currentView === 'people' && peopleMode === 'bios') { q.push('mode=bios'); if (bioOpen) q.push('bio=' + bioOpen); }
    if (currentView === 'sources' && archMode !== 'docs') q.push('mode=' + archMode);
    if (currentView === 'people' && peopleMode === 'zodiac') {
      q.push('mode=zodiac');
      if (zodiacSelection) q.push('sign=' + zodiacSelection);
    }
    if (selectedId) q.push('person=' + selectedId);
    if (docOpen) q.push('doc=' + docOpen);
    return h + (q.length ? '?' + q.join('&') : '');
  }
  // Заголовок вкладки — о том, что открыто: человек, документ, место или раздел
  var baseTitle = document.title;
  function pageTitle() {
    var what = null;
    if (selectedId && P[selectedId]) what = P[selectedId].display_name;
    else if (docOpen && S[docOpen]) what = S[docOpen].title;
    else if (currentView === 'places' && selectedPlace) { var pl = placeBySlug(selectedPlace); what = pl && pl.name; }
    else if (currentView === 'tree' && focusId && P[focusId]) what = P[focusId].display_name;
    else { var tab = document.querySelector('.tabs [aria-selected="true"]'); what = tab && tab.firstChild && tab.firstChild.textContent.trim(); }
    return what ? what + T(' — Семейный архив') : baseTitle;
  }
  var urlQueued = false, urlPush = false;
  function syncUrl(replace) {
    if (routing || !booted) return;
    if (!replace) urlPush = true;
    if (urlQueued) return;
    urlQueued = true;
    Promise.resolve().then(function () {
      var push = urlPush; urlQueued = false; urlPush = false;
      var h = buildHash();
      document.title = pageTitle();
      if (h === location.hash) { if (window.geneTrackPage) window.geneTrackPage(); return; }
      try { window.history[push ? 'pushState' : 'replaceState'](null, '', h); lastApplied = h; if (window.geneTrackPage) window.geneTrackPage(); } catch (e) { /* ignore */ }
    });
  }
  function parseHash(hash) {
    var raw = decodeURIComponent((hash || '').replace(/^#\/?/, ''));
    var r = { view: null, arg: null, person: null, place: null };
    var qi = raw.indexOf('?'), path = qi < 0 ? raw : raw.slice(0, qi), qs = qi < 0 ? '' : raw.slice(qi + 1);
    qs.split('&').forEach(function (kv) {
      var i = kv.indexOf('='); if (i < 0) return;
      var k = kv.slice(0, i), v = kv.slice(i + 1);
      if (k === 'person') r.person = v; else if (k === 'place') r.place = v; else if (k === 'doc') r.doc = v; else if (k === 'line') r.line = v;
      else if (['mode', 'month', 'type', 'day', 'sign', 'bio'].indexOf(k) >= 0) r[k] = v;
    });
    var parts = path.split('/').filter(Boolean);
    if (parts.length === 1 && P[parts[0]]) { r.person = parts[0]; return r; }   // старые ссылки вида #I024
    if (parts[0] === 'discussion') parts[0] = 'questions';
    if (parts[0] && VIEWS.indexOf(parts[0]) >= 0) { r.view = parts[0]; r.arg = parts.slice(1).join('/') || null; }
    return r;
  }
  function applyRoute(r, first) {
    routing = true;
    try {
      var view = r.view || (r.person && first ? 'tree' : r.view) || (first ? 'tree' : currentView);
      if (view === 'tree') {
        var start = D.start_focus && P[D.start_focus] ? D.start_focus : D.root_person_id;
        var f = r.arg && P[r.arg] ? r.arg : (first ? (r.person && P[r.person] ? r.person : start) : (focusId || start));
        if (currentView !== 'tree') showView('tree');
        if (f !== focusId || (r.line || null) !== lineKey) setFocus(f, { line: r.line });
      } else if (view !== currentView) showView(view);
      if (view === 'people') {
        peopleMode = ['calendar', 'zodiac', 'surnames', 'bios'].indexOf(r.mode) >= 0 ? r.mode : 'list';
        bioOpen = peopleMode === 'bios' && r.bio && (D.bios || []).indexOf(r.bio) >= 0 ? r.bio : null;
        zodiacSelection = validZodiacSelection(r.sign) ? r.sign : null;
        zodiacLimit = 24;
        var month = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(r.month || '');
        if (month && +month[1] >= 1000) { calendar.year = +month[1]; calendar.month = +month[2] - 1; }
        calendar.kind = ['birth', 'death'].indexOf(r.type) >= 0 ? r.type : 'all';
        var maxDay = calendar.month === 1 ? 29 : calendarDaysInMonth(calendar.year, calendar.month);
        calendar.day = /^\d{1,2}$/.test(r.day || '') && +r.day >= 1 && +r.day <= maxDay ? +r.day : null;
        renderPeople();
      }
      if (view === 'story') {
        storyAnchor = r.arg; storyPlace = r.place;
        if (storyReady) applyStory(); else pendingStory = true;
      }
      if (view === 'places' && r.place && D.places.some(function (p) { return p.slug === r.place; })) openPlace(r.place);
      else if (view === 'places' && selectedPlace) closePanel();
      if (view === 'sources') setArchMode(r.mode === 'restored' || r.mode === 'corrections' ? r.mode : 'docs');
      if (r.doc && (S[r.doc] || (D.merged_sources || {})[r.doc])) { if (docOpen !== r.doc) openDoc(r.doc); } else if (docOpen) closeDoc();
      if (r.person && P[r.person]) { if (selectedId !== r.person) openPerson(r.person); }
      else if (selectedId) closePanel();
    } finally { routing = false; }
  }
  function applyStory() {
    pendingStory = null;
    if (storyNav) storyNav.setPlace(storyPlace, !!storyAnchor);
    if (storyAnchor) { var t = document.getElementById(storyAnchor); if (t) t.scrollIntoView({ block: 'start', behavior: 'instant' }); }
  }
  var lastApplied = null;
  function onUrl() { if (!booted || location.hash === lastApplied) return; lastApplied = location.hash; applyRoute(parseHash(location.hash), false); document.title = pageTitle(); syncUrl(true); }
  window.addEventListener('popstate', onUrl);
  window.addEventListener('hashchange', onUrl);

  function matchesPerson(p, q) {
    var hay = [p.display_name, p.relation, lifespan(p)].concat(p.aliases || []).join(' ').toLowerCase();
    return !q || hay.indexOf(q) >= 0;
  }

  function zodiacSign(date) {
    var key = (date.month + 1) * 100 + date.day;
    return ZODIAC.filter(function (sign) {
      return sign.from <= sign.to ? key >= sign.from && key <= sign.to : key >= sign.from || key <= sign.to;
    })[0];
  }
  function zodiacPerson(p) {
    var signs = [], dates = [];
    [p.birth].concat(p.birth_alternatives || []).forEach(function (record) {
      var date = record && calendarDate(record.date);
      if (!date) return;
      var sign = zodiacSign(date);
      if (signs.indexOf(sign) < 0) signs.push(sign);
      if (dates.indexOf(record.date) < 0) dates.push(record.date);
    });
    return { person: p, sign: signs.length === 1 ? signs[0] : null,
      group: signs.length > 1 ? 'conflict' : signs.length === 1 ? signs[0].id : 'unknown', dates: dates };
  }
  function indexZodiac() {
    zodiacPeople = D.people.filter(function (p) { return !p.placeholder && p.research_status !== 'unlinked_candidate'; }).map(zodiacPerson);
    zodiacPeople.sort(function (a, b) { return a.person.display_name.localeCompare(b.person.display_name, 'ru'); });
  }
  function validZodiacSelection(value) {
    return ['unknown', 'conflict'].indexOf(value) >= 0 || ZODIAC.some(function (sign) { return sign.id === value; }) ||
      Object.keys(ZODIAC_ELEMENTS).some(function (key) { return 'element-' + key === value; });
  }
  function zodiacRange(sign) {
    function day(key) { return key % 100 + ' ' + MONTHS[Math.floor(key / 100) - 1]; }
    return day(sign.from) + ' — ' + day(sign.to);
  }
  function zodiacMatches(record) {
    return !zodiacSelection || record.group === zodiacSelection ||
      (record.sign && 'element-' + record.sign.element === zodiacSelection);
  }
  function selectZodiac(value) {
    var active = document.activeElement, wasFocused = active && active.getAttribute('data-zodiac-select') === value;
    var tag = wasFocused ? active.tagName.toLowerCase() : null;
    zodiacSelection = zodiacSelection === value ? null : value; zodiacLimit = 24;
    updateCalendar();
    if (wasFocused) {
      var next = $('people-zodiac').querySelector(tag + '[data-zodiac-select="' + value + '"]');
      if (next) next.focus({ preventScroll: true });
    }
    if (zodiacSelection && window.matchMedia('(max-width: 720px)').matches) {
      $('zodiac-details').scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
    }
  }
  function initZodiac() {
    $('zodiac-reset').onclick = function () {
      zodiacSelection = null; updateCalendar();
      document.querySelector('[data-people-mode="zodiac"]').focus({ preventScroll: true });
      $('zodiac-title').scrollIntoView({ block: 'center', behavior: 'instant' });
    };
    $('zodiac-more').onclick = function () { zodiacLimit += 24; renderZodiac(($('people-filter').value || '').trim().toLowerCase()); };
  }
  function zodiacSvg(tag, attrs) {
    var node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    return node;
  }
  function zodiacPoint(radius, angle) {
    var radians = (angle - 90) * Math.PI / 180;
    return [200 + radius * Math.cos(radians), 200 + radius * Math.sin(radians)];
  }
  function zodiacArc(start, end) {
    var a = zodiacPoint(158, start), b = zodiacPoint(158, end), c = zodiacPoint(103, end), d = zodiacPoint(103, start);
    var large = end - start > 180 ? 1 : 0;
    return 'M' + a.join(',') + ' A158,158 0 ' + large + ',1 ' + b.join(',') + ' L' + c.join(',') +
      ' A103,103 0 ' + large + ',0 ' + d.join(',') + ' Z';
  }
  function renderZodiac(q) {
    var records = zodiacPeople.filter(function (record) { return matchesPerson(record.person, q); });
    var counts = {}, known = 0;
    records.forEach(function (record) { counts[record.group] = (counts[record.group] || 0) + 1; if (record.sign) known++; });
    var formatter = new Intl.NumberFormat(document.documentElement.lang || 'ru', { maximumFractionDigits: 1 });
    function share(n) { return formatter.format(known ? 100 * n / known : 0) + '%'; }
    var chart = clear($('zodiac-chart')), legend = clear($('zodiac-signs')), angle = 0;
    chart.appendChild(zodiacSvg('path', { class: 'zodiac-track', d: zodiacArc(0, 180) + ' ' + zodiacArc(180, 360) }));
    ZODIAC.forEach(function (sign) {
      var count = counts[sign.id] || 0, selected = zodiacSelection === sign.id || zodiacSelection === 'element-' + sign.element;
      var color = '--zodiac-color:var(--zodiac-' + sign.element + ')';
      var label = sign.name + T('. Людей: ') + count + ' · ' + share(count);
      if (count) {
        var end = angle + count / known * 360, middle = (angle + end) / 2;
        // A full ring needs two arcs when every matching person has the same sign.
        var path = zodiacSvg('path', { d: end - angle > 359.99 ? zodiacArc(angle, angle + 180) + ' ' + zodiacArc(angle + 180, end) : zodiacArc(angle, end),
          class: 'zodiac-sector' + (selected ? ' selected' : zodiacSelection ? ' dimmed' : ''), style: color,
          role: 'button', tabindex: 0, 'aria-label': label, 'aria-pressed': String(selected), 'data-zodiac-select': sign.id });
        path.addEventListener('click', function () { selectZodiac(sign.id); });
        path.addEventListener('keydown', function (event) { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectZodiac(sign.id); } });
        var title = zodiacSvg('title'); title.textContent = label; path.appendChild(title); chart.appendChild(path);
        var point = zodiacPoint(181, middle), symbol = zodiacSvg('text', { x: point[0], y: point[1], class: 'zodiac-chart-symbol', 'aria-hidden': 'true' });
        symbol.textContent = sign.symbol; chart.appendChild(symbol);
        angle = end;
      }
      legend.appendChild(el('button', { class: 'zodiac-sign', style: color, 'data-zodiac-select': sign.id,
        'aria-label': label, 'aria-pressed': String(zodiacSelection === sign.id), onclick: function () { selectZodiac(sign.id); } },
        el('span', { class: 'zodiac-sign-symbol', text: sign.symbol, 'aria-hidden': 'true' }),
        el('span', {}, el('span', { class: 'zodiac-sign-name', text: sign.name }), el('small', { class: 'zodiac-sign-range', text: zodiacRange(sign) })),
        el('span', { class: 'zodiac-sign-count', text: count }), el('span', { class: 'zodiac-sign-share', text: share(count) })));
    });
    $('zodiac-coverage').textContent = T('Знак определён: ') + known + T(' из ') + records.length + (q ? T(' · По вашему фильтру') : '');
    var elements = clear($('zodiac-elements'));
    Object.keys(ZODIAC_ELEMENTS).forEach(function (key) {
      var count = records.filter(function (record) { return record.sign && record.sign.element === key; }).length;
      elements.appendChild(el('button', { class: 'zodiac-element', style: '--zodiac-color:var(--zodiac-' + key + ')',
        'data-zodiac-select': 'element-' + key, 'aria-pressed': String(zodiacSelection === 'element-' + key), onclick: function () { selectZodiac('element-' + key); } },
        el('span', { class: 'zodiac-swatch', 'aria-hidden': 'true' }), ZODIAC_ELEMENTS[key] + ' · ' + count));
    });
    var missing = clear($('zodiac-missing'));
    [['unknown', T('Без точной даты рождения')], ['conflict', T('Знак требует уточнения')]].forEach(function (item) {
      missing.appendChild(el('button', { class: 'btn', 'data-zodiac-select': item[0], 'aria-pressed': String(zodiacSelection === item[0]),
        onclick: function () { selectZodiac(item[0]); }, text: item[1] + ' · ' + (counts[item[0]] || 0) }));
    });
    var shown = records.filter(zodiacMatches), sign = ZODIAC.filter(function (item) { return item.id === zodiacSelection; })[0];
    var title = sign ? sign.name : zodiacSelection === 'unknown' ? T('Без точной даты рождения') : zodiacSelection === 'conflict' ? T('Знак требует уточнения') : ZODIAC_ELEMENTS[(zodiacSelection || '').replace('element-', '')];
    $('zodiac-center-count').textContent = zodiacSelection ? shown.length : known;
    $('zodiac-center-label').textContent = zodiacSelection ? title + (sign ? ' · ' + share(shown.length) : '') : plural(known, T('человек с известным знаком'), T('человека с известным знаком'), T('людей с известным знаком'));
    $('zodiac-details').hidden = !zodiacSelection;
    $('zodiac-reset').hidden = !zodiacSelection;
    $('zodiac-details-title').textContent = title || T('Все знаки');
    $('zodiac-selection-summary').textContent = T('Людей: ') + shown.length + (sign ? ' · ' + zodiacRange(sign) : '');
    var host = clear($('zodiac-people'));
    if (zodiacSelection) shown.slice(0, zodiacLimit).forEach(function (record) {
      var p = record.person, date = record.dates.length ? record.dates.map(fmtDate).join(' / ') : fmtDate(p.birth && p.birth.date);
      host.appendChild(el('button', { class: 'zodiac-person', onclick: function () { openPerson(p.id); } },
        el('strong', { text: p.display_name }), el('small', { text: date || T('Дата рождения неизвестна') }),
        el('small', { text: p.relation }), record.group === 'conflict' ? el('small', { class: 'zodiac-warning', text: T('Варианты рождения дают разные знаки') }) : null));
    });
    if (zodiacSelection && !shown.length) host.appendChild(el('p', { class: 'empty', text: T('В этой группе пока никого нет. Попробуйте изменить фильтр или выбрать другой знак.') }));
    $('zodiac-more').hidden = !zodiacSelection || shown.length <= zodiacLimit;
  }

  function calendarDaysInMonth(y, m) {
    var leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
    return [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m];
  }

  function calendarDate(value) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
    if (!m) return null;
    var y = +m[1], month = +m[2] - 1, day = +m[3];
    if (y < 1 || month < 0 || month > 11 || day < 1 || day > calendarDaysInMonth(y, month)) return null;
    return { year: y, month: month, day: day };
  }

  function indexCalendar() {
    calendarEvents = [];
    D.people.forEach(function (p) {
      if (p.placeholder) return;
      ['birth', 'death'].forEach(function (kind) {
        var records = [p[kind]].concat(p[kind + '_alternatives'] || []), seen = {};
        var conflicting = records.some(function (r) { return r && r.date && (!p[kind] || r.date !== p[kind].date); });
        records.forEach(function (record, i) {
          var date = record && calendarDate(record.date);
          if (!date || seen[record.date]) return;
          seen[record.date] = true;
          calendarEvents.push({ person: p, kind: kind, date: date, original: record.date, alternative: i > 0,
            uncertain: conflicting || /uncertain|conflicting/.test(record.status || '') });
        });
      });
    });
    calendarEvents.sort(function (a, b) {
      return a.date.month - b.date.month || a.date.day - b.date.day ||
        (a.kind === b.kind ? 0 : a.kind === 'birth' ? -1 : 1) || a.person.display_name.localeCompare(b.person.display_name, 'ru');
    });
  }

  function updateCalendar() { renderPeople(); syncUrl(); }
  function selectCalendarDay(day) {
    calendar.day = calendar.day === day ? null : day;
    updateCalendar();
    var button = $('calendar-days').querySelector('[data-day="' + day + '"]');
    if (button) button.focus({ preventScroll: true });
  }
  function moveCalendarMonth(step) {
    var next = new Date(calendar.year, calendar.month + step, 1);
    if (next.getFullYear() < 1000 || next.getFullYear() > 9999) return;
    calendar.year = next.getFullYear(); calendar.month = next.getMonth(); calendar.day = null;
    updateCalendar();
  }
  function initCalendar() {
    CALENDAR_MONTHS.forEach(function (name, i) { $('calendar-month').appendChild(el('option', { value: i, text: name })); });
    document.querySelectorAll('[data-people-mode]').forEach(function (b) {
      b.addEventListener('click', function () { peopleMode = b.dataset.peopleMode; updateCalendar(); });
    });
    document.querySelectorAll('[data-calendar-kind]').forEach(function (b) {
      b.addEventListener('click', function () { calendar.kind = b.dataset.calendarKind; calendar.day = null; updateCalendar(); });
    });
    $('calendar-prev').onclick = function () { moveCalendarMonth(-1); };
    $('calendar-next').onclick = function () { moveCalendarMonth(1); };
    $('calendar-month').onchange = function () { calendar.month = +this.value; calendar.day = null; updateCalendar(); };
    $('calendar-today').onclick = function () {
      var now = new Date(); calendar.year = now.getFullYear(); calendar.month = now.getMonth(); calendar.day = null;
      updateCalendar();
    };
    $('calendar-all-days').onclick = function () { calendar.day = null; updateCalendar(); };
    $('calendar-leap').onclick = function () { selectCalendarDay(29); };
  }
  // В ячейке дня — имена (на узком экране только значки)
  function calendarDayPeople(list) {
    var names = list.map(function (e) { return el('span', { class: 'calendar-name ' + e.kind }, (e.person.given_names || e.person.display_name).split(' ')[0]); });
    var box = el('span', { class: 'calendar-day-people', 'aria-hidden': 'true' }, names);
    if (names.length > 2) box.appendChild(el('span', { class: 'calendar-more', text: '+' + (names.length - 2) }));
    return box;
  }
  // «Скоро»: ближайшие семейные даты на 30 дней вперёд от сегодняшнего дня
  function renderUpcoming(q) {
    var host = clear($('calendar-upcoming')), now = new Date();
    now.setHours(0, 0, 0, 0);
    if (q) { host.hidden = true; return; }
    var soon = [];
    calendarEvents.forEach(function (e) {
      var next = new Date(now.getFullYear(), e.date.month, e.date.day);
      if (next < now) next = new Date(now.getFullYear() + 1, e.date.month, e.date.day);
      var days = Math.round((next - now) / 864e5);
      if (days <= 30 && (calendar.kind === 'all' || calendar.kind === e.kind)) soon.push({ e: e, days: days, next: next });
    });
    soon.sort(function (a, b) { return a.days - b.days || a.e.date.year - b.e.date.year; });
    host.hidden = !soon.length;
    if (!soon.length) return;
    host.appendChild(el('h3', { class: 'calendar-upcoming-title', text: T('Скоро') }));
    var row = el('div', { class: 'calendar-upcoming-row' });
    soon.slice(0, 5).forEach(function (x) {
      var age = x.next.getFullYear() - x.e.date.year;
      var when = x.days === 0 ? T('сегодня') : x.days === 1 ? T('завтра') : T('через ') + x.days + ' ' + plural(x.days, T('день'), T('дня'), T('дней'));
      row.appendChild(el('button', { class: 'calendar-soon ' + x.e.kind, onclick: function () { openPerson(x.e.person.id); } },
        el('span', { class: 'calendar-soon-when', text: when + ' · ' + x.e.date.day + ' ' + MONTHS[x.e.date.month] }),
        el('strong', { text: x.e.person.display_name }),
        el('small', { text: (x.e.kind === 'birth' ? T('День рождения') : T('День памяти')) + (age > 0 ? ' · ' + age + ' ' + plural(age, T('год'), T('года'), T('лет')) : '') })));
    });
    host.appendChild(row);
  }
  function renderCalendar(q) {
    renderUpcoming(q);
    var events = calendarEvents.filter(function (e) {
      return e.date.month === calendar.month && e.date.year <= calendar.year &&
        (calendar.kind === 'all' || calendar.kind === e.kind) &&
        (matchesPerson(e.person, q) || (q && (e.original + ' ' + fmtDate(e.original)).toLowerCase().indexOf(q) >= 0));
    });
    var title = CALENDAR_MONTHS[calendar.month] + ' ' + calendar.year;
    $('calendar-title').textContent = title;
    $('calendar-month').value = String(calendar.month);
    $('calendar-prev').disabled = calendar.year === 1000 && calendar.month === 0;
    $('calendar-next').disabled = calendar.year === 9999 && calendar.month === 11;
    document.querySelectorAll('[data-calendar-kind]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.calendarKind === calendar.kind)); });
    var days = clear($('calendar-days')), count = calendarDaysInMonth(calendar.year, calendar.month);
    var offset = (new Date(calendar.year, calendar.month, 1).getDay() + 6) % 7, today = new Date();
    for (var empty = 0; empty < offset; empty++) days.appendChild(el('span', { 'aria-hidden': 'true' }));
    for (var day = 1; day <= count; day++) {
      var birthCount = 0, deathCount = 0;
      events.forEach(function (e) { if (e.date.day === day) { if (e.kind === 'birth') birthCount++; else deathCount++; } });
      var hasEvents = birthCount + deathCount > 0;
      var label = day + ' ' + MONTHS[calendar.month] + ' ' + calendar.year + '. ' +
        (hasEvents ? T('Дни рождения: ') + birthCount + T('. Даты смерти: ') + deathCount + '.' : T('Нет семейных дат.'));
      days.appendChild(el('button', { class: 'calendar-day' + (hasEvents ? ' has-events' : ''), 'data-day': day,
        'aria-label': label, 'aria-pressed': String(calendar.day === day),
        'aria-current': today.getFullYear() === calendar.year && today.getMonth() === calendar.month && today.getDate() === day ? 'date' : null,
        onclick: (function (d) { return function () { selectCalendarDay(d); }; })(day) },
        el('span', { class: 'calendar-day-number', text: day }),
        hasEvents ? calendarDayPeople(events.filter(function (e) { return e.date.day === day; })) : null));
    }
    // Keep 29 February visible as an anniversary in years without that day.
    $('calendar-leap').hidden = calendar.month !== 1 || count === 29 || !events.some(function (e) { return e.date.day === 29; });
    $('calendar-leap').setAttribute('aria-pressed', String(calendar.day === 29));
    $('calendar-all-days').hidden = calendar.day === null;
    $('calendar-agenda-title').textContent = calendar.day ? calendar.day + ' ' + MONTHS[calendar.month] : T('Даты месяца');
    var shown = events.filter(function (e) { return calendar.day === null || e.date.day === calendar.day; });
    $('calendar-summary').textContent = T('Записей: ') + shown.length + (q ? T(' · По вашему фильтру') : '');
    var host = clear($('calendar-events')), previousDay = null;
    shown.forEach(function (e) {
      if (e.date.day !== previousDay) {
        var wd = new Date(calendar.year, calendar.month, Math.min(e.date.day, calendarDaysInMonth(calendar.year, calendar.month))).getDay();
        host.appendChild(el('h4', { class: 'calendar-event-day' }, el('b', { text: String(e.date.day) }), el('span', { text: MONTHS[calendar.month] + ', ' + WEEKDAYS[wd] })));
        previousDay = e.date.day;
      }
      var age = calendar.year - e.date.year;
      var elapsed = age ? (e.kind === 'birth' ? T('Со дня рождения: ') : T('Со дня смерти: ')) + age + ' ' + plural(age, T('год'), T('года'), T('лет')) : T('Год события');
      host.appendChild(el('button', { class: 'calendar-event', onclick: function () { openPerson(e.person.id); } },
        el('span', { class: 'calendar-mark ' + e.kind, 'aria-hidden': 'true' }),
        el('span', { class: 'calendar-event-body' }, el('strong', { text: e.person.display_name }),
          e.person.relation ? el('small', { class: 'calendar-rel', text: e.person.relation }) : null,
          el('small', { text: (e.kind === 'birth' ? T('День рождения') : T('Дата смерти')) + ' · ' + fmtDate(e.original) + ' · ' + elapsed }),
          age > 0 && age % 5 === 0 ? el('span', { class: 'calendar-round', text: T('Круглая дата') }) : null,
          e.uncertain || e.alternative ? el('small', { class: 'calendar-warning', text: e.alternative ? T('Другой вариант даты') : T('Дата требует уточнения') }) : null)));
    });
    if (!shown.length) host.appendChild(el('p', { class: 'empty', text: q ? T('По этому фильтру дат нет. Попробуйте другое имя или месяц.') : calendar.day ? T('На этот день семейных дат пока нет.') : T('В этом месяце известных дат пока нет.') }));
  }

  // «Люди» → «Фамилии»: карточки фамилий со ссылками на их страницы (familii/<slug>.html) и на ветвь в древе
  var TRANSLIT = { а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'kh', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'shch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya' };
  function surnameSlug(k) {   // как translit() в tools/site_discovery.py
    return k.toLowerCase().split('').map(function (c) { return c in TRANSLIT ? TRANSLIT[c] : c; }).join('').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  }
  function surnamePlural(k) { return /ий$/.test(k) ? k.replace(/ий$/, 'ие') : /(ов|ев|ин|ын)$/.test(k) ? k + T('ы') : k; }
  function renderSurnames(q) {
    var host = clear($('people-surnames')), dir = location.pathname.replace(/[^\/]*$/, '');
    surnameGroups().filter(function (g) { return g.ids.length >= 3 && g.key.indexOf('(') < 0 && (!q || g.key.toLowerCase().indexOf(q) >= 0); }).forEach(function (g) {
      var years = [], places = {};
      g.ids.forEach(function (id) {
        var p = P[id];
        ['birth', 'death'].forEach(function (k) { var m = /(\d{4})/.exec((p[k] || {}).date || ''); if (m) years.push(+m[1]); });
        ['birth', 'death', 'burial'].forEach(function (k) { ((p[k] || {}).place_slugs || []).forEach(function (s) { places[s] = (places[s] || 0) + 1; }); });
      });
      var top = Object.keys(places).sort(function (a, b) { return places[b] - places[a]; }).map(placeBySlug).filter(Boolean).slice(0, 3)
        .map(function (pl) { return pl.name.split(/[:(]/)[0].trim(); });
      host.appendChild(el('article', { class: 'fam-card' },
        el('h3', { text: surnamePlural(g.key) }),
        el('p', { class: 'fam-meta', text: g.ids.length + ' ' + plural(g.ids.length, T('человек'), T('человека'), T('человек')) + (years.length ? ' · ' + Math.min.apply(null, years) + '–' + Math.max.apply(null, years) : '') }),
        top.length ? el('p', { class: 'fam-places', text: top.join(', ') }) : null,
        el('div', { class: 'fam-actions' },
          el('a', { class: 'btn', href: dir + 'familii/' + surnameSlug(g.key) + '.html', text: T('Страница фамилии') }),
          el('button', { class: 'btn', text: T('Ветвь в древе'), onclick: function () { showView('tree'); setFocus(g.focus, { line: g.key }); } }))));
    });
  }
  // ---------- «Люди → Биографии»: подробные рассказы из bios.html (оглавление карточками, затем одна биография)
  function openBio(id) {
    closePanel();
    peopleMode = 'bios'; bioOpen = id;
    if (currentView !== 'people') showView('people'); else renderPeople();
    syncUrl();
  }
  function renderBios() {
    var host = $('people-bios');
    if (biosHtml === null) {
      biosHtml = '';
      host.appendChild(el('p', { class: 'sub', text: T('Загружаем…') }));
      fetch('bios.html' + (SITE.v_bios ? '?v=' + SITE.v_bios : ''), { credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
        .then(function (html) { biosHtml = html; if (peopleMode === 'bios') renderBios(); })
        .catch(function () { biosHtml = null; clear(host).appendChild(el('p', { class: 'sub', text: T('Не удалось загрузить биографии.') })); });
      return;
    }
    if (!biosHtml) return;
    clear(host).innerHTML = biosHtml;
    host.querySelectorAll('a.pl').forEach(function (a) {
      var pid = a.dataset.p;
      if (!P[pid]) { a.replaceWith(document.createTextNode(a.textContent)); return; }
      a.href = '#/tree/' + pid + '?person=' + pid;
      a.addEventListener('click', function (e) { e.preventDefault(); openPerson(pid); });
    });
    // ссылки на документы — сноски: «(S231, S44)» в тексте становится надстрочной цифрой,
    // а в конце биографии — список «Документы» с названиями (одинаковый документ — одна цифра)
    host.querySelectorAll('article.bio').forEach(function (art) {
      var order = [], num = {};
      var mark = function (sid) {
        if (!num[sid]) { order.push(sid); num[sid] = order.length; }
        return el('a', { class: 'fn', href: '#bio-src-' + art.dataset.p + '-' + num[sid], title: S[sid].title, text: String(num[sid]), onclick: function (e) { e.preventDefault(); openDoc(sid); } });
      };
      art.querySelectorAll('p, li, figcaption').forEach(function (node) {
        Array.prototype.slice.call(node.childNodes).forEach(function (t) {
          if (t.nodeType !== 3 || !/\bS\d+\b/.test(t.nodeValue)) return;
          var frag = document.createDocumentFragment(), s = t.nodeValue, last = 0, m;
          // сначала скобки только из номеров: «(S2, S232)» → ²,³ без скобок; затем одиночные номера в тексте
          var re = /\s?\((S\d+(?:,\s*S\d+)*)\)|\bS\d+\b/g;
          while ((m = re.exec(s))) {
            var ids = (m[1] || m[0]).split(/,\s*/).filter(function (x) { return S[x]; });
            if (!ids.length) continue;
            frag.appendChild(document.createTextNode(s.slice(last, m.index)));
            var sup = el('sup', { class: 'fns' });
            ids.forEach(function (sid, i) { if (i) sup.appendChild(document.createTextNode(',')); sup.appendChild(mark(sid)); });
            frag.appendChild(sup);
            last = m.index + m[0].length;
          }
          frag.appendChild(document.createTextNode(s.slice(last)));
          t.replaceWith(frag);
        });
      });
      if (!order.length) return;
      var list = el('ol', { class: 'bio-srcs' });
      order.forEach(function (sid, i) {
        list.appendChild(el('li', { id: 'bio-src-' + art.dataset.p + '-' + (i + 1) },
          el('a', { href: '#/sources?doc=' + sid, text: S[sid].title, onclick: function (e) { e.preventDefault(); openDoc(sid); } })));
      });
      art.appendChild(el('h3', { class: 'bio-srcs-h', text: T('Документы') }));
      art.appendChild(list);
    });
    enhanceStory(host);
    var arts = Array.prototype.slice.call(host.querySelectorAll('article.bio'));
    if (bioOpen && !host.querySelector('#bio-' + bioOpen)) bioOpen = null;
    // оглавление: портрет, имя, годы, начало рассказа
    host.querySelectorAll('.bio-group').forEach(function (g) {
      var cards = el('div', { class: 'bio-cards' });
      g.querySelectorAll('article.bio').forEach(function (a) {
        var img = a.querySelector('figure.portrait img'), lead = a.querySelector('p.lead');
        cards.appendChild(el('button', { class: 'bio-card', type: 'button', onclick: function () { bioOpen = a.dataset.p; renderBios(); syncUrl(); window.scrollTo(0, 0); } },
          img ? el('img', { src: img.getAttribute('src'), alt: '', loading: 'lazy' }) : el('span', { class: 'bio-noimg', text: (a.querySelector('h2').textContent || '?').charAt(0) }),
          el('span', { class: 'bio-card-text' },
            el('b', { text: a.querySelector('h2').textContent }),
            el('small', { text: (a.querySelector('.bio-years') || {}).textContent || '' }),
            lead ? el('span', { class: 'bio-card-lead', text: lead.textContent }) : null)));
      });
      var h = g.querySelector('.bio-group-h');
      if (h) h.after(cards); else g.prepend(cards);
    });
    host.classList.toggle('reading', !!bioOpen);
    arts.forEach(function (a) { a.hidden = a.dataset.p !== bioOpen; });
    if (bioOpen) {
      var art = host.querySelector('#bio-' + bioOpen), i = arts.indexOf(art);
      var nav = function () {
        return el('div', { class: 'bio-nav' },
          el('button', { class: 'btn', type: 'button', text: T('← Все биографии'), onclick: function () { bioOpen = null; renderBios(); syncUrl(); } }),
          el('button', { class: 'btn', type: 'button', text: T('Карточка в древе'), onclick: function () { openPerson(bioOpen); } }),
          el('button', { class: 'btn', type: 'button', text: T('Поделиться'), onclick: function (e) { shareLink(e.currentTarget, 'bio-' + bioOpen); } }),
          arts[i + 1] ? el('button', { class: 'btn', type: 'button', text: arts[i + 1].querySelector('h2').textContent + ' →', onclick: function () { bioOpen = arts[i + 1].dataset.p; renderBios(); syncUrl(); window.scrollTo(0, 0); } }) : null);
      };
      art.prepend(nav());
      art.appendChild(nav());
    }
  }
  function renderPeople() {
    var q = ($('people-filter').value || '').trim().toLowerCase();
    document.querySelectorAll('[data-people-mode]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.peopleMode === peopleMode)); });
    $('people-list').hidden = peopleMode !== 'list';
    $('people-calendar').hidden = peopleMode !== 'calendar';
    $('people-zodiac').hidden = peopleMode !== 'zodiac';
    $('people-surnames').hidden = peopleMode !== 'surnames';
    $('people-bios').hidden = peopleMode !== 'bios';
    document.querySelector('[data-people-mode="bios"]').hidden = !(D.bios || []).length;
    $('people-filter').hidden = peopleMode === 'bios';
    if (peopleMode === 'bios') {
      $('people-sub').textContent = T('Подробные рассказы о жизни — по документам и воспоминаниям семьи.');
      renderBios();
      return;
    }
    if (peopleMode === 'surnames') {
      $('people-sub').textContent = T('Фамилии нашего архива: сколько человек, годы и места. У каждой — своя страница, её удобно найти через поисковик и переслать родным.');
      renderSurnames(q);
      return;
    }
    if (peopleMode === 'zodiac') {
      $('people-sub').textContent = T('Семья в знаках зодиака — по известным датам рождения.');
      renderZodiac(q);
      return;
    }
    if (peopleMode === 'calendar') {
      $('people-sub').textContent = T('Календарь дней рождения и дат смерти. Выберите месяц или день, чтобы посмотреть семейные даты.');
      renderCalendar(q);
      return;
    }
    var host = clear($('people-list'));
    // сначала люди с фамилией, затем известные только по имени, в конце — пока безымянные места в древе
    var group = function (p) { return p.placeholder ? 2 : (p.surname || '').trim() ? 0 : 1; };
    // при поиске наверху — совпадения в ФИО (сначала с начала слова), ниже — найденные по родству и годам
    var nameRank = function (p) {
      if (!q) return 0;
      var names = [p.display_name].concat(p.aliases || []).join(' ').toLowerCase();
      if (names.indexOf(q) < 0) return 2;
      return names.split(/[\s()«»"„“-]+/).some(function (w) { return w.indexOf(q) === 0; }) ? 0 : 1;
    };
    var list = D.people.filter(function (p) { return matchesPerson(p, q); }).map(function (p) { return { p: p, r: nameRank(p) }; })
      .sort(function (a, b) { return a.r - b.r || group(a.p) - group(b.p) || a.p.display_name.localeCompare(b.p.display_name, 'ru'); });
    var heads = ['', T('Известны только по имени'), T('Имя пока неизвестно')];
    var shown = 0, lastGroup = 0, otherHead = false;
    list.forEach(function (item) {
      var p = item.p;
      shown++;
      var g = group(p);
      if (q) {
        if (item.r === 2 && !otherHead) { otherHead = true; host.appendChild(el('h3', { class: 'plist-h', text: T('Найдены по родству или годам') })); }
      } else if (g !== lastGroup && heads[g]) host.appendChild(el('h3', { class: 'plist-h', text: heads[g] }));
      lastGroup = g;
      var n = (byPerson[p.id] || []).length;
      host.appendChild(el('button', { class: 'prow', onclick: function () { openPerson(p.id); } },
        el('span', { class: 'n', text: p.display_name }), el('span', { class: 'r', text: p.relation }),
        el('span', { class: 'y', text: lifespan(p) }), el('span', { class: 'c', text: n ? '💬 ' + n : '' })));
    });
    // коротко: сколько людей и что делать; вероятная родня и так помечена в списке знаком ≈
    var cn = D.counts;
    $('people-sub').textContent = cn.named_people + ' ' + plural(cn.named_people, T('человек'), T('человека'), T('человек')) + T(' в древе. ') + (q ? T('Найдено: ') + shown + '.' : T('Нажмите на строку, чтобы открыть карточку.'));
  }

  function renderQuestions() {
    var host = clear($('questions'));
    D.questions.forEach(function (q) {
      var n = (byPerson[q.person] || []).length;
      host.appendChild(el('article', { class: 'cardbox qcard' },
        el('p', { text: q.text }),
        el('div', { class: 'foot-row' }, personChip(q.person),
          el('button', { class: 'btn primary', text: T('Ответить'), onclick: function () { openPerson(q.person, { compose: true, placeholder: T('Ответ на вопрос: ') + q.text }); } }),
          n ? el('span', { class: 'ans', text: n + ' ' + plural(n, T('комментарий'), T('комментария'), T('комментариев')) }) : null)));
    });
    $('q-count').textContent = String(D.questions.length);
    var leads = clear($('leads'));
    var shut = function (l) { return l.status === 'closed' || l.status === 'superseded'; };
    D.leads.slice().sort(function (a, b) { return shut(a) - shut(b); }).forEach(function (l) {
      leads.appendChild(el('article', { class: 'cardbox' + (shut(l) ? ' lead-shut' : '') },
        el('h4', null, el('span', { class: 'lid', text: l.id }), l.title),
        shut(l) ? el('p', { class: 'lead-status' }, el('b', { text: l.status === 'closed' ? T('✓ Закрыта. ') : T('Устарела. ') }), l.resolution || '') : null,
        l.record ? el('p', { text: l.record }) : null,
        l.limitations ? el('p', { class: 'where', text: l.limitations }) : null,
        l.person_id && P[l.person_id] ? el('div', { class: 'foot-row' }, personChip(l.person_id)) : null));
    });
  }

  function renderUnmatched() {
    var u = D.unmatched_profiles; if (!u || !u.urls || !u.urls.length) return;
    var host = $('leads');
    host.parentNode.insertBefore(el('h3', { text: T('Профили родственников без места в древе') }), host.nextSibling);
    var box = el('div', { class: 'cardbox' }, el('p', { text: u.note }),
      el('ul', null, u.urls.map(function (x) { return el('li', null, el('a', { href: x, target: '_blank', rel: 'noopener noreferrer', text: x.replace('https://www.facebook.com/', '') })); })));
    host.parentNode.insertBefore(box, host.nextSibling.nextSibling);
  }

  function renderFeed() {
    var sorted = comments.slice().sort(function (a, b) { return b.id - a.id; });
    renderCommentList(clear($('feed')), sorted, T('Комментариев пока нет — будьте первым.'), true);
  }

  function loadStory() {
    fetch('story.html' + (SITE.v_story ? '?v=' + SITE.v_story : ''), { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        var host = $('story');
        host.innerHTML = html;
        host.querySelectorAll('a.pl').forEach(function (a) {
          var id = a.dataset.p;
          if (!P[id]) { a.replaceWith(document.createTextNode(a.textContent)); return; }
          a.href = '#/tree/' + id + '?person=' + id;   // настоящий адрес карточки: работает и в новой вкладке
          a.title = P[id].display_name + (lifespan(P[id]) ? ', ' + lifespan(P[id]) : '');
          a.addEventListener('click', function (e) { e.preventDefault(); openPerson(id); });
        });
        enhanceStory(host);
        buildStoryNav(host);
        storyReady = true;
        if (pendingStory && currentView === 'story') applyStory();
      })
      .catch(function (e) { if (window.console) console.error(e); $('story').textContent = T('Не удалось загрузить рассказ.'); });
  }

  // «История»: лента времени, фильтр по местам и метки ветвей — из site.json (story.*)
  var STORY_TIME = [], STORY_PLACES = [], STORY_BRANCH = {}, BRANCH_NAME = {}, BRANCH_COLOR = {};
  function indexStory() {
    var st = SITE.story || {};
    STORY_TIME = st.timeline || [];
    STORY_PLACES = (st.places || []).map(function (x) { return [x[0], new RegExp(x[1], 'i')]; });
    STORY_BRANCH = st.branch_tags || {};
    BRANCH_NAME = st.branch_names || {};
    BRANCH_COLOR = st.branch_colors || {};
  }
  // Вёрстка «Истории»: ветви у глав, галереи из подряд идущих фото, лайтбокс, боковая лента со scrollspy.
  function enhanceStory(host) {
    host.querySelectorAll('section[id]').forEach(function (sec) {
      var br = STORY_BRANCH[sec.id]; if (!br) return;
      var h = sec.querySelector('h3'); if (!h) return;
      var tags = el('span', { class: 'br-tags' });
      br.forEach(function (b) { tags.appendChild(el('span', { class: 'br br-' + b, style: BRANCH_COLOR[b] ? 'background:' + BRANCH_COLOR[b] : null, text: BRANCH_NAME[b] || b })); });
      h.after(tags);
      sec.classList.add('br-' + br[0] + '-sec');
    });
    // подряд идущие фото → галерея
    Array.prototype.slice.call(host.querySelectorAll('figure.sfig.photo')).forEach(function (f) {
      if (f.parentNode.classList.contains('sgal')) return;
      var run = [f], n = f.nextElementSibling;
      while (n && n.matches('figure.sfig.photo')) { run.push(n); n = n.nextElementSibling; }
      if (run.length < 2) { f.classList.add('solo'); return; }
      var g = el('div', { class: 'sgal n' + Math.min(run.length, 3) });
      f.before(g); run.forEach(function (x) { g.appendChild(x); });
    });
    // вёрстка без дыр: высокая картинка встаёт сбоку от текста, а снимок сбоку,
    // рядом с которым почти нет текста, поднимается на абзац-другой выше
    function textAfter(f) {
      var n = 0;
      for (var x = f.nextElementSibling; x && x.tagName === 'P'; x = x.nextElementSibling) n += x.textContent.length;
      return n;
    }
    function balance() {
      host.querySelectorAll('figure.sfig.photo.solo').forEach(function (f) {
        for (var k = 0; k < 2 && textAfter(f) < 700; k++) {
          var prev = f.previousElementSibling;
          if (!prev || prev.tagName !== 'P') break;
          // выше уже стоит снимок сбоку — два рядом сожмут текст
          var near = false;
          for (var y = prev.previousElementSibling, i = 0; y && i < 3; y = y.previousElementSibling, i++) if (y.matches('figure.solo')) near = true;
          if (near) break;
          prev.before(f);
        }
      });
    }
    host.querySelectorAll('figure.sfig:not(.photo):not(.map) > a > img').forEach(function (img) {
      function check() { if (img.naturalHeight > img.naturalWidth * 1.05) { img.closest('figure').classList.add('photo', 'solo'); balance(); } }
      if (img.complete && img.naturalWidth) check(); else img.addEventListener('load', check, { once: true });
    });
    balance();
    // клик по фото — лайтбокс вместо новой вкладки
    host.querySelectorAll('figure.sfig > a').forEach(function (a) {
      a.addEventListener('click', function (e) {
        if (e.metaKey || e.ctrlKey || e.shiftKey) return;
        e.preventDefault();
        var cap = a.parentNode.querySelector('figcaption');
        $('lightbox-img').src = a.getAttribute('href');
        $('lightbox-img').alt = '';
        $('lightbox-cap').textContent = cap ? cap.childNodes[0] && cap.textContent.replace(/\s+/g, ' ').trim() : '';
        $('lightbox').hidden = false;
      });
    });
    // плавное появление иллюстраций
    if ('IntersectionObserver' in window && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }); }, { rootMargin: '0px 0px -8% 0px' });
      host.querySelectorAll('figure.sfig, .sgal').forEach(function (f) { if (f.closest('.sgal') && f.matches('figure')) return; f.classList.add('reveal'); io.observe(f); });
    }
    // полоса прогресса чтения
    var bar = el('div', { class: 'story-progress' }, el('i'));
    document.body.appendChild(bar);
    window.addEventListener('scroll', function () {
      if (currentView !== 'story') { bar.hidden = true; return; }
      bar.hidden = false;
      var r = host.getBoundingClientRect(), total = r.height - innerHeight;
      bar.firstChild.style.width = Math.max(0, Math.min(1, -r.top / Math.max(1, total))) * 100 + '%';
    }, { passive: true });
  }

  var storyNav = null;
  function buildStoryNav(host) {
    if (!$('story-nav')) {   // the story page may omit the slot: put the navigation before the first section
      var first = host.querySelector('section');
      var slot = el('div', { id: 'story-nav' });
      if (first) first.parentNode.insertBefore(slot, first); else host.insertBefore(slot, host.firstChild);
    }
    var nav = clear($('story-nav'));
    var go = function (id) { var t = document.getElementById(id); if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' }); storyAnchor = id; syncUrl(true); };
    var line = el('div', { class: 'tl' });
    STORY_TIME.forEach(function (e) {
      line.appendChild(el('button', { class: 'tl-item', title: e[1], onclick: function () { go(e[2]); } }, el('b', { text: e[0] }), el('span', { text: e[1] })));
    });
    var blocks = Array.prototype.slice.call(host.querySelectorAll('section > p, section > ul > li, section > figure'))
      .filter(function (b) { return !b.closest('#s-archives'); });
    var status = el('div', { class: 'pl-status', hidden: true });
    var chips = el('div', { class: 'pl-chips' });
    var active = null;
    var byName = {};
    function reset(keepUrl) {
      active = null; host.classList.remove('filtering'); status.hidden = true;
      blocks.forEach(function (b) { b.classList.remove('hit'); });
      chips.querySelectorAll('button').forEach(function (c) { c.setAttribute('aria-pressed', 'false'); });
      if (!keepUrl && storyPlace) { storyPlace = null; syncUrl(true); }
    }
    function activate(name, scroll) {
      var e = byName[name]; if (!e) return;
      reset(true); active = name; storyPlace = name;
      e.btn.setAttribute('aria-pressed', 'true'); host.classList.add('filtering');
      e.hits.forEach(function (b) { b.classList.add('hit'); });
      status.hidden = false; clear(status);
      status.appendChild(el('span', { text: name + ' —' }));
      var i = 0, hits = e.hits, cnt = el('b');
      var show = function (move) { if (move !== false) hits[i].scrollIntoView({ block: 'center' }); cnt.textContent = (i + 1) + ' / ' + hits.length; };
      status.appendChild(cnt);
      status.appendChild(el('button', { class: 'btn', text: '↑', title: T('Предыдущий'), onclick: function () { i = (i - 1 + hits.length) % hits.length; show(); } }));
      status.appendChild(el('button', { class: 'btn', text: '↓', title: T('Следующий'), onclick: function () { i = (i + 1) % hits.length; show(); } }));
      status.appendChild(el('button', { class: 'btn', text: T('Сбросить'), onclick: function () { reset(); } }));
      show(scroll);
    }
    STORY_PLACES.forEach(function (pl, n) {
      // метки data-pl проставлены при сборке по русскому тексту: в переводах корней мест нет
      var hits = blocks.filter(function (b) { return b.dataset.pl != null ? b.dataset.pl.split(',').indexOf(String(n)) >= 0 : pl[1].test(b.textContent); });
      if (!hits.length) return;
      var btn = el('button', { 'aria-pressed': 'false', onclick: function () {
        if (active === pl[0]) { reset(); return; }
        activate(pl[0], true); syncUrl(true);
      } }, pl[0], el('small', { text: String(hits.length) }));
      byName[pl[0]] = { btn: btn, hits: hits };
      chips.appendChild(btn);
    });
    storyNav = { setPlace: function (name, anchorGiven) { if (name && byName[name]) activate(name, !anchorGiven); else if (active) reset(true); } };
    var chapters = el('div', { class: 'pl-chips' });
    host.querySelectorAll('section[id] > h3').forEach(function (h) {
      var t = h.cloneNode(true); var y = t.querySelector('.yr'); if (y) y.remove();
      chapters.appendChild(el('button', { onclick: function () { go(h.parentNode.id); } }, t.textContent.trim()));
    });
    nav.appendChild(el('div', { class: 'nav-block' }, el('h4', { text: T('По времени') }), line));
    nav.appendChild(el('div', { class: 'nav-block' }, el('h4', { text: T('По местам') }), chips));
    nav.appendChild(el('details', { class: 'nav-block' }, el('summary', { text: T('Главы') }), chapters));
    nav.appendChild(status);
    // на широком экране навигация уезжает в боковую колонку
    var page = host.closest('.page');
    var aside = el('aside', { class: 'story-rail' });
    page.appendChild(aside);
    var mq = window.matchMedia('(min-width: 1180px)');
    var place = function () { if (mq.matches) aside.appendChild(nav); else host.insertBefore(nav, host.querySelector('#story-nav-slot')); };
    nav.before(el('span', { id: 'story-nav-slot' }));
    place(); mq.addEventListener('change', place);
    // scrollspy: подсветка текущего момента на ленте
    var items = Array.prototype.slice.call(line.children), targets = STORY_TIME.map(function (e) { return document.getElementById(e[2]); });
    var spy = function () {
      if (currentView !== 'story') return;
      var cur = -1;
      targets.forEach(function (t, i) { if (t && t.getBoundingClientRect().top < innerHeight * 0.35) cur = i; });
      items.forEach(function (it, i) { it.classList.toggle('on', i === cur); it.classList.toggle('past', i < cur); });
      if (cur >= 0 && mq.matches) { var it = items[cur], box = line; if (it.offsetTop < box.scrollTop || it.offsetTop > box.scrollTop + box.clientHeight - 40) box.scrollTop = it.offsetTop - 60; }
    };
    window.addEventListener('scroll', spy, { passive: true }); spy();
    var up = el('button', { class: 'btn story-up', hidden: true, text: T('↑ Время и места'), onclick: function () { nav.scrollIntoView({ behavior: 'smooth', block: 'start' }); } });
    nav.parentNode.appendChild(up);
    if ('IntersectionObserver' in window) new IntersectionObserver(function (es) {
      up.hidden = es[0].isIntersecting || currentView !== 'story';
    }).observe(nav);
  }

  // ---------- family atlas
  var placeFilter = 'all', placeMap = null, placeLayers = null, placeMapReady = false, placeMarkers = {};
  // «Архангельск → Архангельская область» и «Москва → Москва» читаются как повтор: показываем одну строку.
  function placeThenNow(pl) {
    var then = (pl.then || pl.where || '').trim(), now = (pl.now || pl.where || '').trim();
    var norm = function (x) { return x.toLocaleLowerCase('ru-RU').replace(/[^\p{L}]/gu, ''); };
    if (!now || norm(then) === norm(now) || norm(now).indexOf(norm(then)) === 0) return { then: '', now: now || then };
    if (then && norm(then).indexOf(norm(now)) >= 0) return { then: '', now: then };
    return { then: then, now: now };
  }
  function placeBySlug(slug) { return D.places.filter(function (p) { return p.slug === slug; })[0]; }
  function placeGroup(id) { return (D.place_groups || []).filter(function (g) { return g.id === id; })[0]; }
  function placeColor(id) { var g = placeGroup(id); return g ? g.color : '#8a4b2a'; }
  function matchedPlace(place) {
    var value = (place || '').toLocaleLowerCase('ru-RU');
    return D.places.filter(function (p) {
      return (p.aliases || []).some(function (alias) { return value.indexOf(alias.toLocaleLowerCase('ru-RU')) >= 0; });
    });
  }
  function placeDateKey(date) { var y = /(18|19|20)\d{2}/.exec(date || ''); return y ? +y[0] : 9999; }
  function recordPlaces(record) {
    if (Array.isArray(record.place_slugs)) return record.place_slugs.map(placeBySlug).filter(Boolean);
    return matchedPlace(record.place_as_recorded || record.place);
  }
  function placeHasCoordinates(pl) { return Number.isFinite(pl.lat) && Number.isFinite(pl.lon); }
  function placeChronology(pl) {
    var events = (pl.timeline || []).map(function (e) { return { date: e.date, text: e.text, kind: e.kind, people: e.people || [], sources: e.sources || [], key: placeDateKey(e.date) }; });
    var labels = { residence: T('Запись о проживании'), birth: T('Запись о рождении'), death: T('Запись о смерти'), burial: T('Место погребения'), baptism: T('Дата рождения; место крещения') };
    D.people.forEach(function (p) {
      var records = (p.residences || []).map(function (r) { return { record: r, kind: 'residence' }; });
      ['birth', 'death', 'burial'].forEach(function (kind) { if (p[kind]) records.push({ record: p[kind], kind: kind }); });
      records.forEach(function (item) {
        var r = item.record;
        if (!recordPlaces(r).some(function (x) { return x.slug === pl.slug; })) return;
        var kind = r.place_event_kind || item.kind, date = r.date || T('Дата не указана');
        if (events.some(function (e) { return e.kind === kind && e.people.indexOf(p.id) >= 0 && e.date === fmtDate(date); })) return;
        events.push({ date: fmtDate(date), text: p.display_name + ' — ' + labels[kind] + ': ' + (r.place_as_recorded || r.place) + (r.note ? '. ' + r.note : ''), people: [p.id], sources: r.source_ids || [], key: placeDateKey(date) });
      });
    });
    events.sort(function (a, b) { return a.key - b.key || a.date.localeCompare(b.date, 'ru'); });
    return events;
  }
  // Ссылки на документы в тексте места — сноски: «(S4, S9)» превращается в маленькие номера ¹ ², которые открывают документ.
  // Номера общие для всей панели и совпадают с нумерованным списком источников внизу.
  var placeRefNums = null;
  function placeRefNumber(id) {
    if (!placeRefNums) return null;
    if (!placeRefNums.map[id]) { placeRefNums.order.push(id); placeRefNums.map[id] = placeRefNums.order.length; }
    return placeRefNums.map[id];
  }
  function readablePlaceText(value) {
    var text = (value || '').replace(/\s*\(((?:S\d+[,;\s]*)+)\)/g, function (m, ids) { return ' ' + ids.trim(); });
    var out = [];
    text.split(/(\bS\d+\b)/g).forEach(function (part) {
      if (!/^S\d+$/.test(part)) { out.push(part.replace(/\s+([,;.])/g, '$1').replace(/[,;]\s*$/, function (x) { return /S\d/.test(part) ? x : x; })); return; }
      if (!S[part]) return;
      var n = placeRefNumber(part);
      out.push(el('sup', { class: 'place-fn' }, el('button', { type: 'button', title: S[part].title, 'aria-label': T('Источник ') + n + ': ' + S[part].title,
        text: String(n), onclick: function () { showSource(part); } })));
    });
    // между соседними сносками убираем запятые и пробелы, чтобы получилось ¹ ² без мусора
    for (var i = 1; i < out.length - 1; i++) if (typeof out[i] === 'string' && /^[\s,;]*$/.test(out[i]) && typeof out[i - 1] !== 'string' && typeof out[i + 1] !== 'string') out[i] = '';
    return out;
  }
  function placeSourceLink(id) {
    var s = S[id]; if (!s) return null;
    return el('li', {}, el('a', { class: 'place-source-link', href: '#', onclick: function (e) { e.preventDefault(); showSource(id); }, text: s.title }));
  }
  function placeMedia(m) {
    return el('figure', { class: 'place-media' },
      el('a', { href: m.file, target: '_blank', rel: 'noopener' }, el('img', { src: m.file, alt: m.caption, loading: 'lazy' })),
      el('figcaption', {}, m.caption,
        m.credit ? el('span', { class: 'place-credit' }, ' · ', m.credit_url ? el('a', { href: m.credit_url, target: '_blank', rel: 'noopener', text: m.credit }) : m.credit) : null));
  }
  function openPlace(slug) {
    var pl = placeBySlug(slug); if (!pl) return;
    selectedPlace = slug; selectedId = null;
    var body = clear($('panel-body'));
    placeRefNums = { map: {}, order: [] };
    var g = placeGroup(pl.groups[0]);
    body.appendChild(el('p', { class: 'p-rel', text: g ? g.name.replace(/ · /g, ', ') : T('Семейное место') }));
    body.appendChild(el('h2', { class: 'p-name', text: pl.name }));
    body.appendChild(el('p', { class: 'place-period', text: pl.period || '' }));
    var tn = placeThenNow(pl);
    body.appendChild(el('div', { class: 'place-then-now' + (tn.then ? '' : ' single') },
      tn.then ? el('span', {}, el('small', { text: T('Тогда') }), tn.then) : null,
      el('span', {}, el('small', { text: tn.then ? T('Сейчас') : T('Где') }), tn.now)));
    body.appendChild(el('p', { class: 'place-summary' }, readablePlaceText(pl.text)));
    if (pl.geo_note) body.appendChild(el('p', { class: 'place-geo-note', text: T('Точка на карте: ') + pl.geo_note + '.' }));
    if (pl.people && pl.people.length) {
      body.appendChild(el('h3', { class: 'p-sec', text: T('Люди') }));
      body.appendChild(el('div', { class: 'rel-chips' }, pl.people.map(function (id) { return P[id] ? personChip(id) : null; })));
    }
    if (pl.details && pl.details.length) {
      body.appendChild(el('h3', { class: 'p-sec', text: T('История места') }));
      pl.details.forEach(function (t) { body.appendChild(el('p', { class: 'place-detail' }, readablePlaceText(t))); });
    }
    var events = placeChronology(pl);
    if (events.length) {
      body.appendChild(el('h3', { class: 'p-sec', text: T('Хронология') }));
      body.appendChild(el('ol', { class: 'place-timeline' }, events.map(function (e) {
        return el('li', {}, el('time', { text: e.date }), el('span', { text: e.text }),
          e.sources.length ? el('div', { class: 'place-event-sources' }, e.sources.filter(function (id) { return S[id]; }).map(function (id) {
            return el('button', { title: S[id].title, text: S[id].title, onclick: function () { showSource(id); } });
          })) : null);
      })));
    }
    if (pl.media && pl.media.length) {
      body.appendChild(el('h3', { class: 'p-sec', text: T('Фотографии и карты') }));
      body.appendChild(el('div', { class: 'place-media-grid' }, pl.media.map(placeMedia)));
    }
    if (pl.materials && pl.materials.length) {
      body.appendChild(el('h3', { class: 'p-sec', text: T('Посмотреть и прочитать') }));
      body.appendChild(el('ul', { class: 'place-links' }, pl.materials.map(function (m) {
        return el('li', {}, el('a', { href: m.url, target: '_blank', rel: 'noopener', text: m.label }));
      })));
    }
    (pl.sources || []).forEach(function (id) { if (S[id]) placeRefNumber(id); });
    var refs = placeRefNums.order.filter(function (id) { return S[id]; });
    placeRefNums = null;
    if (refs.length) {
      body.appendChild(el('h3', { class: 'p-sec', text: T('Документы и источники') }));
      body.appendChild(el('ol', { class: 'place-links place-sources' }, refs.map(placeSourceLink)));
    }
    var panel = $('panel'); panel.classList.add('open'); panel.setAttribute('aria-hidden', 'false'); panel.scrollTop = 0;
    if (window.matchMedia('(max-width: 720px)').matches) $('scrim').hidden = false;
    focusPlaceOnMap(slug);
    syncUrl();
  }
  function renderPlaceSuggestions() {
    var found = {};
    D.people.forEach(function (p) {
      var records = (p.residences || []).map(function (r) { return { place: r.place, id: p.id, date: r.date, record: r }; });
      ['birth', 'death', 'burial'].forEach(function (key) { var e = p[key]; if (e && e.place_as_recorded) records.push({ place: e.place_as_recorded, id: p.id, date: e.date, record: e }); });
      records.forEach(function (r) {
        if (recordPlaces(r.record).length) return;
        var label = r.place.replace(/\s*\(S\d+\)/g, '').trim(); if (!label) return;
        // Полное название не объединяет разные сёла с одинаковым сокращением «с.».
        var key = label.toLocaleLowerCase('ru-RU').replace(/\s+/g, ' ').trim();
        var item = found[key] || (found[key] = { place: label, people: [], dates: [] });
        if (label.length > item.place.length) item.place = label;
        if (item.people.indexOf(r.id) < 0) item.people.push(r.id);
        if (r.date && item.dates.indexOf(r.date) < 0) item.dates.push(r.date);
      });
    });
    var items = Object.keys(found).map(function (key) { return found[key]; });
    items.sort(function (a, b) { return b.people.length - a.people.length || a.place.localeCompare(b.place, 'ru'); });
    var host = clear($('place-suggestions'));
    var unlocated = D.places.filter(function (p) { return !placeHasCoordinates(p) && (placeFilter === 'all' || p.groups.indexOf(placeFilter) >= 0); });
    if (unlocated.length) host.appendChild(el('ul', { class: 'place-suggestion-list' }, unlocated.map(function (p) {
      return el('li', {}, el('button', { type: 'button', class: 'route-name', text: p.name, onclick: function () { openPlace(p.slug); } }));
    })));
    if (!items.length) {
      if (!unlocated.length) host.appendChild(el('p', { class: 'empty', text: T('Места этой ветви имеют карточки и точки на карте.') }));
      return;
    }
    function row(x) { return el('li', {}, el('strong', { text: x.place }), el('span', { text: ' · ' + x.people.map(function (id) { return P[id].display_name; }).join(', ') })); }
    host.appendChild(el('ul', { class: 'place-suggestion-list' }, items.slice(0, 5).map(row)));
    if (items.length > 5) host.appendChild(el('details', {}, el('summary', { text: T('Ещё ') + (items.length - 5) + ' ' + plural(items.length - 5, T('место'), T('места'), T('мест')) }), el('ul', { class: 'place-suggestion-list' }, items.slice(5).map(row))));
  }
  // ---------- «Места»: дороги семьи. Слева маршрут ветви по годам, справа карта, которая следует за чтением.
  function routeYear(pl) {
    if (Number.isFinite(pl.sort_year)) return pl.sort_year;
    var p = pl.period || '';
    if (/середин[аы] XX/.test(p)) return 1950;
    if (/XIX/.test(p) && !/\d{4}/.test(p)) return 1850;
    var ys = (p.match(/1[89]\d{2}|20\d{2}/g) || []).map(Number);
    if (!ys.length) return 9999;
    var y = ys.filter(function (x) { return x >= 1850; })[0] || ys[0];
    if (/^\s*до\s/.test(p) && ys[0] === y) y -= 5;
    return y;
  }
  function routeYearLabel(period) {
    var parts = (period || '').split(';').map(function (x) { return x.split(' — ')[0].trim(); }).filter(Boolean);
    var withYear = parts.filter(function (x) { return /\d{4}|XX|XIX/.test(x); });
    var t = (withYear.length ? withYear[withYear.length - 1] : parts[0]) || '';
    return t.replace(/середина\s+/i, 'сер. ').replace(/^около\s+/i, 'ок. ');
  }
  function routeLines() {
    return (D.place_groups || []).filter(function (g) { return placeFilter === 'all' || placeFilter === g.id; }).map(function (g) {
      var stops = D.places.filter(function (p) { return p.groups.indexOf(g.id) >= 0; });
      stops.sort(function (a, b) { return routeYear(a) - routeYear(b) || a.name.localeCompare(b.name, 'ru'); });
      return { group: g, stops: stops };
    }).filter(function (l) { return l.stops.length; });
  }
  function routeLabel(a, b, group) {
    var r = (D.place_routes || []).filter(function (x) {
      return x.group === group && x.from_place === a.slug && x.to_place === b.slug;
    })[0];
    return r ? r.label.replace(/^[^:]+:\s*/, '') : '';
  }
  function placeDistanceKm(a, b) {
    if (!placeHasCoordinates(a) || !placeHasCoordinates(b)) return null;
    var rad = Math.PI / 180, dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
    var h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
    return Math.round(6371.0088 * 2 * Math.asin(Math.min(1, Math.sqrt(h))));
  }
  function routeStop(pl, g) {
    var tn = placeThenNow(pl);
    var people = (pl.people || []).filter(function (id) { return P[id]; });
    var names = people.slice(0, 4).map(function (id) { return P[id].display_name.replace(/\s*\(.*?\)\s*/, ' ').trim(); });
    var shared = pl.groups.length > 1 && placeFilter === 'all' && pl.groups[0] !== g.id;
    return el('li', { class: 'route-stop' + (shared ? ' shared' : ''), 'data-slug': pl.slug, style: '--route-color:' + g.color },
      el('div', { class: 'route-year', title: pl.period || '', text: routeYearLabel(pl.period) }),
      el('div', { class: 'route-body' },
        el('h4', {}, el('button', { type: 'button', class: 'route-name', text: pl.name, onclick: function () { openPlace(pl.slug); } })),
        el('p', { class: 'route-where' }, tn.then ? [el('span', { text: tn.then }), el('span', { class: 'route-arrow', 'aria-label': T('сейчас'), text: ' → ' })] : null, tn.now),
        shared ? el('p', { class: 'route-text muted', text: T('Это место есть и на дороге другой ветви — подробности в карточке.') })
          : el('p', { class: 'route-text', text: (pl.text || '').replace(/\s*\((?:S\d+[,;\s]*)+\)/g, '').replace(/\s*\bS\d+\b/g, '').replace(/\(\s*\)/g, '').replace(/\s+([,;.])/g, '$1') }),
        names.length ? el('p', { class: 'route-people', text: names.join(', ') + (people.length > 4 ? T(' и ещё ') + (people.length - 4) : '') }) : null,
        el('button', { type: 'button', class: 'route-more', text: T('Открыть историю места'), onclick: function () { openPlace(pl.slug); } })));
  }
  function routeGap(a, b, group) {
    var km = placeDistanceKm(a, b), label = routeLabel(a, b, group);
    var txt = km === null ? T('Привязка одного из мест не уточнена') : (km < 3 ? T('рядом') : km + T(' км по прямой'));
    return el('li', { class: 'route-gap', 'aria-hidden': 'true' }, el('span', { text: txt + (label ? '. ' + label : '') }));
  }
  function renderPlaces() {
    var filter = clear($('place-filters'));
    var opts = [{ id: 'all', name: T('Все дороги') }].concat((D.place_groups || []).map(function (g) { return { id: g.id, name: g.name.replace(/ · /g, ', '), color: g.color }; }));
    opts.forEach(function (o) {
      filter.appendChild(el('button', { type: 'button', class: placeFilter === o.id ? 'active' : '', 'aria-pressed': String(placeFilter === o.id),
        style: o.color ? '--route-color:' + o.color : null, text: o.name,
        onclick: function () { placeFilter = o.id; renderPlaces(); var top = $('view-places'); if (top) top.scrollIntoView({ block: 'start' }); } }));
    });
    var host = clear($('places'));
    routeLines().forEach(function (line) {
      var g = line.group, items = [];
      line.stops.forEach(function (pl, i) { if (i) items.push(routeGap(line.stops[i - 1], pl, g.id)); items.push(routeStop(pl, g)); });
      host.appendChild(el('section', { class: 'route-line', style: '--route-color:' + g.color },
        el('header', { class: 'route-line-head' }, el('h3', { text: g.name.replace(/ · /g, ', ') }), el('p', { text: g.about })),
        el('ol', { class: 'route-stops' }, items)));
    });
    renderPlaceSuggestions();
    renderPlaceIndex();
    updatePlaceMap();
  }
  // Алфавитный указатель всех мест: ссылка ведёт к карточке места в списке и к точке на карте.
  function renderPlaceIndex() {
    var host = $('place-index'); if (!host) return;
    clear(host);
    var places = D.places.slice().sort(function (a, b) { return a.name.localeCompare(b.name, 'ru'); });
    $('place-index-count').textContent = places.length;
    var letter = '';
    places.forEach(function (pl) {
      var first = pl.name.charAt(0).toUpperCase();
      if (first !== letter) { letter = first; host.appendChild(el('span', { class: 'place-index-letter', text: letter })); }
      host.appendChild(el('a', { href: '#/places?place=' + pl.slug, text: pl.name, onclick: function (e) {
        e.preventDefault();
        if (placeFilter !== 'all' && pl.groups.indexOf(placeFilter) < 0) { placeFilter = 'all'; renderPlaces(); }
        var node = document.querySelector('#places .route-stop[data-slug="' + pl.slug + '"]');
        if (node) { node.scrollIntoView({ block: 'center', behavior: 'smooth' }); node.classList.add('flash'); setTimeout(function () { node.classList.remove('flash'); }, 1600); }
        flyToPlace(pl.slug, true);
      } }));
    });
  }
  // Какая остановка сейчас «читается»: та, что ближе всего к верхней трети экрана.
  var routeObserver = null, routeActive = null, routeFlyTimer = null;
  function watchRouteStops() {
    if (routeObserver) routeObserver.disconnect();
    if (!('IntersectionObserver' in window)) return;
    var visible = {};
    routeObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { var key = e.target.getAttribute('data-slug'); if (e.isIntersecting) visible[key] = e.target; else delete visible[key]; });
      var best = null, bestD = Infinity, mark = window.innerHeight * (window.matchMedia('(max-width: 720px)').matches ? 0.62 : 0.35);
      Object.keys(visible).forEach(function (k) { var r = visible[k].getBoundingClientRect(), d = Math.abs(r.top + Math.min(r.height, 120) / 2 - mark); if (d < bestD) { bestD = d; best = visible[k]; } });
      if (best) setRouteActive(best);
    }, { rootMargin: '-10% 0px -25% 0px', threshold: [0, .25, .5, 1] });
    document.querySelectorAll('#places .route-stop').forEach(function (n) { routeObserver.observe(n); });
  }
  function setRouteActive(node) {
    if (routeActive === node) return;
    if (routeActive) routeActive.classList.remove('active');
    routeActive = node; node.classList.add('active');
    var slug = node.getAttribute('data-slug');
    clearTimeout(routeFlyTimer);
    routeFlyTimer = setTimeout(function () { flyToPlace(slug, false); }, 260);
  }
  function placeMapColors() {
    var m = /(\d+),\s*(\d+),\s*(\d+)/.exec(getComputedStyle(document.body).backgroundColor) || [0, 255, 255, 255];
    var dark = (0.299 * m[1] + 0.587 * m[2] + 0.114 * m[3]) < 110;
    return dark ? { dark: true, land: '#2c2923', border: '#4a463d', water: '#1b2426' } : { dark: false, land: '#f3efe4', border: '#b9b3a3', water: '#d9e4e2' };
  }
  function markPlace(slug) {
    Object.keys(placeMarkers).forEach(function (k) {
      var m = placeMarkers[k], on = k === slug;
      m.setStyle({ radius: on ? 10 : 6, weight: on ? 3 : 1.5, fillOpacity: on ? 1 : .85 });
      var t = m.getTooltip() && m.getTooltip().getElement(); if (t) t.classList.toggle('on', on);
      if (on) m.bringToFront();
    });
  }
  var lastFly = null;
  function flyToPlace(slug, zoomIn) {
    var p = placeBySlug(slug); if (!placeMap || !p || !placeHasCoordinates(p)) return;
    markPlace(slug);
    var z = Math.max(placeMap.getZoom(), zoomIn ? 8 : 6), target = L.latLng(p.lat, p.lon);
    if (lastFly === slug + z) return;   // уже летим туда же
    lastFly = slug + z;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { placeMap.setView(target, z); return; }
    placeMap.stop();
    // рядом — плавный сдвиг без смены масштаба; далеко — «полёт» с облётом
    var far = placeMap.distance(placeMap.getCenter(), target) > 600000 || Math.abs(placeMap.getZoom() - z) > 1;
    if (far) placeMap.flyTo(target, z, { duration: 1.1, easeLinearity: .2 });
    else placeMap.setView(target, z, { animate: true, pan: { duration: .7, easeLinearity: .2 } });
  }
  function focusPlaceOnMap(slug) { flyToPlace(slug, true); }
  function highlightPlaceMarker(slug) { markPlace(slug); }
  function updatePlaceMap() {
    if (currentView !== 'places' || !window.L || !$('place-map')) return;
    var bar = document.querySelector('.bar'); if (bar) document.documentElement.style.setProperty('--bar-h', bar.offsetHeight + 'px');
    if (!placeMapReady) {
      var col = placeMapColors();
      placeMap = L.map('place-map', { scrollWheelZoom: false, zoomControl: true, zoomSnap: .5, attributionControl: true });
      $('place-map').style.background = col.water;
      placeMap.attributionControl.setPrefix('');
      // подложка: OpenStreetMap (реки, города, подписи на местных языках), приглушённая фильтром .place-tiles;
      // без сети — контуры стран из geo/
      // сайт отдаёт Referrer-Policy: no-referrer, а OSM без Referer отвечает плитками «Access blocked» (403):
      // для плиток передаём только адрес сайта, без пути страницы
      var tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18, referrerPolicy: 'strict-origin-when-cross-origin', className: 'place-tiles' + (col.dark ? ' dark' : ''),
        attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'
      }).addTo(placeMap);
      var tileErrors = 0;
      tiles.on('tileerror', function () { if (++tileErrors === 4) loadBaseGeo(); });
      placeMap.attributionControl.addAttribution(T('Координаты: <a href="https://www.geonames.org/" target="_blank" rel="noopener">GeoNames</a>'));
      placeMap.createPane('base-geo'); placeMap.getPane('base-geo').style.zIndex = 200; placeMap.getPane('base-geo').style.pointerEvents = 'none';
      var loadBaseGeo = function () {
        placeMap.attributionControl.addAttribution(T('Границы: <a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener">Natural Earth</a>'));
        fetch(ROOT + 'geo/family-region-countries.geojson').then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
          .then(function (geo) { L.geoJSON(geo, { pane: 'base-geo', interactive: false, style: { color: col.border, weight: 1, fillColor: col.land, fillOpacity: 1 } }).addTo(placeMap); })
          .catch(function () { $('place-map').classList.add('no-basemap'); });
      };
      L.control.scale({ imperial: false, metric: true, position: 'bottomleft' }).addTo(placeMap);
      placeLayers = L.layerGroup().addTo(placeMap); placeMapReady = true;
    }
    placeMap.invalidateSize(); placeLayers.clearLayers(); placeMarkers = {};
    var bounds = [];
    routeLines().forEach(function (line) {
      var color = line.group.color;
      line.stops.forEach(function (p) {
        if (!placeHasCoordinates(p)) return;
        bounds.push([p.lat, p.lon]);
        if (placeMarkers[p.slug]) return;
        var m = L.circleMarker([p.lat, p.lon], { radius: 6, color: '#fff', weight: 1.5, fillColor: color, fillOpacity: .85 });
        m.bindTooltip(p.name, { permanent: true, direction: 'top', offset: [0, -8], className: 'place-label' });
        m.on('click', function () {
          var n = document.querySelector('#places .route-stop[data-slug="' + p.slug + '"]');
          if (n) n.scrollIntoView({ behavior: 'smooth', block: 'center' });
          openPlace(p.slug);
        });
        m.on('mouseover', function () { var t = m.getTooltip().getElement(); if (t) t.classList.add('hover'); });
        m.on('mouseout', function () { var t = m.getTooltip().getElement(); if (t) t.classList.remove('hover'); });
        m.addTo(placeLayers); placeMarkers[p.slug] = m;
      });
      (D.place_routes || []).filter(function (r) { return r.group === line.group.id; }).forEach(function (r) {
        var a = placeBySlug(r.from_place), b = placeBySlug(r.to_place);
        if (!a || !b || !placeHasCoordinates(a) || !placeHasCoordinates(b)) return;
        var edge = L.polyline([[a.lat, a.lon], [b.lat, b.lon]], { color: color, weight: 2.5, opacity: .75, dashArray: '2 7', lineCap: 'round' });
        edge.bindTooltip(r.label); edge.addTo(placeLayers);
      });
    });
    if (bounds.length) {
      // стартовый кадр — основное скопление мест (до 2500 км от медианной точки); дальние места видны при переходе к ним
      var med = function (i) { var v = bounds.map(function (b) { return b[i]; }).sort(function (x, y) { return x - y; }); return v[Math.floor(v.length / 2)]; };
      var mid = L.latLng(med(0), med(1));
      var core = bounds.filter(function (b) { return mid.distanceTo(b) < 2500000; });
      placeMap.fitBounds(core.length >= 2 ? core : bounds, { padding: [30, 30], maxZoom: 7 });
    }
    routeActive = null;
    watchRouteStops();
  }

  // ---------- архив
  var KINDS = [
    ['civil', T('Документы'), ['civil_record_copy', 'church_record', 'family_archive_document', 'education_record', 'revision_list',
      'digitized_archive_original', 'digitized_archive_case', 'census_record', 'immigration_record']],
    ['military', T('Военные'), ['online_military_record', 'military_record_copy']],
    ['photo', T('Фотографии'), ['family_photo']], ['manuscript', T('Рукописи'), ['family_manuscript', 'letter']],
    ['press', T('Газеты и публикации'), ['newspaper', 'publication', 'published_reference', 'published_register_unlinked_person', 'published_diary']],
    ['grave', T('Надгробия и памятники'), ['gravestone', 'gravestone_image', 'memorial_image']],
    ['family', T('Рассказы семьи'), ['family_report', 'family_testimony']],
    ['online', T('Справочники и базы'), ['online_reference', 'online_archive_index', 'online_archive_catalog', 'archive_database']],
    ['research', T('Находки для проверки'), ['research_scan']]
  ];
  var KIND_OF = {}; KINDS.forEach(function (k) { k[2].forEach(function (x) { KIND_OF[x] = k; }); });
  var arch = { q: '', kind: null, line: null, sort: 'year' };
  // «Сначала семейное»: фотографии, документы и рукописи семьи впереди, справочники и непроверенные находки — в конце
  var KIND_RANK = { photo: 0, civil: 1, manuscript: 2, grave: 3, military: 4, family: 5, press: 6, other: 7, research: 8, online: 9 };
  var srcPeople = null;
  function peopleOfSource(id) {
    if (!srcPeople) {
      srcPeople = {};
      D.people.forEach(function (p) {
        var ids = [].concat(p.identity_source_ids || [], (p.birth || {}).source_ids || [], (p.death || {}).source_ids || []);
        ids.forEach(function (sid) { (srcPeople[sid] = srcPeople[sid] || []).indexOf(p.id) < 0 && srcPeople[sid].push(p.id); });
      });
    }
    return srcPeople[id] || [];
  }
  // год в тексте: «1950», «1950-е», «около 1970–1980-х»; без цифр — век («конец XIX века»)
  function yearIn(t) {
    if (!t) return 0;
    var m = /(1[6-9]\d\d|20[0-2]\d)/.exec(t);
    if (m) return +m[1];
    var c = /(начал\S*|конец|конца|середин\S*)?\s*(XVIII|XVII|XIX|XX)\b/.exec(t);
    if (!c) return 0;
    return { XVII: 1600, XVIII: 1700, XIX: 1800, XX: 1900 }[c[2]] + (!c[1] ? 50 : /^кон/.test(c[1]) ? 90 : /^сер/.test(c[1]) ? 50 : 5);
  }
  // дата снимка или документа для сортировки: «Датировка: …» в описании, датировка реставрации, затем заголовок и описание
  var srcYears = {};
  function srcYear(s) {
    if (srcYears[s.id] == null) {
      var dt = /Датировка:\s*([^.]*)/.exec(s.scope || '');
      var rest = (D.restored || []).filter(function (r) { return r.source_id === s.id; })[0];
      srcYears[s.id] = yearIn(dt && dt[1]) || yearIn(rest && rest.date) || yearIn(s.title) || yearIn(s.scope) || 9999;
    }
    return srcYears[s.id];
  }
  function srcLines(s) {
    var out = {};
    peopleOfSource(s.id).forEach(function (pid) { var k = surnameKey(P[pid].surname) || ''; if (k) out[k] = 1; });
    return Object.keys(out);
  }
  function isImage(f) { return /\.(jpe?g|png|webp)$/i.test(f || ''); }
  // отреставрированные фото: у каждой карточки переключатель «Цвет / Ч/б / Оригинал»
  // «Архив»: вкладки «Документы и фотографии» и «Отреставрированные фото»
  var archMode = 'docs';
  function setArchMode(m) {
    if (m === 'restored' && $('arch-tab-restored').hidden) m = 'docs';
    archMode = m;
    $('arch-docs').hidden = m !== 'docs';
    $('arch-restored').classList.toggle('off', m !== 'restored');
    $('arch-corrections').hidden = m !== 'corrections';
    document.querySelectorAll('.arch-tabs [data-mode]').forEach(function (b) { b.setAttribute('aria-selected', String(b.dataset.mode === m)); });
  }
  var restSetters = [], restSort = 'year', restMode = 'color';
  // год снимка для сортировки: из датировки реставрации («около 1950», «1950-е»), иначе из описания
  function restYear(r) {
    return yearIn(r.date) || srcYear(S[r.source_id]);
  }
  function restLine(r) {
    var ls = srcLines(S[r.source_id]);
    return ls.length ? ls.sort(function (a, b) { return a.localeCompare(b, 'ru'); })[0] : '';
  }
  function renderRestored() {
    var list = (D.restored || []).filter(function (r) { return S[r.source_id]; });
    list.sort(restSort === 'line'
      ? function (a, b) { return (!restLine(a)) - (!restLine(b)) || restLine(a).localeCompare(restLine(b), 'ru') || restYear(a) - restYear(b); }
      : function (a, b) { return restYear(a) - restYear(b); });
    $('rest-sort').querySelectorAll('button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.s === restSort));
      b.onclick = function () { restSort = b.dataset.s; renderRestored(); };
    });
    var box = $('arch-restored'); if (!box || !list.length) return;
    box.hidden = false;
    $('arch-tab-restored').hidden = false;
    $('arch-tab-restored').textContent = T('Отреставрированные фото · ') + list.length;
    document.querySelectorAll('.arch-tabs [data-mode]').forEach(function (b) { b.onclick = function () { setArchMode(b.dataset.mode); syncUrl(); }; });
    setArchMode(archMode);
    restSetters = [];
    // общий переключатель у заголовка: все снимки разом в цвете, в ч/б или оригиналами
    $('rest-all').querySelectorAll('button').forEach(function (b) {
      b.onclick = function () {
        restMode = b.dataset.v;
        restSetters.forEach(function (f) { f(b.dataset.v); });
        $('rest-all').querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      };
    });
    var grid = clear($('restored-grid'));
    var lastLine = null;
    list.forEach(function (r) {
      var s = S[r.source_id];
      if (restSort === 'line' && restLine(r) !== lastLine) {
        lastLine = restLine(r);
        var t = !lastLine ? T('Места') : /ий$/.test(lastLine) ? lastLine.replace(/ий$/, 'ие') : /(ов|ев|ин|ын)$/.test(lastLine) ? lastLine + T('ы') : lastLine;
        grid.appendChild(el('h4', { class: 'rest-group', text: t }));
      }
      var variants = [];
      if (r.color) variants.push(['color', T('Цвет'), r.color, r.color_thumb]);
      if (r.bw) variants.push(['bw', T('Ч/б'), r.bw, r.bw_thumb]);
      if (s.file) variants.push(['orig', T('Оригинал'), s.file, s.thumb || s.file]);
      var cur = variants[0];
      var img = el('img', { src: cur[3], alt: s.title, loading: 'lazy' });
      var setV = function (key) {
        var v = variants.filter(function (x) { return x[0] === key; })[0]; if (!v) return;
        cur = v; img.src = v[3];
        sw.querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.textContent === v[1])); });
      };
      restSetters.push(setV);
      if (restMode !== 'color') setTimeout(function () { setV(restMode); });
      var pic = el('button', { class: 'rest-pic', type: 'button', 'aria-label': T('Открыть снимок и людей на нём'), onclick: function () { openDoc(s.id, cur[0]); } }, img);
      var sw = el('div', { class: 'rest-switch', role: 'group', 'aria-label': T('Вариант') });
      variants.forEach(function (v) {
        sw.appendChild(el('button', { type: 'button', 'aria-pressed': String(v === cur), text: v[1], onclick: function () {
          cur = v; img.src = v[3];
          sw.querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.textContent === v[1])); });
        } }));
      });
      grid.appendChild(el('figure', { class: 'rest-card' }, pic, sw,
        el('figcaption', null, r.date ? el('b', { class: 'rest-date', text: r.date }) : null, s.title, ' ', el('button', { class: 'src', type: 'button', text: s.id, title: T('Оригинал и описание'), onclick: function () { openDoc(s.id); } }))));
    });
  }
  var archFiltersSet = false;
  function renderSources() {
    // на телефоне фильтры при первом показе свёрнуты: иначе они занимают весь экран до первого документа
    if (!archFiltersSet) { archFiltersSet = true; if (window.matchMedia('(max-width: 720px)').matches) $('arch-filters').open = false; }
    var kc = clear($('arch-kind')), lc = clear($('arch-line')), sc = clear($('arch-sort'));
    var chip = function (host, label, on, fn, n) { host.appendChild(el('button', { 'aria-pressed': String(!!on), onclick: fn }, label, n != null ? el('small', { text: String(n) }) : null)); };
    var counts = {}; D.sources.forEach(function (s) { var k = (KIND_OF[s.kind] || ['other'])[0]; counts[k] = (counts[k] || 0) + 1; });
    chip(kc, T('Все'), !arch.kind, function () { arch.kind = null; renderSources(); }, D.sources.length);
    KINDS.forEach(function (k) { if (counts[k[0]]) chip(kc, k[1], arch.kind === k[0], function () { arch.kind = arch.kind === k[0] ? null : k[0]; renderSources(); }, counts[k[0]]); });
    var lines = {}; D.sources.forEach(function (s) { srcLines(s).forEach(function (l) { lines[l] = (lines[l] || 0) + 1; }); });
    chip(lc, T('Все роды'), !arch.line, function () { arch.line = null; renderSources(); });
    Object.keys(lines).sort(function (a, b) { return lines[b] - lines[a]; }).slice(0, 12).forEach(function (l) {
      chip(lc, /ий$/.test(l) ? l.replace(/ий$/, 'ие') : /(ов|ев|ин|ын)$/.test(l) ? l + T('ы') : l, arch.line === l, function () { arch.line = arch.line === l ? null : l; renderSources(); }, lines[l]);
    });
    [['year', T('По времени')], ['family', T('Сначала семейное')], ['id', T('По номеру')]].forEach(function (o) { chip(sc, o[1], arch.sort === o[0], function () { arch.sort = o[0]; renderSources(); }); });
    var q = arch.q.toLowerCase();
    var list = D.sources.filter(function (s) {
      if (arch.kind && (KIND_OF[s.kind] || [''])[0] !== arch.kind) return false;
      if (arch.line && srcLines(s).indexOf(arch.line) < 0) return false;
      if (q) {
        var hay = [s.id, s.title, s.scope, s.locator].concat(peopleOfSource(s.id).map(function (pid) { return P[pid].display_name; })).join(' ').toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
    var byYear = function (a, b) { return srcYear(a) - srcYear(b) || (+a.id.slice(1)) - (+b.id.slice(1)); };
    var rank = function (s) { var r = KIND_RANK[(KIND_OF[s.kind] || ['other'])[0]]; return r == null ? 7 : r; };
    list.sort(arch.sort === 'family' ? function (a, b) { return rank(a) - rank(b) || byYear(a, b); } : arch.sort === 'year' ? byYear : function (a, b) { return (+a.id.slice(1)) - (+b.id.slice(1)); });
    $('arch-count').textContent = list.length + ' ' + plural(list.length, T('документ'), T('документа'), T('документов'));
    var host = clear($('sources'));
    list.forEach(function (s) {
      var k = KIND_OF[s.kind] || ['other', T('Прочее')];
      var y = srcYear(s);
      var pic = s.thumb || (isImage(s.file) ? s.file : null);
      var ppl = peopleOfSource(s.id);
      host.appendChild(el('button', { class: 'acard k-' + k[0] + (pic && /\.pdf$/i.test(s.file || '') ? ' has-pdf' : ''), id: 'src-' + s.id, onclick: function () { openDoc(s.id); } },
        el('div', { class: 'acard-pic' }, pic ? el('img', { src: pic, alt: '', loading: 'lazy' }) : el('span', { class: 'acard-ph', text: /\.pdf$/i.test(s.file || '') ? 'PDF' : (s.url ? '↗' : '¶') })),
        el('div', { class: 'acard-body' },
          el('p', { class: 'acard-kind' }, el('span', { text: k[1] }), y < 9999 ? el('span', { text: ' · ' + y }) : null, el('span', { class: 'acard-id', text: s.id })),
          el('p', { class: 'acard-title', text: s.title }),
          byPerson[s.id] ? el('p', { class: 'acard-cm', text: byPerson[s.id].length + ' ' + plural(byPerson[s.id].length, T('комментарий'), T('комментария'), T('комментариев')) }) : null,
          ppl.length ? el('p', { class: 'acard-ppl', text: ppl.slice(0, 3).map(function (x) { return P[x].display_name; }).join(', ') + (ppl.length > 3 ? T(' и ещё ') + (ppl.length - 3) : '') }) : null)));
    });
    if (!list.length) host.appendChild(el('p', { class: 'sub', text: T('Ничего не нашлось. Попробуйте другое слово или сбросьте фильтры.') }));
    renderCorrections();
    var rl = clear($('research-log'));
    (D.research_log || []).slice().reverse().forEach(function (r) {
      rl.appendChild(el('details', { class: 'rlog-item' }, el('summary', null, el('span', { class: 'rlog-date', text: fmtDate(r.date) }), ' ', r.action),
        el('p', { text: r.result }), r.scope ? el('p', { class: 'where', text: r.scope }) : null));
    });
  }
  // «Журнал исправлений» — отдельная вкладка архива: новые правки сверху, имя открывает карточку, номер — документ
  function renderCorrections() {
    var tb = clear($('corrections').querySelector('tbody'));
    var list = (D.corrections || []).slice().reverse();
    $('arch-tab-corrections').textContent = T('Журнал исправлений · ') + list.length;
    list.forEach(function (c) {
      var pid = c.person_id && P[c.person_id] ? c.person_id : null;
      var who = pid ? el('button', { class: 'linkish', type: 'button', text: P[pid].display_name, onclick: function () { openPerson(pid); } })
        : document.createTextNode(c.person_id || c.family_id || '');
      var why = el('td', null, c.reason ? document.createTextNode(c.reason + ' ') : null);
      (c.source_ids || []).forEach(function (sid) {
        if (S[sid]) why.appendChild(el('button', { class: 'src-chip', type: 'button', text: sid, title: S[sid].title, onclick: function () { openDoc(sid); } }));
      });
      tb.appendChild(el('tr', null, el('td', null, who), el('td', { text: c.field || '' }), el('td', { text: c.previous == null ? '' : String(c.previous) }), el('td', { text: c.current == null ? '' : String(c.current) }), why));
    });
  }
  var docOpen = null;
  function openDoc(id, variant) {
    if (!S[id] && (D.merged_sources || {})[id]) { id = D.merged_sources[id]; variant = 'back'; }   // оборот, объединённый со снимком
    var s = S[id]; if (!s) return;
    docOpen = id;
    var view = clear($('doc-view')), meta = clear($('doc-meta'));
    var rest = (D.restored || []).filter(function (r) { return r.source_id === id; })[0];
    if ((rest || s.back) && isImage(s.file)) {
      // снимок с вариантами: реставрация (цвет, ч/б), оригинал и оборот — переключатель над изображением
      var vars = [];
      if (rest && rest.color) vars.push(['color', T('Цвет'), rest.color]);
      if (rest && rest.bw) vars.push(['bw', T('Ч/б'), rest.bw]);
      vars.push(['orig', rest ? T('Оригинал') : T('Снимок'), s.file]);
      if (s.back) vars.push(['back', T('Оборот'), s.back]);
      var cur = vars.filter(function (v) { return v[0] === variant; })[0] || vars[0];
      var img = el('img', { src: cur[2], alt: s.title });
      var link = el('a', { href: cur[2], target: '_blank', rel: 'noopener', title: T('Открыть в полном размере') }, img);
      var sw = el('div', { class: 'rest-switch doc-switch', role: 'group', 'aria-label': T('Вариант') });
      vars.forEach(function (v) {
        sw.appendChild(el('button', { type: 'button', 'aria-pressed': String(v === cur), text: v[1], onclick: function () {
          cur = v; img.src = v[2]; link.href = v[2];
          sw.querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.textContent === v[1])); });
        } }));
      });
      view.appendChild(el('div', { class: 'doc-rest' }, sw, link));
    } else if (isImage(s.file)) view.appendChild(el('a', { href: s.file, target: '_blank', rel: 'noopener', title: T('Открыть в полном размере') }, el('img', { src: s.file, alt: s.title })));
    else if (/\.pdf$/i.test(s.file || '')) view.appendChild(el('iframe', { src: s.file, title: s.title }));
    else view.appendChild(el('div', { class: 'doc-noimg', text: s.url ? T('Электронный источник — откройте по ссылке справа.') : T('Текстовый источник: сведения приведены справа.') }));
    var k = KIND_OF[s.kind] || ['other', T('Прочее')];
    meta.appendChild(el('p', { class: 'acard-kind' }, el('span', { text: k[1] }), el('span', { class: 'acard-id', text: s.id })));
    meta.appendChild(el('h2', { id: 'doc-title', text: s.title }));
    if (s.scope) meta.appendChild(el('p', { class: 'doc-scope', text: s.scope }));
    if (s.locator) meta.appendChild(el('p', { class: 'where' }, el('b', { text: T('Где хранится: ') }), s.locator));
    if (rest && rest.date) meta.appendChild(el('p', { class: 'where' }, el('b', { text: T('Датировка: ') }), rest.date));
    if (rest && rest.caveats) meta.appendChild(el('details', { class: 'rest-info' }, el('summary', { text: T('О реставрации') }), el('p', { text: rest.caveats })));
    var links = [];
    if (s.file) links.push(el('a', { href: s.file, target: '_blank', rel: 'noopener', download: '', text: T('Скачать файл') }));
    if (s.url) links.push(el('a', { href: s.url, target: '_blank', rel: 'noopener', text: T('Открыть источник ↗') }));
    links.push(el('a', { href: 's/' + id + '.html', text: T('Поделиться'), onclick: function (e) { e.preventDefault(); shareLink(e.currentTarget, id); } }));
    if (links.length) meta.appendChild(el('p', { class: 'doc-links' }, links.map(function (a, i) { return [i ? ' · ' : '', a]; })));
    var ppl = peopleOfSource(id);
    if (ppl.length) {
      meta.appendChild(el('h3', { text: s.kind === 'family_photo' ? T('Люди на снимке') : T('Упомянутые люди') }));
      meta.appendChild(el('div', { class: 'doc-ppl' }, ppl.map(function (pid) { return el('button', { class: 'btn', text: P[pid].display_name, onclick: function () { closeDoc(); openPerson(pid); } }); })));
    }
    var leads = (D.leads || []).filter(function (l) { return (l.source_ids || []).indexOf(id) >= 0 || (l.record || '').indexOf(id) >= 0; });
    if (leads.length) {
      meta.appendChild(el('h3', { text: T('Связанные наводки') }));
      leads.forEach(function (l) { meta.appendChild(el('p', { class: 'where', text: l.id + ' · ' + l.title })); });
    }
    // комментарии к снимку или документу — тот же механизм, что у людей, ключ — номер S###
    var photo = s.kind === 'family_photo';
    meta.appendChild(el('h3', { class: 'cm', text: photo ? T('Кто на снимке? Комментарии') : T('Комментарии') }));
    var cl = el('div', { class: 'comments' });
    meta.appendChild(cl);
    renderCommentList(cl, byPerson[id] || [], photo ? T('Пока никто не написал. Узнали кого-то, знаете, где и когда это снято? Напишите — это главное, что поможет подписать снимок.') : T('Пока никто ничего не добавил.'));
    meta.appendChild(commentForm(id, photo ? T('Например: «Слева — тётя Анна, справа её муж Пётр. Летом, примерно 1985 год».') : T('Что вы знаете об этом документе? Можно поправить расшифровку или дописать подробности.')));
    $('doc').hidden = false;
    document.body.classList.add('doc-open');
    syncUrl();
  }
  // ---------- «Поделиться»: ссылка s/<ключ>.html — у неё своё превью в мессенджерах (заголовок, описание, обложка)
  function shareKey() {
    if (docOpen) return docOpen;
    if (currentView === 'people' && peopleMode === 'bios') return bioOpen ? 'bio-' + bioOpen : 'bios';
    if (selectedId && $('panel').classList.contains('open')) return selectedId;
    if (currentView === 'places') return selectedPlace ? 'place-' + selectedPlace : 'places';
    if (currentView === 'sources') return archMode === 'restored' ? 'restored' : 'archive';
    return { story: 'story', people: 'people', questions: 'questions' }[currentView] || 'tree';
  }
  function shareLink(btn, key) {
    var url = location.href.split('#')[0].replace(/[^\/]*$/, '') + 's/' + (key || shareKey()) + '.html';
    var label = btn.querySelector('.share-label') || btn, old = label.textContent;
    var done = function () { label.textContent = T('Скопировано'); setTimeout(function () { label.textContent = old; }, 1600); };
    // на телефоне — системное меню «Поделиться» (сразу в Телеграм), на компьютере — в буфер обмена
    if (navigator.share && window.matchMedia('(pointer: coarse)').matches) { navigator.share({ title: document.title, url: url }).catch(function () {}); return; }
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, function () { prompt(T('Ссылка:'), url); }); else prompt(T('Ссылка:'), url);
  }
  function closeDoc() { if ($('doc').hidden) return; $('doc').hidden = true; docOpen = null; document.body.classList.remove('doc-open'); syncUrl(); }
  function showSource(id) {
    closePanel();
    showView('sources');
    openDoc(id);
  }
  function lightbox(s) {
    $('lightbox-img').src = s.file;
    $('lightbox-img').alt = s.title;
    $('lightbox-cap').textContent = s.id + ' · ' + s.title;
    $('lightbox').hidden = false;
  }

  // ---------- surname navigation
  // Нормализует женскую форму к мужской: Иванова → Иванов, Покровская → Покровский, Nováková → Novák.
  // Другие написания одной фамилии — site.json → surname_variants: {"Вариант": "Основное написание"}.
  function surnameKey(s) {
    s = (s || '').trim();
    if (!s) return '';
    var special = SITE.surname_variants || {};
    if (/ská$/.test(s)) s = s.replace(/ská$/, 'ský');
    else if (/ová$/.test(s)) s = s.replace(/ová$/, '');
    else if (/ская$/.test(s)) s = s.replace(/ская$/, 'ский');
    else if (/цкая$/.test(s)) s = s.replace(/цкая$/, 'цкий');
    else if (/(ова|ева|ёва|ина|ына)$/.test(s)) s = s.slice(0, -1);
    return special[s] || s;
  }
  function surnamesOf(p) {
    var out = [];
    if (p.placeholder) return out;
    var k = surnameKey(p.surname);
    if (k) out.push(k);
    var m = /\(([А-ЯЁA-Z][^)\s]*)\)/.exec(p.display_name);
    if (m) { var mk = surnameKey(m[1]); if (mk && out.indexOf(mk) < 0) out.push(mk); }
    return out;
  }
  function surnameGroups() {
    var groups = {};
    D.people.forEach(function (p) {
      surnamesOf(p).forEach(function (k) { (groups[k] = groups[k] || []).push(p.id); });
    });
    return Object.keys(groups).map(function (k) {
      var ids = groups[k];
      var set = {}; ids.forEach(function (id) { set[id] = true; });
      function descIn(id, seen) {
        var n = 0;
        childrenOf(id).forEach(function (c) { if (!seen[c]) { seen[c] = true; if (set[c]) n++; n += descIn(c, seen); } });
        return n;
      }
      var tops = ids.filter(function (id) { return !parentsOf(id).some(function (q) { return set[q]; }); });
      var sure = tops.filter(function (id) { return P[id].research_status !== 'unlinked_candidate'; });
      if (sure.length) tops = sure;
      tops.sort(function (a, b) {
        var da = descIn(a, {}), db = descIn(b, {});
        if (db !== da) return db - da;
        var ma = P[a].sex === 'M' ? 0 : 1, mb = P[b].sex === 'M' ? 0 : 1;
        if (ma !== mb) return ma - mb;
        var ya = parseInt(year((P[a].birth || {}).date), 10) || 9999, yb = parseInt(year((P[b].birth || {}).date), 10) || 9999;
        return ya - yb;
      });
      // линия фамилии обычно идёт по мужчине: при равенстве предпочитаем носителя фамилии по рождению
      return { key: k, ids: ids, focus: tops[0] || ids[0] };
    }).sort(function (a, b) { return b.ids.length - a.ids.length || a.key.localeCompare(b.key, LOCALE.lang); });
  }
  function renderBranches() {
    var host = clear($('branches'));
    host.appendChild(el('button', { text: T('Наша семья'), onclick: function () { setFocus(D.start_focus || D.root_person_id); } }));
    (SITE.quick_focus || []).forEach(function (q) {
      if (P[q.person]) host.appendChild(el('button', { text: q.label, onclick: function () { setFocus(q.person); } }));
    });
    surnameGroups().filter(function (g) { return g.ids.length >= 3; }).forEach(function (g) {
      host.appendChild(el('button', {
        class: 'sn', title: g.ids.length + T(' чел. · в центре: ') + P[g.focus].display_name,
        onclick: function () { setFocus(g.focus, { line: g.key }); }
      }, g.key, el('small', { text: ' ' + g.ids.length })));
    });
  }

  function initSearch() {
    var input = $('search'), out = $('search-results'), toggle = $('search-toggle'), panel = $('search-panel');
    function close(returnFocus) {
      panel.hidden = true;
      out.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
      if (returnFocus) toggle.focus();
    }
    toggle.addEventListener('click', function () {
      if (!panel.hidden) { close(true); return; }
      panel.hidden = false;
      toggle.setAttribute('aria-expanded', 'true');
      input.focus();
      run();
    });
    function run() {
      var q = input.value.trim().toLowerCase();
      clear(out);
      if (q.length < 2) { out.hidden = true; return; }
      var hits = D.people.filter(function (p) { return [p.display_name].concat(p.aliases || []).join(' ').toLowerCase().indexOf(q) > -1; }).slice(0, 12);
      if (!hits.length) out.appendChild(el('li', null, el('button', { disabled: true, text: T('Никого не нашлось') })));
      hits.forEach(function (p) {
        out.appendChild(el('li', null, el('button', { onclick: function () { close(false); input.value = ''; showView('tree'); setFocus(p.id); openPerson(p.id); } },
          p.display_name, el('small', { text: [p.relation, lifespan(p)].filter(Boolean).join(' · ') }))));
      });
      out.hidden = false;
    }
    input.addEventListener('input', run);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !out.hidden) { var b = out.querySelector('button:not([disabled])'); if (b) b.click(); }
      if (e.key === 'ArrowDown' && !out.hidden) { var first = out.querySelector('button:not([disabled])'); if (first) { e.preventDefault(); first.focus(); } }
    });
    document.querySelector('.search').addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !panel.hidden) { e.preventDefault(); e.stopPropagation(); close(true); }
    });
    document.querySelector('.search').addEventListener('focusout', function (e) {
      if (!e.currentTarget.contains(e.relatedTarget)) close(false);
    });
    document.addEventListener('click', function (e) { if (!e.target.closest('.search')) close(false); });
  }

  // ---------- wide view: horizontal whole-family chart from the daughters
  var WCW = 240, WCH = 64, WCOL = 294, WROW = 72;
  var wide = { view: { x: 0, y: 0, k: 1 }, built: false, rootFam: null };

  function wideLayout() {
    var cards = {}, order = [], links = [];
    var row = 0;
    function put(id, col, y, cls) {
      if (cards[id]) return cards[id];
      var c = { id: id, col: col, y: y, cls: cls || '' };
      cards[id] = c; order.push(c);
      return c;
    }
    function spouseLabel(id, except) {
      var s = spousesOf(id).filter(function (x) { return except.indexOf(x) < 0; });
      return s.map(function (x) { return P[x].given_names.split(' ')[0]; }).join(', ');
    }
    // descendants subtree growing to the left (col decreases)
    function desc(id, col) {
      if (cards[id]) return cards[id];
      var kids = [];
      (spouseFams[id] || []).forEach(function (f) { f.children.forEach(function (c) { if (kids.indexOf(c) < 0 && !cards[c]) kids.push(c); }); });
      if (!kids.length) { return put(id, col, row++, 'side'); }
      var placed = kids.map(function (c) { return desc(c, col - 1); });
      var y = (placed[0].y + placed[placed.length - 1].y) / 2;
      var me = put(id, col, y, 'side');
      links.push({ from: [id], fromCol: col, to: kids, toCol: col - 1 });
      return me;
    }
    // a family whose children sit in `col`, parents in col+1 (chain = the path child, already known)
    function family(fam, col, chain) {
      var father = fam.partners.filter(function (x) { return P[x].sex === 'M'; })[0];
      var mother = fam.partners.filter(function (x) { return P[x].sex !== 'M'; })[0];
      if (father) ancestor(father, col + 1);
      var kids = [];
      chain.forEach(function (c) { kids.push(c); put(c, col, row++, 'chain'); });
      fam.children.forEach(function (c) { if (chain.indexOf(c) < 0) { kids.push(c); desc(c, col); } });
      // half-siblings: other families of either parent
      fam.partners.forEach(function (par) {
        (spouseFams[par] || []).forEach(function (of) {
          if (of === fam) return;
          var other = of.partners.filter(function (x) { return x !== par; })[0];
          var startRow = row;
          var hk = [];
          of.children.forEach(function (c) { if (!cards[c]) { hk.push(c); desc(c, col); } });
          if (other && !cards[other]) put(other, col + 1, hk.length ? cards[hk[0]].y : row++, 'side');
          if (hk.length) links.push({ from: other ? [other] : [par], fromCol: col + 1, to: hk, toCol: col, half: true });
          if (other) links.push({ marriage: true, a: par, b: other });
          if (!hk.length && row === startRow) row++;
        });
      });
      if (mother) ancestor(mother, col + 1);
      links.push({ from: fam.partners.slice(), fromCol: col + 1, to: kids, toCol: col });
    }
    function ancestor(id, col) {
      var pf = parentFam[id];
      if (pf) family(pf, col, [id]);
      else put(id, col, row++, 'chain');
    }
    var root = D.families.filter(function (f) { return f.id === 'F1'; })[0];
    family(root, 0, root.children.slice());
    return { cards: order, links: links, byId: cards, rows: row, spouseLabel: spouseLabel };
  }

  function renderWide() {
    var L = wideLayout();
    var minCol = Infinity, maxCol = -Infinity;
    L.cards.forEach(function (c) { minCol = Math.min(minCol, c.col); maxCol = Math.max(maxCol, c.col); });
    var PAD = 30;
    function x(col) { return (col - minCol) * WCOL + PAD; }
    function y(r) { return r * WROW + PAD + 18; }
    var W = (maxCol - minCol) * WCOL + WCW + PAD * 2, H = L.rows * WROW + PAD * 2 + 18;
    var stage = $('wide-stage'), host = clear($('wide-cards'));
    stage.style.width = W + 'px'; stage.style.height = H + 'px';
    var titles = { 0: T('Дети'), 1: T('Родители'), 2: T('Деды'), 3: T('Прадеды'), 4: T('Прапрадеды'), 5: T('5-е колено'), 6: T('6-е колено') };
    for (var col = Math.max(0, minCol); col <= maxCol; col++) {
      host.appendChild(el('div', { class: 'wide-col', style: 'left:' + x(col) + 'px', text: titles[col] || '' }));
    }
    var rootIds = parentFam[D.root_person_id] ? parentFam[D.root_person_id].children : [D.root_person_id];
    L.cards.forEach(function (c) {
      var p = P[c.id];
      var sp = c.cls === 'side' ? L.spouseLabel(c.id, []) : '';
      var sub = [lifespan(p), sp ? '⚭ ' + sp : ''].filter(Boolean).join(' · ') || p.relation;
      var n = (byPerson[c.id] || []).length;
      host.appendChild(el('button', {
        class: 'wcard ' + sexClass(c.id) + (isProbable(c.id) ? ' probable' : '') + (c.cls === 'chain' ? ' chain' : '') + (rootIds.indexOf(c.id) >= 0 ? ' root' : ''),
        style: 'left:' + x(c.col) + 'px;top:' + y(c.y) + 'px', title: p.display_name + (p.relation ? ' — ' + p.relation : ''),
        onclick: wideGuard(function () { openPerson(c.id); }),
        ondblclick: function () { showView('tree'); setFocus(c.id); }
      }, el('span', { class: 'nm', text: p.display_name }), el('span', { class: 'yr', text: sub }), n ? el('span', { class: 'badge', text: String(n) }) : null));
    });
    var svg = $('wide-links');
    svg.setAttribute('width', W); svg.setAttribute('height', H);
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    function path(d, cls) {
      var e = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      e.setAttribute('d', d); if (cls) e.setAttribute('class', cls); svg.appendChild(e);
    }
    function cy(id) { return y(L.byId[id].y) + WCH / 2; }
    L.links.forEach(function (l) {
      if (l.marriage) {
        var a = L.byId[l.a], b = L.byId[l.b]; if (!a || !b) return;
        var xa = x(a.col) + WCW + 8;
        path('M' + (x(a.col) + WCW) + ' ' + cy(l.a) + 'H' + xa + 'V' + cy(l.b) + 'H' + (x(b.col) + WCW), 'half');
        return;
      }
      var parents = l.from.filter(function (id) { return L.byId[id]; });
      var kids = l.to.filter(function (id) { return L.byId[id]; });
      if (!parents.length || !kids.length) return;
      var bx = x(l.toCol) + WCW + (WCOL - WCW) / 2 + (l.half ? -8 : 0);
      var ys = parents.map(cy).concat(kids.map(cy));
      var d = 'M' + bx + ' ' + Math.min.apply(null, ys) + 'V' + Math.max.apply(null, ys);
      parents.forEach(function (id) { d += 'M' + x(L.byId[id].col) + ' ' + cy(id) + 'H' + bx; });
      kids.forEach(function (id) { d += 'M' + bx + ' ' + cy(id) + 'H' + (x(L.byId[id].col) + WCW); });
      path(d, l.half ? 'half' : '');
    });
    wide.built = true;
  }

  var wideDrag = { moved: false };
  function wideGuard(fn) { return function (e) { if (wideDrag.moved) { e.preventDefault(); return; } fn(e); }; }
  function wideApply() { $('wide-stage').style.transform = 'translate(' + wide.view.x + 'px,' + wide.view.y + 'px) scale(' + wide.view.k + ')'; }
  function wideZoomAt(f, cx, cy) {
    var v = wide.view, k = Math.min(1.6, Math.max(0.15, v.k * f)), r = k / v.k;
    v.x = cx - (cx - v.x) * r; v.y = cy - (cy - v.y) * r; v.k = k; wideApply();
  }
  function wideFit() {
    var c = $('wide-canvas').getBoundingClientRect(), s = $('wide-stage');
    var k = Math.min(1, (c.width - 16) / s.offsetWidth, (c.height - 16) / s.offsetHeight);
    k = Math.max(k, 0.3);
    wide.view.k = k;
    wide.view.x = Math.max(8, (c.width - s.offsetWidth * k) / 2);
    wide.view.y = s.offsetHeight * k < c.height ? (c.height - s.offsetHeight * k) / 2 : 8;
    wideApply();
  }
  function initWide() {
    var canvas = $('wide-canvas');
    gestures(canvas, wide.view, wideApply, 0.15, wideDrag);
    $('wide-in').onclick = function () { var r = canvas.getBoundingClientRect(); wideZoomAt(1.25, r.width / 2, r.height / 2); };
    $('wide-out').onclick = function () { var r = canvas.getBoundingClientRect(); wideZoomAt(0.8, r.width / 2, r.height / 2); };
    $('wide-fit').onclick = wideFit;
    $('wide-back').onclick = function () { if (document.fullscreenElement) document.exitFullscreen(); showView('sources'); };
    $('open-wide').onclick = function () { showView('wide'); };
    $('wide-full').onclick = function () {
      var sec = $('view-wide');
      if (document.fullscreenElement) document.exitFullscreen();
      else if (sec.requestFullscreen) sec.requestFullscreen().then(function () { setTimeout(wideFit, 150); });
    };
    document.addEventListener('fullscreenchange', function () {
      $('wide-full').textContent = document.fullscreenElement ? T('✕ Выйти из полного экрана') : T('⛶ На весь экран');
      setTimeout(wideFit, 150);
    });
  }

  // ---------- шапка: меню «Ещё» и лента вкладок, которая прокручивается на узком экране
  function tabsEdges() {
    var t = document.querySelector('.tabs');
    if (!t) return;
    t.classList.toggle('more-left', t.scrollLeft > 2);
    t.classList.toggle('more-right', t.scrollLeft + t.clientWidth < t.scrollWidth - 2);
  }
  function syncHeader(name) {
    var menu = $('more-menu');
    if (menu) {
      menu.open = false;
      menu.querySelectorAll('[data-view-link]').forEach(function (a) { a.classList.toggle('on', a.dataset.viewLink === name); });
      menu.classList.toggle('on', !!menu.querySelector('.on'));
    }
    var t = document.querySelector('.tabs'), b = t && t.querySelector('[aria-selected="true"]');
    if (b && t.scrollWidth > t.clientWidth) t.scrollLeft = b.offsetLeft - (t.clientWidth - b.offsetWidth) / 2;
    tabsEdges();
  }
  function initHeader() {
    var t = document.querySelector('.tabs'), menu = $('more-menu');
    if (t) { t.addEventListener('scroll', tabsEdges, { passive: true }); window.addEventListener('resize', tabsEdges); tabsEdges(); }
    if (!menu) return;
    document.addEventListener('click', function (e) { if (menu.open && !menu.contains(e.target)) menu.open = false; });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && menu.open) { menu.open = false; menu.querySelector('summary').focus(); } });
    menu.querySelectorAll('a').forEach(function (a) { a.addEventListener('click', function () { menu.open = false; }); });
  }

  // ---------- boot
  function boot(data) {
    // старые ссылки вида …/gene/index.html#/… — убираем index.html из адресной строки
    if (/\/index\.html$/.test(location.pathname)) { try { history.replaceState(null, '', location.pathname.replace(/index\.html$/, '') + location.search + location.hash); } catch (e) { /* ignore */ } }
    D = data;
    SITE = D.site || {};
    document.body.classList.toggle('no-comments', !SITE.comments);
    index();
    document.querySelectorAll('.tabs button').forEach(function (b) { b.addEventListener('click', function () { showView(b.dataset.view); }); });
    initHeader();
    $('panel-close').onclick = closePanel;
    $('scrim').onclick = closePanel;
    $('share-btn').onclick = function () { shareLink($('share-btn')); };
    $('lightbox-close').onclick = function () { $('lightbox').hidden = true; };
    $('lightbox').addEventListener('click', function (e) { if (e.target.id === 'lightbox') $('lightbox').hidden = true; });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { if (!$('doc').hidden) closeDoc(); else if (!$('lightbox').hidden) $('lightbox').hidden = true; else closePanel(); } });
    $('people-filter').addEventListener('input', function () { calendar.day = null; zodiacSelection = null; zodiacLimit = 24; renderPeople(); syncUrl(true); });
    initCalendar();
    initZodiac();
    $('arch-q').addEventListener('input', function () { arch.q = this.value.trim(); renderSources(); });
    $('doc-close').onclick = closeDoc;
    $('doc').addEventListener('click', function (e) { if (e.target.id === 'doc') closeDoc(); });
    document.querySelectorAll('#qa-nav [data-go]').forEach(function (b) { b.addEventListener('click', function () { var t = $(b.dataset.go); if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' }); }); });
    $('general-form').appendChild(el('h3', { text: T('Общий комментарий') }));
    $('general-form').appendChild(commentForm('general', T('Например: «В древе нет двоюродного брата, сына тёти Анны» или «Фамилия пишется иначе».')));
    initPanZoom();
    initWide();
    initSearch();
    renderBranches();
    renderPlaces();
    renderSources();
    renderRestored();
    loadStory();

    // Режим печати: ?print=wide — только «Всё древо» в натуральную величину (для экспорта в PNG).
    if (/[?&]print=wide/.test(location.search)) {
      document.documentElement.classList.add('print-wide');
      loadComments().then(function () {
        showView('wide');
        renderWide();
        var s = $('wide-stage');
        wide.view = { x: 0, y: 0, k: 1 }; wideApply();
        document.body.style.width = s.offsetWidth + 'px';
        document.body.style.height = s.offsetHeight + 'px';
        document.title = 'READY ' + s.offsetWidth + 'x' + s.offsetHeight;
      });
      return;
    }
    // Древо рисуем сразу по данным, не дожидаясь комментариев: иначе на медленной связи
    // первые секунды видно пустое поле. Значки комментариев дорисовываются, когда они придут.
    renderPeople();
    renderQuestions();
    renderUnmatched();
    renderFeed();
    applyRoute(parseHash(location.hash), true);
    booted = true;
    syncUrl(true);
    loadComments().then(function () {
      if (currentView === 'people') renderPeople();
      renderQuestions();
      renderFeed();
      if (selectedId && byPerson[selectedId] && $('panel').classList.contains('open')) renderCommentList($('panel-body').querySelector('.comments'), byPerson[selectedId] || [], '');
      if (focusId) renderTree();
      if (wide.built) renderWide();
      if (comments.some(function (c) { return S[c.person_id]; })) renderSources();
      if (docOpen && byPerson[docOpen]) renderCommentList($('doc-meta').querySelector('.comments'), byPerson[docOpen], '');
    });
  }

  // data.json и комментарии запрашиваются ещё из <head> (window.genePrefetch), пока грузится app.js
  var pre = window.genePrefetch || {};
  (pre.data || fetch('data.json', { credentials: 'same-origin' }))
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(boot)
    .catch(function (e) { if (window.console) console.error(e); document.body.appendChild(el('p', { class: 'page', text: T('Не удалось загрузить данные. Обновите страницу.') })); });
})();
