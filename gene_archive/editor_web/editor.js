/* gene-archive online editor: people, families, documents, places, readers' proposals,
   history of changes and accounts. Talks to the server at ./api/ (see gene_archive/server.py).
   Every save sends the record as it was loaded ("base"): if someone changed it meanwhile,
   the server answers 409 instead of overwriting their change. */
(function () {
  'use strict';
  var BASE = location.pathname.replace(/[^/]*$/, '');   // …/edit/
  var SITE = BASE.replace(/edit\/$/, '');
  var me = null, data = null, lang = 'ru', tab = 'people', query = '', dirty = false, lastHash = location.hash;
  var showAllProposals = false, proposals = [], buildTimer = null;

  // ---------- helpers
  function $(id) { return document.getElementById(id); }
  function el(tag, attrs) {
    var e = document.createElement(tag);
    for (var k in attrs || {}) {
      var v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'text') e.textContent = v;
      else if (k === 'class') e.className = v;
      else if (k.slice(0, 2) === 'on') e.addEventListener(k.slice(2), v);
      else if (k === 'value') e.value = v;
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (var i = 2; i < arguments.length; i++) add(e, arguments[i]);
    return e;
  }
  function add(parent, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { add(parent, x); }); return; }
    parent.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  function clear(e) { while (e.firstChild) e.removeChild(e.firstChild); return e; }
  function clone(x) { return x == null ? x : JSON.parse(JSON.stringify(x)); }
  function T(s) { var d = DICT[lang]; return (d && d[s]) || s; }
  function getPath(o, path) { return path.split('.').reduce(function (a, k) { return a == null ? undefined : a[k]; }, o); }
  function setPath(o, path, v) {
    var ks = path.split('.'), last = ks.pop();
    ks.forEach(function (k) { if (o[k] == null || typeof o[k] !== 'object') o[k] = {}; o = o[k]; });
    if (v === '' || v == null || (Array.isArray(v) && !v.length && last !== 'notes')) delete o[last]; else o[last] = v;
  }
  function years(p) {
    var b = String(getPath(p, 'birth.date') || '').match(/\d{4}/), d = String(getPath(p, 'death.date') || '').match(/\d{4}/);
    return b || d ? (b ? b[0] : '?') + '–' + (d ? d[0] : '') : '';
  }
  var KINDS = {
    people: { key: 'id', title: function (r) { return r.display_name || r.id; }, sub: years },
    families: { key: 'id', title: function (r) { return famTitle(r); }, sub: function (r) { return (r.children || []).length ? (r.children.length + ' ' + T('детей')) : ''; } },
    sources: { key: 'id', title: function (r) { return r.title || r.id; }, sub: function (r) { return r.kind || ''; } },
    places: { key: 'slug', title: function (r) { return r.name || r.slug; }, sub: function (r) { return r.where || ''; } }
  };
  function byKey(kind, key) { return (data[kind] || []).filter(function (r) { return r[KINDS[kind].key] === key; })[0]; }
  function personName(id) { var p = byKey('people', id); return p ? p.display_name : id; }
  function famTitle(f) { return (f.partners || []).length ? f.partners.map(personName).join(' + ') : T('Братья и сёстры') + ': ' + (f.children || []).slice(0, 2).map(personName).join(', '); }
  function label(kind, key) {
    var r = byKey(kind, key);
    if (!r) return key;
    return key + ' — ' + KINDS[kind].title(r) + (kind === 'people' && years(r) ? ' (' + years(r) + ')' : '');
  }
  function fmtStamp(iso) { try { return new Date(iso).toLocaleString(lang === 'en' ? 'en-GB' : lang === 'ro' ? 'ro-RO' : 'ru-RU', { dateStyle: 'medium', timeStyle: 'short' }); } catch (e) { return iso; } }

  // ---------- server
  function api(method, path, body, headers) {
    var h = { 'X-Gene-Client': '1' };
    if (me) h['X-CSRF-Token'] = me.csrf;
    if (body !== undefined && !(body instanceof Blob)) { h['Content-Type'] = 'application/json'; body = JSON.stringify(body); }
    for (var k in headers || {}) h[k] = headers[k];
    return fetch(BASE + 'api/' + path, { method: method, headers: h, body: body, credentials: 'same-origin' }).then(function (r) {
      return r.text().then(function (t) {
        var j = null; try { j = t ? JSON.parse(t) : null; } catch (e) { j = { error: t }; }
        if (r.status === 401 && path !== 'login') { me = null; showLogin(); }
        if (!r.ok) { var err = new Error((j && j.error) || ('HTTP ' + r.status)); err.status = r.status; err.body = j; throw err; }
        return j;
      });
    });
  }
  function loadData() {
    return api('GET', 'data').then(function (d) {
      data = d;
      ['people', 'families', 'sources', 'places'].forEach(function (k) { data[k] = data[k] || []; });
      buildDatalists();
    });
  }

  // ---------- sign-in and invitations
  function showLogin(message) {
    $('who').textContent = '';
    var name = el('input', { id: 'l-name', autocomplete: 'username', required: true, autocapitalize: 'none' });
    var pw = el('input', { id: 'l-pw', type: 'password', autocomplete: 'current-password', required: true });
    var msg = el('div', { class: message ? 'msg err' : '', text: message || '' });
    var form = el('form', { class: 'login', onsubmit: function (e) {
      e.preventDefault();
      msg.className = ''; msg.textContent = '';
      api('POST', 'login', { name: name.value, password: pw.value }).then(start).catch(function (err) {
        msg.className = 'msg err';
        msg.textContent = err.status === 429 ? T('Слишком много попыток. Попробуйте через 15 минут.') : T('Неверное имя или пароль.');
      });
    } }, el('h1', { text: T('Редактор архива') }), el('p', { text: T('Войдите, чтобы править сведения.') }),
      el('label', { for: 'l-name', text: T('Имя пользователя') }), name, el('label', { for: 'l-pw', text: T('Пароль') }), pw,
      el('button', { class: 'primary', type: 'submit', text: T('Войти') }), msg,
      el('p', { class: 'sub' }, el('a', { href: SITE, text: T('← на сайт') })));
    clear($('app')).appendChild(form);
    name.focus();
  }
  function showInvite(token) {
    api('GET', 'invite?token=' + encodeURIComponent(token)).then(function (u) {
      var pw = el('input', { type: 'password', autocomplete: 'new-password', minlength: '10', required: true, id: 'i-pw' });
      var pw2 = el('input', { type: 'password', autocomplete: 'new-password', minlength: '10', required: true, id: 'i-pw2' });
      var msg = el('div');
      var form = el('form', { class: 'login', onsubmit: function (e) {
        e.preventDefault();
        if (pw.value !== pw2.value) { msg.className = 'msg err'; msg.textContent = T('Пароли не совпадают.'); return; }
        api('POST', 'invite', { token: token, name: u.name, password: pw.value }).then(function () {
          history.replaceState(null, '', BASE); start();
        }).catch(function (err) { msg.className = 'msg err'; msg.textContent = err.message; });
      } }, el('h1', { text: T('Здравствуйте, ') + u.display + '!' }),
        el('p', {}, T('Ваше имя для входа: '), el('b', { text: u.name }), '. ' + T('Придумайте пароль — не короче 10 знаков.')),
        el('label', { for: 'i-pw', text: T('Пароль') }), pw, el('label', { for: 'i-pw2', text: T('Ещё раз') }), pw2,
        el('button', { class: 'primary', type: 'submit', text: T('Сохранить и войти') }), msg);
      clear($('app')).appendChild(form);
      pw.focus();
    }).catch(function () { showLogin(T('Ссылка-приглашение устарела или уже использована. Попросите новую.')); });
  }
  function start() {
    return api('GET', 'me').then(function (m) {
      me = m;
      renderHeader();
      showBuild(m.build);
      return loadData();
    }).then(function () { route(); }).catch(function (err) { if (err.status !== 401) showLogin(err.message); });
  }
  function renderHeader() {
    var who = clear($('who'));
    if (!me) return;
    add(who, [el('span', { text: me.display + (me.role === 'admin' ? ' · ' + T('администратор') : '') }),
      el('a', { href: SITE, target: '_blank', rel: 'noopener', text: T('Сайт') }),
      el('a', { href: '#/account', text: T('Пароль') }),
      el('button', { class: 'link', type: 'button', text: T('Выйти'), onclick: function () {
        api('POST', 'logout', {}).catch(function () {}).then(function () { me = null; showLogin(); });
      } })]);
  }

  // ---------- site rebuild status
  function showBuild(b) {
    var s = $('build');
    if (!b) { s.textContent = ''; return; }
    s.className = 'build' + (b.state === 'building' || b.state === 'queued' ? ' busy' : b.state === 'failed' ? ' fail' : '');
    s.title = b.error || '';
    s.textContent = b.state === 'building' || b.state === 'queued' ? T('Сайт обновляется…')
      : b.state === 'failed' ? T('Сайт не собрался — см. подсказку') : b.finished_at ? T('Сайт обновлён') + ' ' + fmtStamp(b.finished_at) : '';
  }
  function pollBuild(n) {
    clearTimeout(buildTimer);
    buildTimer = setTimeout(function () {
      api('GET', 'status').then(function (r) {
        showBuild(r.build);
        if ((r.build.state === 'building' || r.build.state === 'queued') && (n || 0) < 120) pollBuild((n || 0) + 1);
      }).catch(function () {});
    }, 1500);
  }

  // ---------- navigation
  function setLang(l, quiet) {
    lang = DICT[l] || l === 'ru' ? l : 'ru';
    document.documentElement.lang = lang;
    $('lang').value = lang;
    $('brand').textContent = T('Редактор архива');
    document.title = T('Редактор архива');
    if (!quiet) { try { localStorage.setItem('gene-editor-lang', lang); } catch (e) {} }
  }
  window.addEventListener('beforeunload', function (e) { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
  window.addEventListener('hashchange', function () {
    if (dirty && !confirm(T('Есть несохранённые изменения. Уйти без сохранения?'))) { history.replaceState(null, '', lastHash || '#'); return; }
    dirty = false;
    route();
  });
  function go(hash) {
    if (dirty && !confirm(T('Есть несохранённые изменения. Уйти без сохранения?'))) return;
    dirty = false;
    if (location.hash !== hash) history.pushState(null, '', hash);
    route();
  }
  function route() {
    lastHash = location.hash;
    var inv = location.hash.match(/^#invite=([A-Za-z0-9_-]+)/);
    if (inv) { showInvite(inv[1]); return; }
    if (!me || !data) return;
    var parts = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
    var t = parts[0] || 'people';
    if (KINDS[t]) tab = t;
    else if (['proposals', 'history', 'users', 'account'].indexOf(t) >= 0) tab = t;
    layout();
    var pane = $('pane');
    if (KINDS[t] && parts[1] === 'new') editRecord(pane, t, null, newTemplate(t, parts[2]));
    else if (KINDS[t] && parts[1]) {
      var r = byKey(t, parts[1]);
      if (r) editRecord(pane, t, r); else add(pane, el('p', { class: 'msg err', text: T('Запись не найдена: ') + parts[1] }));
    }
    else if (t === 'proposals') showProposals(pane);
    else if (t === 'history') showHistory(pane);
    else if (t === 'users') showUsers(pane);
    else if (t === 'account') showAccount(pane);
    else add(pane, el('div', { class: 'card' }, el('h2', { text: T('Выберите запись слева') }),
      el('p', { class: 'sub', text: T('или создайте новую. Правки проверяются перед сохранением, попадают в журнал исправлений и в историю, сайт обновляется сам.') })));
  }
  function newTemplate(kind, arg) {
    if (kind === 'people') return { given_names: '', surname: '', sex: 'U', notes: [] };
    if (kind === 'families') {
      var m = (arg || '').match(/^(partner|child)-(I\d+)$/);
      return { partners: m && m[1] === 'partner' ? [m[2]] : [], children: m && m[1] === 'child' ? [m[2]] : [] };
    }
    if (kind === 'sources') return { title: '', kind: 'family_photo' };
    return { slug: '', name: '' };
  }

  // ---------- layout: tabs, search, list
  function layout() {
    var app = clear($('app'));
    var tabs = el('div', { class: 'tabs', role: 'group', 'aria-label': T('Разделы') });
    var items = [['people', T('Люди')], ['families', T('Семьи')], ['sources', T('Документы')], ['places', T('Места')]];
    if (me.role === 'admin') items.push(['proposals', T('Предложения')]);
    items.push(['history', T('История')]);
    if (me.role === 'admin') items.push(['users', T('Пользователи')]);
    items.forEach(function (it) {
      var b = el('button', { type: 'button', 'aria-pressed': String(tab === it[0]), text: it[1], onclick: function () { go('#/' + it[0]); } });
      if (it[0] === 'proposals') {
        var badge = el('span', { class: 'badge' });
        b.appendChild(badge);
        api('GET', 'proposals').then(function (list) { proposals = list; var n = list.filter(function (p) { return p.status === 'new'; }).length; badge.textContent = n ? String(n) : ''; }).catch(function () {});
      }
      tabs.appendChild(b);
    });
    var side = el('aside', { class: 'side' }, tabs);
    if (KINDS[tab]) {
      var q = el('input', { type: 'search', placeholder: T('Поиск: имя, номер, год…'), value: query, 'aria-label': T('Поиск'), oninput: function () { query = q.value; fillList(list); } });
      side.appendChild(el('div', { class: 'find' }, q, el('button', { type: 'button', text: '+ ' + T('Новая запись'), onclick: function () { go('#/' + tab + '/new'); } })));
      var list = el('nav', { class: 'list', 'aria-label': T('Список') });
      side.appendChild(list);
      fillList(list);
    }
    var open = KINDS[tab] && location.hash.split('/').length > 2;
    add(app, el('div', { class: 'layout' + (open ? ' open' : '') }, side, el('section', { class: 'pane', id: 'pane' })));
  }
  function fillList(list) {
    clear(list);
    var k = KINDS[tab], q = query.trim().toLowerCase();
    var current = location.hash.split('/')[2];
    var rows = data[tab].filter(function (r) {
      if (!q) return true;
      return (r[k.key] + ' ' + k.title(r) + ' ' + k.sub(r) + ' ' + (r.aliases || []).join(' ') + ' ' + (r.surname || '')).toLowerCase().indexOf(q) >= 0;
    });
    rows.slice(0, 600).forEach(function (r) {
      list.appendChild(el('button', { type: 'button', 'aria-current': String(r[k.key] === current), onclick: function () { go('#/' + tab + '/' + encodeURIComponent(r[k.key])); } },
        el('b', { text: k.title(r) }), el('small', { text: r[k.key] + (k.sub(r) ? ' · ' + k.sub(r) : '') })));
    });
    if (!rows.length) list.appendChild(el('p', { class: 'empty', text: T('Ничего не нашлось.') }));
  }

  // ---------- form building blocks (all edit the working copy `rec`)
  function field(rec, path, lbl, opts) {
    opts = opts || {};
    var v = getPath(rec, path), input;
    if (opts.type === 'select') {
      input = el('select', {}, opts.options.map(function (o) { return el('option', { value: o[0], text: o[1] }); }));
      input.value = v == null ? (opts.empty || '') : String(v);
    } else if (opts.type === 'textarea') {
      input = el('textarea', { class: opts.cls || '', rows: opts.rows || 4 });
      input.value = v == null ? '' : Array.isArray(v) ? v.join('\n') : v;
    } else if (opts.type === 'check') {
      input = el('input', { type: 'checkbox' });
      input.checked = opts.checked ? opts.checked(v) : !!v;
    } else {
      input = el('input', { type: opts.type || 'text', list: opts.list || null, step: opts.step || null });
      input.value = v == null ? '' : String(v);
    }
    var id = 'f-' + path.replace(/\W/g, '-') + '-' + Math.random().toString(36).slice(2, 7);
    input.id = id;
    var hint = opts.hint ? el('div', { class: 'hint', text: opts.hint }) : null;
    input.addEventListener(opts.type === 'check' || opts.type === 'select' ? 'change' : 'input', function () {
      dirty = true;
      var val = opts.type === 'check' ? (opts.setCheck ? opts.setCheck(input.checked) : input.checked || null)
        : opts.parse ? opts.parse(input.value) : opts.type === 'number' ? (input.value === '' ? null : Number(input.value)) : input.value;
      setPath(rec, path, val);
      if (opts.onchange) opts.onchange(val, hint);
    });
    if (opts.type === 'check') return el('div', { class: 'f check' + (opts.wide ? ' wide' : '') }, input, el('label', { for: id, text: lbl }));
    return el('div', { class: 'f' + (opts.wide ? ' wide' : '') }, el('label', { for: id, text: lbl }), input, hint);
  }
  function chips(rec, path, lbl, kind, opts) {
    opts = opts || {};
    var box = el('div', { class: 'chips' });
    var input = el('input', { list: 'dl-' + kind, placeholder: opts.placeholder || T('добавить…'), 'aria-label': lbl });
    function values() { return (getPath(rec, path) || []).slice(); }
    function draw() {
      Array.prototype.slice.call(box.querySelectorAll('.chip')).forEach(function (c) { c.remove(); });
      values().forEach(function (v, i) {
        var text = el('span', { class: opts.noOpen ? '' : 'open', text: label(kind, v), title: T('Открыть'), onclick: opts.noOpen ? null : function () { go('#/' + kind + '/' + encodeURIComponent(v)); } });
        box.insertBefore(el('span', { class: 'chip' }, text, el('button', { type: 'button', 'aria-label': T('Убрать'), text: '×', onclick: function () {
          var vs = values(); vs.splice(i, 1); setPath(rec, path, vs); dirty = true; draw(); if (opts.onchange) opts.onchange();
        } })), input);
      });
    }
    input.addEventListener('change', function () {
      var key = (input.value.match(kind === 'places' ? /^([a-z0-9][a-z0-9-]*)/ : /^([A-Z]\d+)/) || [])[1];
      if (!key || !byKey(kind, key)) { input.setCustomValidity(T('Выберите из списка')); input.reportValidity(); return; }
      input.setCustomValidity('');
      var vs = values(); if (vs.indexOf(key) < 0) vs.push(key);
      setPath(rec, path, vs); dirty = true; input.value = ''; draw(); if (opts.onchange) opts.onchange();
    });
    box.appendChild(input);
    draw();
    return el('div', { class: 'f' + (opts.wide === false ? '' : ' wide') }, el('label', { text: lbl }), box, opts.hint ? el('div', { class: 'hint', text: opts.hint }) : null);
  }
  function paragraphs(rec, path, lbl, hint) {
    var t = el('textarea', { class: 'long', 'aria-label': lbl });
    t.value = (getPath(rec, path) || []).join('\n\n');
    t.addEventListener('input', function () {
      dirty = true;
      var ps = t.value.split(/\n\s*\n/).map(function (s) { return s.trim(); }).filter(Boolean);
      setPath(rec, path, ps.length ? ps : (path === 'notes' ? [] : null));
      if (path === 'notes') rec.notes = ps;
    });
    return el('div', { class: 'f wide' }, el('label', { text: lbl }), t, el('div', { class: 'hint', text: hint || T('Абзацы разделяйте пустой строкой. Номера документов (S12) станут ссылками.') }));
  }
  function lines(rec, path, lbl) {
    return field(rec, path, lbl, { type: 'textarea', rows: 3, wide: true, hint: T('По одному в строке.'),
      parse: function (v) { var a = v.split(/\n|;/).map(function (s) { return s.trim(); }).filter(Boolean); return a.length ? a : null; } });
  }
  var DATE_HINT = 'Например: 1899, 1899-10-09, 9.10.1899, около 1899, до 1950, между 1900 и 1905.';
  var STATUSES = [['', '—'], ['documented', 'по документу'], ['family_report', 'со слов семьи'], ['uncertain_family_report', 'со слов семьи, неточно'],
    ['calculated_from_age', 'вычислено по возрасту'], ['gravestone', 'по надгробию'], ['publication', 'по публикации'], ['probable', 'вероятно']];
  function eventBox(rec, ev, title) {
    var d = field(rec, ev + '.date', T('Дата'), { hint: T(DATE_HINT), onchange: function (v, hint) {
      var n = normalizeDate(v || '');
      hint.className = 'hint' + (n && n !== v ? ' ok' : '');
      hint.textContent = n && n !== v ? T('Будет записано как: ') + n : T(DATE_HINT);
    } });
    return el('fieldset', {}, el('legend', { text: title }), el('div', { class: 'grid' },
      d,
      field(rec, ev + '.place_as_recorded', T('Место (как в источнике)')),
      field(rec, ev + '.status', T('Откуда известно'), { type: 'select', options: STATUSES.map(function (s) { return [s[0], T(s[1])]; }) }),
      chips(rec, ev + '.place_slugs', T('Место на карте'), 'places', { wide: false }),
      chips(rec, ev + '.source_ids', T('Документы'), 'sources'),
      field(rec, ev + '.note', T('Примечание'), { wide: true })));
  }
  // the same forms as the server understands (gene_archive/editor.py normalize_date) — only for the hint
  function normalizeDate(t) {
    t = t.trim().replace(/\s+/g, ' ').replace(/\s*(г|года?|г\.)\.?$/i, '');
    if (!t) return '';
    var M = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
    var m = t.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
    if (m) return m[3] + '-' + ('0' + m[2]).slice(-2) + '-' + ('0' + m[1]).slice(-2);
    m = t.match(/^(?:между|between)\s+(\d{4})\s+(?:и|and)\s+(\d{4})$/i) || t.match(/^(\d{4})\s*[–—-]\s*(\d{4})$/);
    if (m) return 'BET ' + m[1] + ' AND ' + m[2];
    var q = [[/^(около|ок\.?|примерно|приблизительно|about|abt|circa|c\.)\s+/i, 'ABT'], [/^(до|before|bef)\s+/i, 'BEF'], [/^(после|after|aft)\s+/i, 'AFT']];
    for (var i = 0; i < q.length; i++) if (q[i][0].test(t)) { var rest = t.replace(q[i][0], ''); if (/^\d{4}$/.test(rest)) return q[i][1] + ' ' + rest; }
    return t.toUpperCase() === t ? t : (/^\d{4}(-\d{2}(-\d{2})?)?$/.test(t) ? t : t.replace(/^(abt|bef|aft|bet|est|cal)\b/i, function (x) { return x.toUpperCase(); }));
  }
  var KNOWN = {
    people: ['id', 'given_names', 'surname', 'display_name', 'sex', 'relation', 'aliases', 'identity_source_ids', 'birth', 'death', 'burial', 'notes', 'research_status', 'research_note', 'living', 'placeholder'],
    families: ['id', 'partners', 'relation', 'children', 'probable_children', 'adopted_children', 'probable_note', 'marriage', 'source_ids', 'notes'],
    sources: ['id', 'title', 'kind', 'file', 'back', 'url', 'locator', 'scope', 'preview_page', 'hidden'],
    places: ['slug', 'name', 'where', 'lat', 'lon', 'geo_note', 'period', 'then', 'now', 'aliases', 'text', 'details', 'sort_year']
  };
  function extraBox(kind, rec, holder) {
    var extra = {};
    Object.keys(rec).forEach(function (k) { if (KNOWN[kind].indexOf(k) < 0) extra[k] = rec[k]; });
    var t = el('textarea', { class: 'code', spellcheck: 'false', 'aria-label': T('Другие поля (JSON)') });
    t.value = Object.keys(extra).length ? JSON.stringify(extra, null, 2) : '';
    t.addEventListener('input', function () { dirty = true; });
    holder.extra = function () {
      var v = t.value.trim();
      var obj = v ? JSON.parse(v) : {};
      if (typeof obj !== 'object' || Array.isArray(obj)) throw new Error('{}');
      Object.keys(rec).forEach(function (k) { if (KNOWN[kind].indexOf(k) < 0) delete rec[k]; });
      Object.keys(obj).forEach(function (k) { if (KNOWN[kind].indexOf(k) < 0) rec[k] = obj[k]; });
    };
    return el('details', { class: 'card' }, el('summary', { text: T('Другие поля (JSON)') + (Object.keys(extra).length ? ' · ' + Object.keys(extra).join(', ') : '') }),
      el('p', { class: 'sub', text: T('Поля, для которых нет формы (места жительства, профили, другие версии дат…), — в формате JSON, как в family_tree.json.') }), t);
  }

  // ---------- record forms
  var SOURCE_KINDS = ['family_photo', 'family_archive_document', 'civil_record_copy', 'church_record', 'revision_list', 'census_record', 'education_record',
    'immigration_record', 'digitized_archive_original', 'digitized_archive_case', 'online_military_record', 'military_record_copy', 'family_manuscript', 'letter',
    'newspaper', 'publication', 'published_reference', 'published_diary', 'gravestone', 'gravestone_image', 'memorial_image', 'family_report', 'family_testimony',
    'online_reference', 'online_archive_index', 'online_archive_catalog', 'archive_database', 'research_scan'];

  function editRecord(pane, kind, original, template) {
    var rec = clone(original || template), holder = {};
    var k = KINDS[kind], isNew = !original;
    var head = el('div', {}, el('button', { class: 'link back', type: 'button', text: '← ' + T('К списку'), onclick: function () { go('#/' + kind); } }), el('h2', { text: isNew ? T('Новая запись') : k.title(original) }),
      el('p', { class: 'sub', text: isNew ? T('Номер будет присвоен при сохранении.') : (original[k.key] + (k.sub(original) ? ' · ' + k.sub(original) : '')) }));
    var body = el('div');
    if (kind === 'people') personForm(body, rec, original);
    else if (kind === 'families') familyForm(body, rec);
    else if (kind === 'sources') sourceForm(body, rec, original);
    else placeForm(body, rec, isNew);
    body.appendChild(extraBox(kind, rec, holder));
    var msg = el('div', { role: 'status', 'aria-live': 'polite' });
    var reason = el('input', { class: 'reason', placeholder: T('Почему изменено (попадёт в журнал исправлений)'), 'aria-label': T('Причина правки') });
    var why = { source_ids: [] };
    var save = el('button', { class: 'primary', type: 'button', text: T('Сохранить'), onclick: function () { submit(); } });
    var del = isNew ? null : el('button', { class: 'danger', type: 'button', text: T('Удалить'), onclick: function () {
      if (!confirm(T('Удалить запись ') + original[k.key] + '? ' + T('Ссылки на неё в других записях нужно убрать заранее — иначе удаление не пройдёт.'))) return;
      api('POST', 'delete', { kind: kind, base: original, reason: reason.value }).then(function () {
        dirty = false; return loadData();
      }).then(function () { go('#/' + kind); pollBuild(); }).catch(showError);
    } });
    function showError(err) {
      clear(msg).className = 'msg err';
      add(msg, el('b', { text: err.message }));
      if (err.status === 409) {
        add(msg, el('p', { text: T('Ваши изменения не сохранены. Скопируйте их, если нужно, и откройте свежую версию.') }),
          el('details', {}, el('summary', { text: T('Мои изменения (JSON)') }), el('pre', { class: 'mono', text: JSON.stringify(rec, null, 2) })),
          el('button', { type: 'button', text: T('Открыть свежую версию'), onclick: function () { dirty = false; loadData().then(route); } }));
      } else if (err.body && err.body.errors && err.body.errors.length > 1) {
        add(msg, el('ul', {}, err.body.errors.map(function (e) { return el('li', { text: e }); })));
      }
      msg.scrollIntoView({ block: 'nearest' });
    }
    function submit() {
      try { holder.extra(); } catch (e) { showError(new Error(T('В поле «Другие поля (JSON)» ошибка: ') + e.message)); return; }
      if (kind === 'people' && !rec.display_name) rec.display_name = [rec.given_names, rec.surname].filter(Boolean).join(' ');
      save.disabled = true;
      api('POST', 'save', { kind: kind, record: rec, base: original || null, reason: reason.value, source_ids: why.source_ids, proposal: editRecord.proposal || null })
        .then(function (r) {
          editRecord.proposal = null;
          dirty = false;
          return loadData().then(function () {
            go('#/' + kind + '/' + encodeURIComponent(r.id));
            var m = $('pane').querySelector('[role=status]');
            if (m) {
              m.className = 'msg ' + (r.warnings.length ? 'warn' : 'ok');
              add(m, el('b', { text: r.changed.length ? T('Сохранено.') + ' ' + T('Сайт обновится через несколько секунд.') : T('Изменений нет.') }));
              if (r.warnings.length) add(m, el('ul', {}, r.warnings.map(function (w) { return el('li', { text: w }); })));
            }
            pollBuild();
          });
        }).catch(showError).then(function () { save.disabled = false; });
    }
    var whyChips = chips(why, 'source_ids', T('На каком документе основана правка'), 'sources');
    add(clear(pane), [head, msg, body, el('fieldset', {}, el('legend', { text: T('Основание правки') }), whyChips),
      el('div', { class: 'actions' }, reason, save, del)]);
  }

  function personForm(body, rec, original) {
    add(body, el('fieldset', {}, el('legend', { text: T('Имя') }), el('div', { class: 'grid' },
      field(rec, 'given_names', T('Имя и отчество')),
      field(rec, 'surname', T('Фамилия')),
      field(rec, 'display_name', T('Как показывать на сайте'), { hint: T('Пусто — «Имя Фамилия».') }),
      field(rec, 'sex', T('Пол'), { type: 'select', options: [['M', T('мужской')], ['F', T('женский')], ['U', T('неизвестно')]] }),
      field(rec, 'relation', T('Кем приходится'), { hint: T('Например: прадед по маме.') }),
      lines(rec, 'aliases', T('Другие написания, девичья фамилия')),
      chips(rec, 'identity_source_ids', T('Документы, по которым известен человек'), 'sources'))));
    add(body, eventBox(rec, 'birth', T('Рождение')));
    add(body, eventBox(rec, 'death', T('Смерть')));
    add(body, eventBox(rec, 'burial', T('Погребение')));
    add(body, el('fieldset', {}, el('legend', { text: T('Рассказ') }), paragraphs(rec, 'notes', T('Рассказ о жизни'))));
    add(body, el('fieldset', {}, el('legend', { text: T('Статус и приватность') }), el('div', { class: 'grid' },
      field(rec, 'research_status', T('Возможная родня: связь не доказана'), { type: 'check', checked: function (v) { return v === 'unlinked_candidate'; }, setCheck: function (c) { return c ? 'unlinked_candidate' : null; }, wide: true }),
      field(rec, 'research_note', T('Почему связь под вопросом'), { wide: true }),
      field(rec, 'living', T('Живой человек'), { type: 'select', options: [['', T('определять автоматически')], ['true', T('да — показывать только имя')], ['false', T('нет — показывать всё (с согласия)')]],
        parse: function (v) { return v === '' ? null : v === 'true'; } }),
      field(rec, 'placeholder', T('Неизвестный (заглушка)'), { type: 'check' }))));
    if (original) {
      var id = original.id;
      var asChild = data.families.filter(function (f) { return ['children', 'probable_children', 'adopted_children'].some(function (k) { return (f[k] || []).indexOf(id) >= 0; }); });
      var asPartner = data.families.filter(function (f) { return (f.partners || []).indexOf(id) >= 0; });
      var btn = function (f) { return el('button', { type: 'button', text: f.id + ' — ' + famTitle(f), onclick: function () { go('#/families/' + f.id); } }); };
      add(body, el('fieldset', {}, el('legend', { text: T('Семьи') }),
        el('p', { class: 'sub', text: T('Родители, супруги и дети задаются в семьях.') }),
        el('div', { class: 'related' }, asChild.map(btn), asPartner.map(btn),
          !asChild.some(function (f) { return (f.partners || []).length; }) ? el('button', { type: 'button', text: '+ ' + T('Семья родителей'), onclick: function () { go('#/families/new/child-' + id); } }) : null,
          el('button', { type: 'button', text: '+ ' + T('Новая семья (супруг, дети)'), onclick: function () { go('#/families/new/partner-' + id); } }))));
    }
  }
  function familyForm(body, rec) {
    function probable() {
      host.querySelectorAll('.prob').forEach(function (n) { n.remove(); });
      (rec.children || []).forEach(function (c) {
        var cb = el('input', { type: 'checkbox', id: 'prob-' + c });
        cb.checked = (rec.probable_children || []).indexOf(c) >= 0;
        cb.addEventListener('change', function () {
          dirty = true;
          var a = (rec.probable_children || []).filter(function (x) { return x !== c; });
          if (cb.checked) a.push(c);
          setPath(rec, 'probable_children', a);
        });
        host.appendChild(el('div', { class: 'f check prob wide' }, cb, el('label', { for: 'prob-' + c, text: T('Не доказано, что это ребёнок этой пары: ') + personName(c) })));
      });
    }
    var host = el('div', { class: 'grid' });
    add(host, [chips(rec, 'partners', T('Супруги (не больше двух; пусто — братья и сёстры с неизвестными родителями)'), 'people'),
      field(rec, 'relation', T('Отношения'), { type: 'select', options: [['', '—'], ['spouses', T('супруги')], ['divorced', T('в разводе')], ['siblings', T('братья и сёстры')]] }),
      chips(rec, 'children', T('Дети'), 'people', { onchange: probable }),
      chips(rec, 'adopted_children', T('Приёмные дети'), 'people'),
      field(rec, 'probable_note', T('Почему родство детей под вопросом'), { wide: true })]);
    add(body, el('fieldset', {}, el('legend', { text: T('Состав семьи') }), host));
    probable();
    add(body, eventBox(rec, 'marriage', T('Брак')));
    add(body, el('fieldset', {}, el('legend', { text: T('Документы и рассказ') }), el('div', { class: 'grid' },
      chips(rec, 'source_ids', T('Документы, подтверждающие семью'), 'sources'), paragraphs(rec, 'notes', T('О семье')))));
  }
  function isImage(p) { return /\.(jpe?g|png|webp|gif)$/i.test(p || ''); }
  function fileField(rec, path, lbl) {
    var show = el('div');
    function draw() {
      clear(show);
      var p = rec[path];
      if (!p) { add(show, el('div', { class: 'hint', text: T('Файла нет.') })); return; }
      var href = BASE + 'api/file?path=' + encodeURIComponent(p);
      add(show, [isImage(p) ? el('img', { class: 'preview', src: href, alt: '' }) : null, el('a', { href: href, target: '_blank', rel: 'noopener', text: p }), ' ',
        el('button', { class: 'link', type: 'button', text: T('убрать'), onclick: function () { delete rec[path]; dirty = true; draw(); } })]);
    }
    var input = el('input', { type: 'file', accept: '.jpg,.jpeg,.png,.webp,.gif,.pdf', 'aria-label': lbl });
    var st = el('div', { class: 'hint' });
    input.addEventListener('change', function () {
      var f = input.files[0]; if (!f) return;
      st.textContent = T('Загружаю…');
      api('POST', 'upload', f, { 'X-File-Name': encodeURIComponent(f.name), 'Content-Type': 'application/octet-stream' }).then(function (r) {
        rec[path] = r.path; dirty = true; st.textContent = T('Загружено. Не забудьте сохранить запись.'); input.value = ''; draw();
      }).catch(function (err) { st.textContent = err.message; });
    });
    draw();
    return el('div', { class: 'f' }, el('label', { text: lbl }), show, input, st);
  }
  function sourceForm(body, rec, original) {
    add(body, el('fieldset', {}, el('legend', { text: T('Документ') }), el('div', { class: 'grid' },
      field(rec, 'title', T('Название'), { wide: true, hint: T('Что это и когда: «Метрическая книга с. Красное, 1895: рождение Ивана».') }),
      field(rec, 'kind', T('Вид'), { list: 'dl-kinds' }),
      field(rec, 'preview_page', T('Страница PDF для превью'), { type: 'number' }),
      field(rec, 'hidden', T('Скрыть с сайта (семья попросила убрать)'), { type: 'check', wide: true }),
      fileField(rec, 'file', T('Файл (скан, фото, PDF)')),
      fileField(rec, 'back', T('Оборот снимка')),
      field(rec, 'url', T('Ссылка на запись в интернете'), { type: 'url', wide: true }),
      field(rec, 'locator', T('Где хранится (архив, фонд, опись, дело, лист)'), { wide: true }),
      field(rec, 'scope', T('Расшифровка и что доказывает'), { type: 'textarea', rows: 8, wide: true }))));
    if (original) {
      var re = new RegExp('\\b' + original.id + '\\b');
      var users = data.people.filter(function (p) { return re.test(JSON.stringify(p)); }).map(function (p) { return ['people', p]; })
        .concat(data.families.filter(function (f) { return re.test(JSON.stringify(f)); }).map(function (f) { return ['families', f]; }));
      add(body, el('fieldset', {}, el('legend', { text: T('Где упоминается') }), users.length ? el('div', { class: 'related' }, users.map(function (u) {
        return el('button', { type: 'button', text: u[1].id + ' — ' + KINDS[u[0]].title(u[1]), onclick: function () { go('#/' + u[0] + '/' + u[1].id); } });
      })) : el('p', { class: 'sub', text: T('Пока ни у кого нет ссылки на этот документ.') })));
    }
  }
  function placeForm(body, rec, isNew) {
    add(body, el('fieldset', {}, el('legend', { text: T('Место') }), el('div', { class: 'grid' },
      isNew ? field(rec, 'slug', T('Код (латиницей, например krasnoye)'), { parse: function (v) { return v.toLowerCase().replace(/[^a-z0-9-]+/g, '-'); } }) : null,
      field(rec, 'name', T('Название')),
      field(rec, 'where', T('Где это (губерния, уезд, страна)')),
      field(rec, 'lat', T('Широта'), { type: 'number', step: 'any' }),
      field(rec, 'lon', T('Долгота'), { type: 'number', step: 'any' }),
      field(rec, 'geo_note', T('Что отмечено на карте')),
      field(rec, 'period', T('Годы, когда там жила семья')),
      field(rec, 'then', T('Тогда (административно)')),
      field(rec, 'now', T('Сейчас')),
      field(rec, 'sort_year', T('Год для порядка'), { type: 'number' }),
      lines(rec, 'aliases', T('Другие названия (для поиска в текстах)')),
      field(rec, 'text', T('Коротко для карты'), { type: 'textarea', wide: true }),
      paragraphs(rec, 'details', T('История места')))));
  }

  // ---------- readers' proposals (admins)
  var FIELD_NAMES = { display_name: 'Имя', 'birth.date': 'Дата рождения', 'birth.place': 'Место рождения', 'death.date': 'Дата смерти', 'death.place': 'Место смерти', other: 'Другое' };
  function showProposals(pane) {
    clear(pane);
    add(pane, [el('h2', { text: T('Предложения читателей') }),
      el('p', { class: 'sub', text: T('Родственники предлагают исправления кнопкой «Предложить исправление» в карточке человека. Примените, откройте запись или отклоните.') }),
      field({ v: showAllProposals }, 'v', T('Показывать и обработанные'), { type: 'check', onchange: function (v) { showAllProposals = !!v; dirty = false; showProposals(pane); } })]);
    var host = el('div');
    pane.appendChild(host);
    api('GET', 'proposals').then(function (list) {
      proposals = list;
      var rows = list.filter(function (p) { return showAllProposals || p.status === 'new'; });
      if (!rows.length) host.appendChild(el('p', { class: 'sub', text: T('Новых предложений нет.') }));
      rows.forEach(function (p) {
        var kind = p.target[0] === 'I' ? 'people' : p.target[0] === 'F' ? 'families' : 'sources';
        var rec = byKey(kind, p.target);
        var msg = el('div');
        var card = el('div', { class: 'card' },
          el('div', { class: 'meta', text: '№' + p.id + ' · ' + fmtStamp(p.created_at) + ' · ' + p.author + (p.status !== 'new' ? ' · ' + T(p.status === 'applied' ? 'учтено' : 'отклонено') + (p.handled_by ? ' (' + p.handled_by + ')' : '') : '') }),
          el('p', {}, el('b', { text: rec ? KINDS[kind].title(rec) + ' (' + p.target + ')' : p.target }), ' — ', T(FIELD_NAMES[p.field] || p.field), p.value ? ': ' : '', p.value ? el('b', { text: p.value }) : null),
          p.note ? el('p', { text: p.note }) : null, msg);
        if (p.status === 'new') {
          var row = el('div', { class: 'row' });
          if (rec && kind === 'people' && p.field !== 'other' && p.value) row.appendChild(el('button', { class: 'primary', type: 'button', text: T('Применить'), onclick: function () { applyProposal(p, rec, msg); } }));
          if (rec) row.appendChild(el('button', { type: 'button', text: T('Открыть запись'), onclick: function () { editRecord.proposal = p.id; go('#/' + kind + '/' + p.target); } }));
          row.appendChild(el('button', { type: 'button', text: T('Учтено'), onclick: function () { closeProposal(p, 'applied'); } }));
          row.appendChild(el('button', { class: 'danger', type: 'button', text: T('Отклонить'), onclick: function () { closeProposal(p, 'rejected'); } }));
          card.appendChild(row);
        }
        host.appendChild(card);
      });
    }).catch(function (err) { host.appendChild(el('p', { class: 'msg err', text: err.message })); });
  }
  function closeProposal(p, status) {
    var note = status === 'rejected' ? (prompt(T('Почему отклонено? (необязательно)')) || '') : '';
    api('POST', 'proposal', { id: p.id, status: status, note: note }).then(function () { route(); }).catch(function (err) { alert(err.message); });
  }
  function applyProposal(p, rec, msg) {
    var next = clone(rec);
    var path = { 'birth.place': 'birth.place_as_recorded', 'death.place': 'death.place_as_recorded' }[p.field] || p.field;
    setPath(next, path, p.value);
    api('POST', 'save', { kind: 'people', record: next, base: rec, proposal: p.id,
      reason: T('Предложение №') + p.id + ' (' + p.author + ')' + (p.note ? ': ' + p.note : '') })
      .then(function (r) {
        if (!r.changed.length) return api('POST', 'proposal', { id: p.id, status: 'applied', note: T('уже было так') });
      })
      .then(function () { return loadData(); }).then(function () { pollBuild(); route(); })
      .catch(function (err) { clear(msg).className = 'msg err'; msg.textContent = err.message + ' — ' + T('откройте запись и поправьте вручную.'); });
  }

  // ---------- history
  function showHistory(pane) {
    clear(pane);
    add(pane, [el('h2', { text: T('История правок') }),
      el('p', { class: 'sub', text: me.git ? T('Каждое сохранение — версия в git. Администратор может вернуть данные к любой версии; возврат тоже станет новой правкой.') : T('git не установлен на сервере — история не ведётся.') })]);
    if (!me.git) return;
    api('GET', 'history').then(function (list) {
      var tb = el('tbody');
      list.forEach(function (h, i) {
        tb.appendChild(el('tr', {}, el('td', { text: fmtStamp(h.date) }), el('td', { text: h.author }), el('td', { text: h.message }),
          el('td', {}, me.role === 'admin' && i > 0 ? el('button', { type: 'button', text: T('Вернуть эту версию'), onclick: function () {
            if (!confirm(T('Вернуть все данные к состоянию после этой правки? Более поздние правки отменятся (их можно будет вернуть так же).'))) return;
            api('POST', 'restore', { commit: h.commit }).then(function () { return loadData(); }).then(function () { pollBuild(); route(); }).catch(function (err) { alert(err.message); });
          } }) : null)));
      });
      pane.appendChild(el('table', {}, el('thead', {}, el('tr', {}, el('th', { text: T('Когда') }), el('th', { text: T('Кто') }), el('th', { text: T('Что') }), el('th'))), tb));
    }).catch(function (err) { pane.appendChild(el('p', { class: 'msg err', text: err.message })); });
  }

  // ---------- accounts
  function inviteBox(token) {
    var link = location.origin + BASE + '#invite=' + token;
    return el('div', { class: 'msg ok' }, el('p', { text: T('Отправьте человеку эту ссылку (действует 7 дней, одноразовая). По ней он сам задаст пароль:') }),
      el('div', { class: 'invite mono', text: link }),
      el('button', { type: 'button', text: T('Скопировать'), onclick: function (e) { navigator.clipboard.writeText(link).then(function () { e.target.textContent = T('Скопировано'); }); } }));
  }
  function showUsers(pane, invite) {
    clear(pane);
    var nf = { role: 'editor' };
    var tb = el('tbody');
    add(pane, [el('h2', { text: T('Пользователи') }),
      el('p', { class: 'sub', text: T('Редактор правит сведения. Администратор ещё и разбирает предложения, возвращает версии и управляет пользователями.') }),
      invite ? inviteBox(invite) : null,
      el('table', {}, el('thead', {}, el('tr', {}, el('th', { text: T('Логин') }), el('th', { text: T('Имя') }), el('th', { text: T('Роль') }), el('th'))), tb)]);
    var post = function (body) {
      dirty = false;
      api('POST', 'users', body).then(function (r) { showUsers(pane, r && r.invite); }).catch(function (err) { alert(err.message); });
    };
    api('GET', 'users').then(function (list) {
      list.forEach(function (u) {
        var self = u.name === me.name;
        tb.appendChild(el('tr', {}, el('td', { class: 'mono', text: u.name }), el('td', { text: u.display }),
          el('td', { text: (u.role === 'admin' ? T('администратор') : T('редактор')) + (u.disabled ? ' · ' + T('отключён') : u.active ? '' : ' · ' + T('ждёт приглашения')) }),
          el('td', {}, self ? el('span', { class: 'sub', text: T('это вы') }) : [
            el('button', { type: 'button', text: T('Новая ссылка'), onclick: function () { post({ action: 'invite', name: u.name }); } }), ' ',
            el('button', { type: 'button', text: u.role === 'admin' ? T('Сделать редактором') : T('Сделать администратором'), onclick: function () { post({ action: 'role', name: u.name, role: u.role === 'admin' ? 'editor' : 'admin' }); } }), ' ',
            el('button', { class: u.disabled ? '' : 'danger', type: 'button', text: u.disabled ? T('Включить') : T('Отключить'), onclick: function () { post({ action: u.disabled ? 'enable' : 'disable', name: u.name }); } })])));
      });
    }).catch(function (err) { pane.appendChild(el('p', { class: 'msg err', text: err.message })); });
    add(pane, el('fieldset', {}, el('legend', { text: T('Новый пользователь') }), el('div', { class: 'grid' },
      field(nf, 'name', T('Логин (латиницей)'), { hint: T('Например: anna.k') }),
      field(nf, 'display', T('Имя в истории правок'), { hint: T('Например: тётя Анна') }),
      field(nf, 'role', T('Роль'), { type: 'select', options: [['editor', T('редактор')], ['admin', T('администратор')]] })),
      el('p', {}, el('button', { class: 'primary', type: 'button', text: T('Создать и получить ссылку'), onclick: function () {
        post({ action: 'add', name: nf.name || '', display: nf.display || '', role: nf.role || 'editor' });
      } }))));
  }
  function showAccount(pane) {
    clear(pane);
    var f = {}, msg = el('div');
    add(pane, [el('h2', { text: T('Смена пароля') }), el('div', { class: 'grid' },
      field(f, 'old', T('Текущий пароль'), { type: 'password' }), field(f, 'new', T('Новый пароль (не короче 10 знаков)'), { type: 'password' })),
      el('p', {}, el('button', { class: 'primary', type: 'button', text: T('Сменить пароль'), onclick: function () {
        dirty = false;
        api('POST', 'password', { old: f.old || '', new: f.new || '' }).then(function () { me = null; showLogin(T('Пароль изменён. Войдите с новым паролем.')); })
          .catch(function (err) { msg.className = 'msg err'; msg.textContent = err.message; });
      } })), msg]);
  }

  // ---------- datalists for pickers
  function buildDatalists() {
    document.querySelectorAll('datalist').forEach(function (d) { d.remove(); });
    var mk = function (id, items) { var dl = el('datalist', { id: id }); items.forEach(function (v) { dl.appendChild(el('option', { value: v })); }); document.body.appendChild(dl); };
    mk('dl-people', data.people.map(function (p) { return label('people', p.id); }));
    mk('dl-families', data.families.map(function (f) { return label('families', f.id); }));
    mk('dl-sources', data.sources.map(function (s) { return label('sources', s.id); }));
    mk('dl-places', data.places.map(function (p) { return label('places', p.slug); }));
    mk('dl-kinds', SOURCE_KINDS);
  }

  // ---------- translations of the editor interface (the source text is Russian)
  var DICT = {
    en: {
      'Редактор архива': 'Archive editor', 'Войдите, чтобы править сведения.': 'Sign in to edit the archive.', 'Имя пользователя': 'User name', 'Пароль': 'Password',
      'Войти': 'Sign in', '← на сайт': '← back to the site', 'Слишком много попыток. Попробуйте через 15 минут.': 'Too many attempts. Try again in 15 minutes.',
      'Неверное имя или пароль.': 'Wrong user name or password.', 'Пароли не совпадают.': 'The passwords differ.', 'Здравствуйте, ': 'Hello, ',
      'Ваше имя для входа: ': 'Your user name: ', 'Придумайте пароль — не короче 10 знаков.': 'Choose a password of at least 10 characters.', 'Ещё раз': 'Repeat',
      'Сохранить и войти': 'Save and sign in', 'Ссылка-приглашение устарела или уже использована. Попросите новую.': 'The invitation link has expired or was already used. Ask for a new one.',
      'администратор': 'administrator', 'редактор': 'editor', 'Сайт': 'Site', 'Выйти': 'Sign out', 'Сайт обновляется…': 'Updating the site…',
      'Сайт не собрался — см. подсказку': 'The site build failed — see the tooltip', 'Сайт обновлён': 'Site updated',
      'Есть несохранённые изменения. Уйти без сохранения?': 'You have unsaved changes. Leave without saving?', 'Запись не найдена: ': 'Record not found: ',
      'Выберите запись слева': 'Choose a record on the left',
      'или создайте новую. Правки проверяются перед сохранением, попадают в журнал исправлений и в историю, сайт обновляется сам.': 'or create a new one. Changes are checked before saving, go to the corrections log and the history, and the site updates itself.',
      'Разделы': 'Sections', 'Люди': 'People', 'Семьи': 'Families', 'Документы': 'Documents', 'Места': 'Places', 'Предложения': 'Proposals', 'История': 'History',
      'Пользователи': 'Users', 'Поиск: имя, номер, год…': 'Search: name, id, year…', 'Поиск': 'Search', 'Новая запись': 'New record', 'Список': 'List',
      'Ничего не нашлось.': 'Nothing found.', 'детей': 'children', 'Братья и сёстры': 'Siblings', 'добавить…': 'add…', 'Открыть': 'Open', 'Убрать': 'Remove',
      'Выберите из списка': 'Choose from the list', 'Абзацы разделяйте пустой строкой. Номера документов (S12) станут ссылками.': 'Separate paragraphs with an empty line. Document numbers (S12) become links.',
      'По одному в строке.': 'One per line.', 'Дата': 'Date', 'Например: 1899, 1899-10-09, 9.10.1899, около 1899, до 1950, между 1900 и 1905.': 'For example: 1899, 1899-10-09, about 1899, before 1950, between 1900 and 1905.',
      'Будет записано как: ': 'Will be saved as: ', 'Место (как в источнике)': 'Place (as recorded)', 'Откуда известно': 'How we know', 'Место на карте': 'Place on the map',
      'Примечание': 'Note', 'по документу': 'documented', 'со слов семьи': 'family report', 'со слов семьи, неточно': 'family report, uncertain',
      'вычислено по возрасту': 'calculated from age', 'по надгробию': 'gravestone', 'по публикации': 'publication', 'вероятно': 'probable',
      'Другие поля (JSON)': 'Other fields (JSON)', 'Поля, для которых нет формы (места жительства, профили, другие версии дат…), — в формате JSON, как в family_tree.json.': 'Fields without a form (residences, profiles, alternative dates…) as JSON, as in family_tree.json.',
      'Номер будет присвоен при сохранении.': 'The id is assigned on saving.', 'Почему изменено (попадёт в журнал исправлений)': 'Why (goes to the corrections log)',
      'Причина правки': 'Reason', 'Сохранить': 'Save', 'Удалить': 'Delete', 'Удалить запись ': 'Delete record ',
      'Ссылки на неё в других записях нужно убрать заранее — иначе удаление не пройдёт.': 'Remove references to it from other records first, otherwise the deletion is refused.',
      'Ваши изменения не сохранены. Скопируйте их, если нужно, и откройте свежую версию.': 'Your changes were not saved. Copy them if needed and open the current version.',
      'Мои изменения (JSON)': 'My changes (JSON)', 'Открыть свежую версию': 'Open the current version', 'В поле «Другие поля (JSON)» ошибка: ': 'Error in “Other fields (JSON)”: ',
      'Сохранено.': 'Saved.', 'Сайт обновится через несколько секунд.': 'The site will update in a few seconds.', 'Изменений нет.': 'No changes.',
      'На каком документе основана правка': 'Document the change is based on', 'Основание правки': 'Basis of the change', 'Имя': 'Name', 'Имя и отчество': 'Given names',
      'Фамилия': 'Surname', 'Как показывать на сайте': 'Name shown on the site', 'Пусто — «Имя Фамилия».': 'Empty: “Given names Surname”.', 'Пол': 'Sex',
      'мужской': 'male', 'женский': 'female', 'неизвестно': 'unknown', 'Кем приходится': 'Relation', 'Например: прадед по маме.': 'For example: maternal great-grandfather.',
      'Другие написания, девичья фамилия': 'Other spellings, maiden name', 'Документы, по которым известен человек': 'Documents that identify the person',
      'Рождение': 'Birth', 'Смерть': 'Death', 'Погребение': 'Burial', 'Рассказ': 'Story', 'Рассказ о жизни': 'Life story', 'Статус и приватность': 'Status and privacy',
      'Возможная родня: связь не доказана': 'Possible relative: the link is not proven', 'Почему связь под вопросом': 'Why the link is uncertain',
      'Живой человек': 'Living person', 'определять автоматически': 'decide automatically', 'да — показывать только имя': 'yes — show only the name',
      'нет — показывать всё (с согласия)': 'no — show everything (with consent)', 'Неизвестный (заглушка)': 'Unknown person (placeholder)',
      'Родители, супруги и дети задаются в семьях.': 'Parents, spouses and children are set in families.', 'Семья родителей': 'Parents’ family',
      'Новая семья (супруг, дети)': 'New family (spouse, children)', 'Не доказано, что это ребёнок этой пары: ': 'Not proven to be a child of this couple: ',
      'Супруги (не больше двух; пусто — братья и сёстры с неизвестными родителями)': 'Partners (at most two; empty for siblings with unknown parents)',
      'Отношения': 'Relationship', 'супруги': 'spouses', 'в разводе': 'divorced', 'братья и сёстры': 'siblings', 'Дети': 'Children', 'Приёмные дети': 'Adopted children',
      'Почему родство детей под вопросом': 'Why the children’s link is uncertain', 'Состав семьи': 'Members', 'Брак': 'Marriage', 'Документы и рассказ': 'Documents and story',
      'Документы, подтверждающие семью': 'Documents proving the family', 'О семье': 'About the family', 'Файла нет.': 'No file.', 'убрать': 'remove', 'Загружаю…': 'Uploading…',
      'Загружено. Не забудьте сохранить запись.': 'Uploaded. Do not forget to save the record.', 'Документ': 'Document', 'Название': 'Title',
      'Что это и когда: «Метрическая книга с. Красное, 1895: рождение Ивана».': 'What and when: “Krasnoye parish register, 1895: birth of Ivan”.', 'Вид': 'Kind',
      'Страница PDF для превью': 'PDF page for the thumbnail', 'Скрыть с сайта (семья попросила убрать)': 'Hide from the site (the family asked to remove it)',
      'Файл (скан, фото, PDF)': 'File (scan, photo, PDF)', 'Оборот снимка': 'Back of the photo', 'Ссылка на запись в интернете': 'Link to the online record',
      'Где хранится (архив, фонд, опись, дело, лист)': 'Where it is kept (archive, fonds, file, page)', 'Расшифровка и что доказывает': 'Transcription and what it proves',
      'Где упоминается': 'Referenced by', 'Пока ни у кого нет ссылки на этот документ.': 'Nobody refers to this document yet.', 'Место': 'Place',
      'Код (латиницей, например krasnoye)': 'Code (latin letters, e.g. krasnoye)', 'Где это (губерния, уезд, страна)': 'Where (region, country)', 'Широта': 'Latitude', 'Долгота': 'Longitude',
      'Что отмечено на карте': 'What the map point marks', 'Годы, когда там жила семья': 'Years the family lived there', 'Тогда (административно)': 'Then (administratively)',
      'Сейчас': 'Now', 'Год для порядка': 'Year for sorting', 'Другие названия (для поиска в текстах)': 'Other names (found in texts)', 'Коротко для карты': 'Short text for the map',
      'История места': 'History of the place', 'Дата рождения': 'Date of birth', 'Место рождения': 'Place of birth', 'Дата смерти': 'Date of death', 'Место смерти': 'Place of death',
      'Другое': 'Other', 'Предложения читателей': 'Readers’ proposals',
      'Родственники предлагают исправления кнопкой «Предложить исправление» в карточке человека. Примените, откройте запись или отклоните.': 'Relatives send corrections with the “Suggest a correction” button on a person’s card. Apply, open the record or reject.',
      'Показывать и обработанные': 'Show handled ones too', 'Новых предложений нет.': 'No new proposals.', 'учтено': 'applied', 'отклонено': 'rejected', 'Применить': 'Apply',
      'Открыть запись': 'Open the record', 'Учтено': 'Done', 'Отклонить': 'Reject', 'Почему отклонено? (необязательно)': 'Why rejected? (optional)', 'Предложение №': 'Proposal #',
      'уже было так': 'already so', 'откройте запись и поправьте вручную.': 'open the record and edit it by hand.', 'История правок': 'History of changes',
      'Каждое сохранение — версия в git. Администратор может вернуть данные к любой версии; возврат тоже станет новой правкой.': 'Every save is a git version. An administrator can bring the data back to any version; that becomes a new change too.',
      'git не установлен на сервере — история не ведётся.': 'git is not installed on the server — no history is kept.', 'Вернуть эту версию': 'Restore this version',
      'Вернуть все данные к состоянию после этой правки? Более поздние правки отменятся (их можно будет вернуть так же).': 'Bring all data back to the state after this change? Later changes are undone (and can be restored the same way).',
      'Когда': 'When', 'Кто': 'Who', 'Что': 'What', 'Отправьте человеку эту ссылку (действует 7 дней, одноразовая). По ней он сам задаст пароль:': 'Send this one-time link (valid 7 days); the person sets the password there:',
      'Скопировать': 'Copy', 'Скопировано': 'Copied', 'Редактор правит сведения. Администратор ещё и разбирает предложения, возвращает версии и управляет пользователями.': 'An editor edits the data. An administrator also handles proposals, restores versions and manages users.',
      'отключён': 'disabled', 'ждёт приглашения': 'invitation pending', 'это вы': 'you', 'Новая ссылка': 'New link', 'Сделать редактором': 'Make editor',
      'Сделать администратором': 'Make administrator', 'Включить': 'Enable', 'Отключить': 'Disable', 'Логин': 'Login', 'Роль': 'Role', 'Новый пользователь': 'New user',
      'Логин (латиницей)': 'Login (latin letters)', 'Например: anna.k': 'For example: anna.k', 'Имя в истории правок': 'Name in the history', 'Например: тётя Анна': 'For example: Aunt Anna',
      'Создать и получить ссылку': 'Create and get a link', 'Смена пароля': 'Change password', 'Текущий пароль': 'Current password', 'Новый пароль (не короче 10 знаков)': 'New password (10+ characters)',
      'Сменить пароль': 'Change password', 'К списку': 'Back to the list', 'Пароль изменён. Войдите с новым паролем.': 'Password changed. Sign in with the new password.'
    }
  };
  DICT.ro = {};   // filled below from a compact list to keep the file readable
  [['Редактор архива', 'Editorul arhivei'], ['Войдите, чтобы править сведения.', 'Autentificați-vă pentru a edita arhiva.'], ['Имя пользователя', 'Nume de utilizator'], ['Пароль', 'Parolă'],
    ['Войти', 'Intră'], ['← на сайт', '← înapoi la site'], ['Слишком много попыток. Попробуйте через 15 минут.', 'Prea multe încercări. Reveniți peste 15 minute.'],
    ['Неверное имя или пароль.', 'Nume sau parolă greșită.'], ['Пароли не совпадают.', 'Parolele diferă.'], ['Здравствуйте, ', 'Bună ziua, '], ['Ваше имя для входа: ', 'Numele dvs. de utilizator: '],
    ['Придумайте пароль — не короче 10 знаков.', 'Alegeți o parolă de cel puțin 10 caractere.'], ['Ещё раз', 'Încă o dată'], ['Сохранить и войти', 'Salvează și intră'],
    ['Ссылка-приглашение устарела или уже использована. Попросите новую.', 'Linkul de invitație a expirat sau a fost folosit. Cereți unul nou.'], ['администратор', 'administrator'], ['редактор', 'editor'],
    ['Сайт', 'Site'], ['Выйти', 'Ieșire'], ['Сайт обновляется…', 'Site-ul se actualizează…'], ['Сайт не собрался — см. подсказку', 'Construirea site-ului a eșuat — vedeți indicația'], ['Сайт обновлён', 'Site actualizat'],
    ['Есть несохранённые изменения. Уйти без сохранения?', 'Aveți modificări nesalvate. Plecați fără a salva?'], ['Запись не найдена: ', 'Înregistrare negăsită: '], ['Выберите запись слева', 'Alegeți o înregistrare din stânga'],
    ['или создайте новую. Правки проверяются перед сохранением, попадают в журнал исправлений и в историю, сайт обновляется сам.', 'sau creați una nouă. Modificările sunt verificate înainte de salvare, intră în jurnalul de corecturi și în istoric, iar site-ul se actualizează singur.'],
    ['Разделы', 'Secțiuni'], ['Люди', 'Persoane'], ['Семьи', 'Familii'], ['Документы', 'Documente'], ['Места', 'Locuri'], ['Предложения', 'Propuneri'], ['История', 'Istoric'], ['Пользователи', 'Utilizatori'],
    ['Поиск: имя, номер, год…', 'Căutare: nume, număr, an…'], ['Поиск', 'Căutare'], ['Новая запись', 'Înregistrare nouă'], ['Список', 'Listă'], ['Ничего не нашлось.', 'Nu s-a găsit nimic.'], ['детей', 'copii'],
    ['Братья и сёстры', 'Frați și surori'], ['добавить…', 'adaugă…'], ['Открыть', 'Deschide'], ['Убрать', 'Elimină'], ['Выберите из списка', 'Alegeți din listă'],
    ['Абзацы разделяйте пустой строкой. Номера документов (S12) станут ссылками.', 'Separați paragrafele cu un rând gol. Numerele documentelor (S12) devin linkuri.'], ['По одному в строке.', 'Câte unul pe rând.'],
    ['Дата', 'Data'], ['Например: 1899, 1899-10-09, 9.10.1899, около 1899, до 1950, между 1900 и 1905.', 'De exemplu: 1899, 1899-10-09, 9.10.1899, about 1899, before 1950, between 1900 and 1905.'],
    ['Будет записано как: ', 'Va fi salvat ca: '], ['Место (как в источнике)', 'Locul (ca în sursă)'], ['Откуда известно', 'De unde se știe'], ['Место на карте', 'Locul pe hartă'], ['Примечание', 'Notă'],
    ['по документу', 'din document'], ['со слов семьи', 'din spusele familiei'], ['со слов семьи, неточно', 'din spusele familiei, nesigur'], ['вычислено по возрасту', 'calculat după vârstă'],
    ['по надгробию', 'după piatra funerară'], ['по публикации', 'dintr-o publicație'], ['вероятно', 'probabil'], ['Другие поля (JSON)', 'Alte câmpuri (JSON)'],
    ['Поля, для которых нет формы (места жительства, профили, другие версии дат…), — в формате JSON, как в family_tree.json.', 'Câmpurile fără formular (reședințe, profiluri, alte variante de date…) în format JSON, ca în family_tree.json.'],
    ['Номер будет присвоен при сохранении.', 'Numărul se atribuie la salvare.'], ['Почему изменено (попадёт в журнал исправлений)', 'De ce (intră în jurnalul de corecturi)'], ['Причина правки', 'Motivul'],
    ['Сохранить', 'Salvează'], ['Удалить', 'Șterge'], ['Удалить запись ', 'Ștergeți înregistrarea '], ['Ссылки на неё в других записях нужно убрать заранее — иначе удаление не пройдёт.', 'Eliminați mai întâi trimiterile la ea din alte înregistrări, altfel ștergerea este refuzată.'],
    ['Ваши изменения не сохранены. Скопируйте их, если нужно, и откройте свежую версию.', 'Modificările nu au fost salvate. Copiați-le dacă e nevoie și deschideți versiunea actuală.'], ['Мои изменения (JSON)', 'Modificările mele (JSON)'],
    ['Открыть свежую версию', 'Deschide versiunea actuală'], ['В поле «Другие поля (JSON)» ошибка: ', 'Eroare în „Alte câmpuri (JSON)”: '], ['Сохранено.', 'Salvat.'], ['Сайт обновится через несколько секунд.', 'Site-ul se va actualiza în câteva secunde.'],
    ['Изменений нет.', 'Nicio modificare.'], ['На каком документе основана правка', 'Documentul pe care se bazează modificarea'], ['Основание правки', 'Temeiul modificării'], ['Имя', 'Nume'], ['Имя и отчество', 'Prenume'],
    ['Фамилия', 'Nume de familie'], ['Как показывать на сайте', 'Numele afișat pe site'], ['Пусто — «Имя Фамилия».', 'Gol: „Prenume Nume”.'], ['Пол', 'Sex'], ['мужской', 'masculin'], ['женский', 'feminin'], ['неизвестно', 'necunoscut'],
    ['Кем приходится', 'Rudenia'], ['Например: прадед по маме.', 'De exemplu: străbunic pe linia mamei.'], ['Другие написания, девичья фамилия', 'Alte grafii, numele de fată'], ['Документы, по которым известен человек', 'Documentele care identifică persoana'],
    ['Рождение', 'Naștere'], ['Смерть', 'Deces'], ['Погребение', 'Înmormântare'], ['Рассказ', 'Povestea'], ['Рассказ о жизни', 'Povestea vieții'], ['Статус и приватность', 'Statut și confidențialitate'],
    ['Возможная родня: связь не доказана', 'Posibilă rudă: legătura nu este dovedită'], ['Почему связь под вопросом', 'De ce legătura e nesigură'], ['Живой человек', 'Persoană în viață'], ['определять автоматически', 'automat'],
    ['да — показывать только имя', 'da — se arată doar numele'], ['нет — показывать всё (с согласия)', 'nu — se arată tot (cu acord)'], ['Неизвестный (заглушка)', 'Persoană necunoscută'],
    ['Родители, супруги и дети задаются в семьях.', 'Părinții, soții și copiii se stabilesc în familii.'], ['Семья родителей', 'Familia părinților'], ['Новая семья (супруг, дети)', 'Familie nouă (soț/soție, copii)'],
    ['Не доказано, что это ребёнок этой пары: ', 'Nu este dovedit că e copilul acestui cuplu: '], ['Супруги (не больше двух; пусто — братья и сёстры с неизвестными родителями)', 'Parteneri (cel mult doi; gol pentru frați cu părinți necunoscuți)'],
    ['Отношения', 'Relația'], ['супруги', 'soți'], ['в разводе', 'divorțați'], ['братья и сёстры', 'frați'], ['Дети', 'Copii'], ['Приёмные дети', 'Copii adoptați'], ['Почему родство детей под вопросом', 'De ce filiația e nesigură'],
    ['Состав семьи', 'Membrii'], ['Брак', 'Căsătorie'], ['Документы и рассказ', 'Documente și poveste'], ['Документы, подтверждающие семью', 'Documente care dovedesc familia'], ['О семье', 'Despre familie'],
    ['Файла нет.', 'Niciun fișier.'], ['убрать', 'elimină'], ['Загружаю…', 'Se încarcă…'], ['Загружено. Не забудьте сохранить запись.', 'Încărcat. Nu uitați să salvați înregistrarea.'], ['Документ', 'Document'], ['Название', 'Titlu'],
    ['Что это и когда: «Метрическая книга с. Красное, 1895: рождение Ивана».', 'Ce și când: „Registrul parohiei Krasnoe, 1895: nașterea lui Ivan”.'], ['Вид', 'Tip'], ['Страница PDF для превью', 'Pagina PDF pentru miniatură'],
    ['Скрыть с сайта (семья попросила убрать)', 'Ascunde de pe site (familia a cerut)'], ['Файл (скан, фото, PDF)', 'Fișier (scanare, foto, PDF)'], ['Оборот снимка', 'Verso fotografiei'], ['Ссылка на запись в интернете', 'Link către înregistrarea online'],
    ['Где хранится (архив, фонд, опись, дело, лист)', 'Unde se păstrează (arhivă, fond, dosar, filă)'], ['Расшифровка и что доказывает', 'Transcriere și ce dovedește'], ['Где упоминается', 'Unde este menționat'],
    ['Пока ни у кого нет ссылки на этот документ.', 'Nimeni nu trimite încă la acest document.'], ['Место', 'Loc'], ['Код (латиницей, например krasnoye)', 'Cod (litere latine, de ex. krasnoye)'], ['Где это (губерния, уезд, страна)', 'Unde (regiune, țară)'],
    ['Широта', 'Latitudine'], ['Долгота', 'Longitudine'], ['Что отмечено на карте', 'Ce marchează punctul'], ['Годы, когда там жила семья', 'Anii în care familia a trăit acolo'], ['Тогда (административно)', 'Atunci (administrativ)'],
    ['Сейчас', 'Acum'], ['Год для порядка', 'An pentru sortare'], ['Другие названия (для поиска в текстах)', 'Alte denumiri (găsite în texte)'], ['Коротко для карты', 'Text scurt pentru hartă'], ['История места', 'Istoria locului'],
    ['Дата рождения', 'Data nașterii'], ['Место рождения', 'Locul nașterii'], ['Дата смерти', 'Data decesului'], ['Место смерти', 'Locul decesului'], ['Другое', 'Altceva'], ['Предложения читателей', 'Propunerile cititorilor'],
    ['Родственники предлагают исправления кнопкой «Предложить исправление» в карточке человека. Примените, откройте запись или отклоните.', 'Rudele trimit corecturi cu butonul „Propune o corectură” din fișa persoanei. Aplicați, deschideți înregistrarea sau respingeți.'],
    ['Показывать и обработанные', 'Arată și cele rezolvate'], ['Новых предложений нет.', 'Nicio propunere nouă.'], ['учтено', 'aplicat'], ['отклонено', 'respins'], ['Применить', 'Aplică'], ['Открыть запись', 'Deschide înregistrarea'],
    ['Учтено', 'Rezolvat'], ['Отклонить', 'Respinge'], ['Почему отклонено? (необязательно)', 'De ce respins? (opțional)'], ['Предложение №', 'Propunerea nr. '], ['уже было так', 'era deja așa'],
    ['откройте запись и поправьте вручную.', 'deschideți înregistrarea și corectați manual.'], ['История правок', 'Istoricul modificărilor'],
    ['Каждое сохранение — версия в git. Администратор может вернуть данные к любой версии; возврат тоже станет новой правкой.', 'Fiecare salvare este o versiune în git. Un administrator poate readuce datele la orice versiune; și aceasta devine o modificare nouă.'],
    ['git не установлен на сервере — история не ведётся.', 'git nu este instalat pe server — istoricul nu se păstrează.'], ['Вернуть эту версию', 'Restabilește această versiune'],
    ['Вернуть все данные к состоянию после этой правки? Более поздние правки отменятся (их можно будет вернуть так же).', 'Readuceți toate datele la starea de după această modificare? Modificările ulterioare se anulează (pot fi restabilite la fel).'],
    ['Когда', 'Când'], ['Кто', 'Cine'], ['Что', 'Ce'], ['Отправьте человеку эту ссылку (действует 7 дней, одноразовая). По ней он сам задаст пароль:', 'Trimiteți acest link de unică folosință (valabil 7 zile); persoana își va alege parola acolo:'],
    ['Скопировать', 'Copiază'], ['Скопировано', 'Copiat'], ['Редактор правит сведения. Администратор ещё и разбирает предложения, возвращает версии и управляет пользователями.', 'Editorul modifică datele. Administratorul se ocupă și de propuneri, versiuni și utilizatori.'],
    ['отключён', 'dezactivat'], ['ждёт приглашения', 'invitație în așteptare'], ['это вы', 'dvs.'], ['Новая ссылка', 'Link nou'], ['Сделать редактором', 'Fă editor'], ['Сделать администратором', 'Fă administrator'],
    ['Включить', 'Activează'], ['Отключить', 'Dezactivează'], ['Логин', 'Login'], ['Роль', 'Rol'], ['Новый пользователь', 'Utilizator nou'], ['Логин (латиницей)', 'Login (litere latine)'], ['Например: anna.k', 'De exemplu: anna.k'],
    ['Имя в истории правок', 'Numele în istoric'], ['Например: тётя Анна', 'De exemplu: mătușa Ana'], ['Создать и получить ссылку', 'Creează și obține linkul'], ['Смена пароля', 'Schimbarea parolei'], ['Текущий пароль', 'Parola actuală'],
    ['Новый пароль (не короче 10 знаков)', 'Parola nouă (cel puțin 10 caractere)'], ['Сменить пароль', 'Schimbă parola'], ['К списку', 'Înapoi la listă'], ['Пароль изменён. Войдите с новым паролем.', 'Parola a fost schimbată. Intrați cu parola nouă.']
  ].forEach(function (p) { DICT.ro[p[0]] = p[1]; });

  // ---------- start
  var saved = null; try { saved = localStorage.getItem('gene-editor-lang'); } catch (e) {}
  setLang(saved || (/^ro/i.test(navigator.language) ? 'ro' : /^ru/i.test(navigator.language) ? 'ru' : 'en'), true);
  $('lang').addEventListener('change', function () { setLang($('lang').value); renderHeader(); if (me) route(); else if (/^#invite=/.test(location.hash)) route(); else showLogin(); });
  if (/^#invite=/.test(location.hash)) route(); else start();
})();
