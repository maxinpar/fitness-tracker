/* Gym mode. One exercise open at a time, big targets, no session-wide form.
 *
 * The server renders the week's plan plus the rest of the catalogue into
 * #catalogue; everything below is presentation state. Nothing is written to
 * Postgres until SAVE SESSION, which posts reps_<id>_<n> / kg_<id>_<n> — the
 * same field names the original form used, so app.py needed no change.
 *
 * Progress survives a reload via localStorage, keyed by date: the phone screen
 * locks between sets and a dropped session is worse than a stale one. */
(function () {
  'use strict';

  var CAT = JSON.parse(document.getElementById('catalogue').textContent);
  var byId = {};
  CAT.forEach(function (c) { byId[c.id] = c; });

  var PLANNED = CAT.filter(function (c) { return c.planned; }).map(function (c) { return c.id; });
  var KEY = 'ft-session-' + document.querySelector('input[name=date]').value;

  var state = load() || fresh();

  function fresh() {
    return { order: PLANNED.slice(), sets: freshSets(PLANNED), done: [], activeId: PLANNED[0] || '', notes: '' };
  }
  function freshSets(ids) {
    var out = {};
    ids.forEach(function (id) {
      var e = byId[id];
      out[id] = [];
      for (var i = 0; i < e.sets; i++) out[id].push({ reps: e.reps, kg: e.kg });
    });
    return out;
  }
  function load() {
    try {
      var raw = JSON.parse(localStorage.getItem(KEY));
      // Drop anything referring to an exercise the plan no longer offers.
      if (!raw || !raw.order || !raw.order.every(function (id) { return byId[id]; })) return null;
      return raw;
    } catch (e) { return null; }
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  }

  var f1 = function (n) { return (Math.round(n * 10) / 10).toFixed(1); };

  function estMinutes() {
    var m = state.order.reduce(function (acc, id) {
      return acc + byId[id].perSet * ((state.sets[id] || []).length || 1);
    }, 0);
    return Math.round(m);
  }

  // ── rendering ────────────────────────────────────────────────────────────
  var el = {
    active: document.getElementById('active'),
    photo: document.getElementById('active-photo'),
    name: document.getElementById('active-name'),
    meta: document.getElementById('active-meta'),
    rows: document.getElementById('set-rows'),
    doneBtn: document.getElementById('mark-done'),
    tiles: document.getElementById('tiles'),
    pool: document.getElementById('pool'),
    poolWrap: document.getElementById('pool-wrap'),
    est: document.getElementById('est'),
    doneCount: document.getElementById('done-count'),
    exCount: document.getElementById('ex-count'),
    notes: document.getElementById('notes'),
  };

  function setPhoto(node, ex, size) {
    if (ex.photo) {
      node.style.background = '';
      node.classList.remove('stripe');
      node.style.backgroundImage = 'url("/static/exercises/' + ex.photo + '")';
      node.style.backgroundSize = 'cover';
      node.style.backgroundPosition = 'center';
      node.textContent = '';
    } else {
      node.classList.add('stripe');
      node.style.backgroundImage = '';
      if (size === 'tile') node.textContent = 'photo';
    }
  }

  function renderActive() {
    var id = state.activeId;
    if (!id || state.order.indexOf(id) === -1) { el.active.hidden = true; return; }
    var e = byId[id];
    el.active.hidden = false;
    el.name.textContent = e.name;
    var n = (state.sets[id] || []).length;
    // The warm-up row is timed, not loaded, so neither "ref" nor "bodyweight" applies.
    var load = e.category === 'warmup' ? '' : (e.ref ? ' · ref ' + f1(e.ref) + ' kg' : ' · bodyweight');
    el.meta.textContent = n + (n === 1 ? ' set' : ' sets') + ' · plan ' + e.reps + ' ' + e.repUnit + load;

    // Keep the corner marks; only the photo fill changes.
    setPhoto(el.photo, e, 'active');

    el.rows.textContent = '';
    (state.sets[id] || []).forEach(function (row, i) {
      el.rows.appendChild(setRow(e, row, i));
    });
    el.doneBtn.textContent = state.done.indexOf(id) > -1 ? 'Logged ✓' : 'Done · next';
  }

  function stepper(value, unit, onMinus, onPlus) {
    var box = document.createElement('div');
    box.className = 'stepper';
    var minus = document.createElement('button');
    minus.type = 'button'; minus.className = 'btn minus'; minus.textContent = '−';
    minus.setAttribute('aria-label', 'decrease ' + unit);
    minus.addEventListener('click', onMinus);
    var val = document.createElement('div');
    val.className = 'val mono';
    val.appendChild(document.createTextNode(value));
    var u = document.createElement('small');
    u.className = 'text-muted'; u.textContent = unit;
    val.appendChild(u);
    var plus = document.createElement('button');
    plus.type = 'button'; plus.className = 'btn plus'; plus.textContent = '+';
    plus.setAttribute('aria-label', 'increase ' + unit);
    plus.addEventListener('click', onPlus);
    box.appendChild(minus); box.appendChild(val); box.appendChild(plus);
    return box;
  }

  function setRow(e, row, i) {
    var wrap = document.createElement('div');
    wrap.className = 'setrow';

    var label = document.createElement('span');
    label.className = 'slabel mono';
    label.textContent = 'S' + (i + 1);
    wrap.appendChild(label);

    wrap.appendChild(stepper(row.reps, e.repUnit,
      function () { bump(e.id, i, 'reps', -1); },
      function () { bump(e.id, i, 'reps', 1); }));

    wrap.appendChild(stepper(f1(row.kg), e.kgUnit,
      function () { bump(e.id, i, 'kg', -1); },
      function () { bump(e.id, i, 'kg', 1); }));

    var drop = document.createElement('button');
    drop.type = 'button'; drop.className = 'btn btn-ghost drop'; drop.textContent = '−';
    drop.title = 'Remove this set';
    // The last set cannot be removed — an exercise with no sets is not a log.
    drop.disabled = (state.sets[e.id] || []).length < 2;
    drop.addEventListener('click', function () {
      if ((state.sets[e.id] || []).length < 2) return;
      state.sets[e.id].splice(i, 1);
      commit();
    });
    wrap.appendChild(drop);
    return wrap;
  }

  function bump(id, i, field, dir) {
    var e = byId[id];
    var step = field === 'reps' ? e.repStep : e.kgStep;
    var next = state.sets[id][i][field] + dir * step;
    state.sets[id][i][field] = Math.max(0, Math.round(next * 10) / 10);
    commit();
  }

  function renderTiles() {
    el.tiles.textContent = '';
    state.order.forEach(function (id) {
      var e = byId[id];
      var rows = state.sets[id] || [];
      var isDone = state.done.indexOf(id) > -1;

      var wrap = document.createElement('div');
      wrap.className = 'tile' + (id === state.activeId ? ' open' : '');

      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary';
      btn.addEventListener('click', function () { state.activeId = id; commit(); });

      var ph = document.createElement('span');
      ph.className = 'tile-photo';
      setPhoto(ph, e, 'tile');
      btn.appendChild(ph);

      var text = document.createElement('span');
      text.className = 'tile-text';
      var nm = document.createElement('span');
      nm.className = 'tile-name'; nm.textContent = e.name;
      var meta = document.createElement('span');
      meta.className = 'tile-meta text-muted mono';
      meta.textContent = rows.length + ' × ' + (rows[0] ? rows[0].reps : e.reps) + ' ' + e.repUnit +
        ' · ' + f1(rows[0] ? rows[0].kg : e.kg) + ' ' + e.kgUnit;
      text.appendChild(nm); text.appendChild(meta);
      btn.appendChild(text);

      var tag = document.createElement('span');
      tag.className = 'tag ' + (isDone ? 'tag-accent' : 'tag-neutral');
      tag.textContent = isDone ? 'logged' : (id === state.activeId ? 'open' : 'to do');
      btn.appendChild(tag);

      wrap.appendChild(btn);
      el.tiles.appendChild(wrap);
    });
  }

  function renderPool() {
    el.pool.textContent = '';
    var rest = CAT.filter(function (c) { return state.order.indexOf(c.id) === -1; });
    el.poolWrap.hidden = rest.length === 0;
    rest.forEach(function (c) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-secondary';
      b.textContent = '+ ' + c.name;
      b.addEventListener('click', function () {
        state.order.push(c.id);
        state.sets[c.id] = freshSets([c.id])[c.id];
        state.activeId = c.id;
        commit();
        window.flash(c.name + ' added — estimate now ~' + estMinutes() + ' min.');
      });
      el.pool.appendChild(b);
    });
  }

  function commit() {
    save();
    render();
  }

  function render() {
    renderActive();
    renderTiles();
    renderPool();
    el.est.innerHTML = '~' + estMinutes() + '&nbsp;MIN';
    el.doneCount.textContent = state.done.length;
    el.exCount.textContent = state.order.length;
  }

  // ── actions ──────────────────────────────────────────────────────────────
  document.getElementById('close-active').addEventListener('click', function () {
    state.activeId = ''; commit();
  });

  document.getElementById('add-set').addEventListener('click', function () {
    var id = state.activeId;
    if (!id) return;
    var rows = state.sets[id];
    rows.push({ reps: rows[rows.length - 1].reps, kg: rows[rows.length - 1].kg });
    commit();
    window.flash('Set added — estimate now ~' + estMinutes() + ' min.');
  });

  el.doneBtn.addEventListener('click', function () {
    var id = state.activeId;
    if (!id) return;
    if (state.done.indexOf(id) === -1) state.done.push(id);
    var next = state.order.find(function (x) { return state.done.indexOf(x) === -1; }) || '';
    state.activeId = next;
    commit();
  });

  document.getElementById('reset').addEventListener('click', function () {
    state = fresh();
    el.notes.value = '';
    commit();
    window.flash('Back to the week plan.');
  });

  el.notes.addEventListener('input', function () { state.notes = el.notes.value; save(); });

  // ── save ─────────────────────────────────────────────────────────────────
  document.getElementById('session-form').addEventListener('submit', function (ev) {
    var payload = document.getElementById('payload');
    payload.textContent = '';
    var any = false;
    state.order.forEach(function (id) {
      (state.sets[id] || []).forEach(function (row, i) {
        if (!row.reps) return;               // a blank set is a skipped set
        any = true;
        payload.appendChild(hidden('reps_' + id + '_' + (i + 1), row.reps));
        payload.appendChild(hidden('kg_' + id + '_' + (i + 1), byId[id].ref === null && !row.kg ? '' : row.kg));
      });
    });
    if (!any) {
      ev.preventDefault();
      window.flash('Nothing to save — log at least one set.');
      return;
    }
    try { localStorage.removeItem(KEY); } catch (e) {}
  });

  function hidden(name, value) {
    var i = document.createElement('input');
    i.type = 'hidden'; i.name = name; i.value = value;
    return i;
  }

  el.notes.value = state.notes || '';
  render();
})();
