(function () {
  'use strict';

  const VIEWS = ['pick', 'browse', 'history'];
  const CHIPS = [
    { label: 'egal', min: null, max: null },
    { label: '< 15 min', min: null, max: 900 },
    { label: '15–30', min: 900, max: 1800 },
    { label: '30–60', min: 1800, max: 3600 },
    { label: '> 60', min: 3600, max: null },
  ];
  // Sort id → [item field, direction]. Header clicks flip the direction within a field.
  const SORTS = {
    added_desc: ['added_at', -1], added_asc: ['added_at', 1],
    dur_asc: ['duration', 1], dur_desc: ['duration', -1],
    pub_desc: ['published', -1], pub_asc: ['published', 1],
    title_asc: ['title', 1], title_desc: ['title', -1],
    channel_asc: ['channel', 1], channel_desc: ['channel', -1],
    skips_desc: ['skips', -1], skips_asc: ['skips', 1],
    position: ['position', 1],
  };
  const ICONS = {
    open: '<svg class="icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3H3v10h10v-3M9 3h4v4M13 3 7 9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    watched: '<svg class="icon" viewBox="0 0 16 16" aria-hidden="true"><path d="m3 8.5 3 3 7-7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    skip: '<svg class="icon" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 3 6 5-6 5M12 3v10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    remove: '<svg class="icon" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    restore: '<svg class="icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 7h7a3 3 0 0 1 0 6H6M3 7l3-3M3 7l3 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  };
  const ACTION_LABELS = {
    open: 'Auf YouTube', watched: 'Gesehen', skip: 'Überspringen', remove: 'Entfernen', restore: 'Wiederherstellen',
  };

  const state = {
    playlists: [],
    playlistId: null,
    items: [],
    enriching: 0,
    syncing: false,
    view: 'pick',
    pick: null,
    pickLoading: false,
    history: [],
    filters: { min: null, max: null, channels: [] },
    browse: { q: '', status: 'active', min: null, max: null, channels: [], skips: 'any', sort: 'added_desc' },
  };

  const $ = (sel, el) => (el || document).querySelector(sel);
  const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));

  // ---------- API ----------

  async function api(path, opts) {
    opts = opts || {};
    const init = { method: opts.method || 'GET', headers: {} };
    if (opts.body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body);
    }
    let res;
    try {
      res = await fetch('/api' + path, init);
    } catch (err) {
      toast('Hub nicht erreichbar: ' + err.message);
      throw err;
    }
    let data = null;
    const text = res.status === 204 ? '' : await res.text();
    if (text) {
      try { data = JSON.parse(text); } catch (_) { data = null; }
    }
    if (!res.ok) {
      const msg = (data && data.detail) || (res.status + ' ' + res.statusText);
      toast('Anfrage fehlgeschlagen: ' + msg);
      throw new Error(msg);
    }
    return data;
  }

  // ---------- Formatting ----------

  const rtf = new Intl.RelativeTimeFormat('de-DE', { numeric: 'auto' });
  const compactNum = new Intl.NumberFormat('de-DE', { notation: 'compact', maximumFractionDigits: 1 });
  const dateFmt = new Intl.DateTimeFormat('de-DE', { year: 'numeric', month: 'short', day: 'numeric' });

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function fmtDuration(sec) {
    if (sec == null || !isFinite(sec)) return '—';
    sec = Math.max(0, Math.round(sec));
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    const mm = h ? String(m).padStart(2, '0') : String(m);
    return (h ? h + ':' : '') + mm + ':' + String(s).padStart(2, '0');
  }

  function fmtHours(sec) {
    const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
    return h ? `${h} h ${m} min` : `${m} min`;
  }

  function fmtDate(str) {
    if (!str) return '—';
    const d = new Date(str);
    return isNaN(d) ? str : dateFmt.format(d);
  }

  function fmtRel(str) {
    if (!str) return '—';
    const d = new Date(str);
    if (isNaN(d)) return str;
    const diff = (d.getTime() - Date.now()) / 1000;
    const abs = Math.abs(diff);
    if (abs < 60) return rtf.format(Math.round(diff), 'second');
    if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute');
    if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour');
    if (abs < 86400 * 30) return rtf.format(Math.round(diff / 86400), 'day');
    if (abs < 86400 * 365) return rtf.format(Math.round(diff / (86400 * 30)), 'month');
    return rtf.format(Math.round(diff / (86400 * 365)), 'year');
  }

  function fmtCompact(n) {
    return n == null || !isFinite(n) ? '—' : compactNum.format(n);
  }

  function minutesToSec(v) {
    const n = parseFloat(v);
    return isFinite(n) && n >= 0 ? Math.round(n * 60) : null;
  }

  function secToMinutes(sec) {
    return sec == null ? '' : String(Math.round(sec / 60));
  }

  // ---------- Persistence ----------

  function storageKey() {
    return 'ytph:filters:' + state.playlistId;
  }

  function loadFilters() {
    try {
      const raw = localStorage.getItem(storageKey());
      const saved = raw ? JSON.parse(raw) : null;
      if (saved && saved.pick) Object.assign(state.filters, saved.pick);
      if (saved && saved.browse) Object.assign(state.browse, saved.browse);
    } catch (_) { /* Storage may be blocked; defaults are fine. */ }
    if (!Array.isArray(state.filters.channels)) state.filters.channels = [];
    if (!Array.isArray(state.browse.channels)) state.browse.channels = [];
    if (!SORTS[state.browse.sort]) state.browse.sort = 'added_desc';
  }

  function saveFilters() {
    try {
      const browse = Object.assign({}, state.browse, { q: '' });
      localStorage.setItem(storageKey(), JSON.stringify({ pick: state.filters, browse }));
      localStorage.setItem('ytph:playlist', String(state.playlistId));
    } catch (_) { /* ignore */ }
  }

  // ---------- Data loading ----------

  let pollTimer = null;

  async function loadState() {
    const data = await api('/state');
    state.playlists = data.playlists || [];
    state.enriching = data.enriching || 0;
    state.youtube = data.youtube || {};
    if (!state.playlists.some((p) => p.id === state.playlistId)) {
      let remembered = null;
      try { remembered = Number(localStorage.getItem('ytph:playlist')); } catch (_) { /* ignore */ }
      const found = state.playlists.find((p) => p.id === remembered) || state.playlists[0];
      state.playlistId = found ? found.id : null;
      if (found) loadFilters();
    }
    renderTopbar();
    schedulePoll();
  }

  function schedulePoll() {
    clearTimeout(pollTimer);
    if (state.enriching > 0) pollTimer = setTimeout(pollState, 3000);
  }

  async function pollState() {
    let data;
    try { data = await api('/state'); } catch (_) { return schedulePoll(); }
    const before = state.enriching;
    state.enriching = data.enriching || 0;
    state.youtube = data.youtube || state.youtube;
    state.playlists = data.playlists || state.playlists;
    renderTopbar();
    if (before > 0 && state.enriching === 0 && state.playlistId) await loadItems();
    schedulePoll();
  }

  async function loadItems() {
    if (!state.playlistId) { state.items = []; renderView(); return; }
    const items = await api('/playlists/' + state.playlistId + '/items');
    state.items = Array.isArray(items) ? items : [];
    if (state.pick) {
      const fresh = state.items.find((i) => i.id === state.pick.id);
      if (fresh) state.pick = fresh;
    }
    renderView();
  }

  async function loadHistory() {
    if (!state.playlistId) { state.history = []; return; }
    const h = await api('/playlists/' + state.playlistId + '/history?limit=100');
    state.history = Array.isArray(h) ? h : [];
    if (state.view === 'history') renderHistory();
  }

  let pickSeq = 0;

  async function loadPick(excludeId) {
    if (!state.playlistId) { state.pick = null; renderHero(); return; }
    const seq = ++pickSeq;
    state.pickLoading = true;
    renderHero();
    const params = new URLSearchParams();
    if (state.filters.min != null) params.append('min', state.filters.min);
    if (state.filters.max != null) params.append('max', state.filters.max);
    state.filters.channels.forEach((c) => params.append('channel', c));
    if (excludeId != null) params.append('exclude', excludeId);
    const qs = params.toString();
    let item = null;
    try {
      item = await api('/playlists/' + state.playlistId + '/pick' + (qs ? '?' + qs : ''));
    } catch (_) { item = null; }
    if (seq !== pickSeq) return;
    state.pickLoading = false;
    state.pick = item || null;
    renderHero();
  }

  async function selectPlaylist(id) {
    state.playlistId = id;
    state.pick = null;
    state.history = [];
    loadFilters();
    saveFilters();
    renderTopbar();
    await loadItems();
    if (state.view === 'pick') loadPick();
    if (state.view === 'history') loadHistory();
  }

  // ---------- Item actions ----------

  function replaceItem(item) {
    const idx = state.items.findIndex((i) => i.id === item.id);
    if (idx >= 0) state.items[idx] = item; else state.items.push(item);
    if (state.pick && state.pick.id === item.id) state.pick = item;
  }

  const UNDO = { watched: 'restore', remove: 'restore', skip: 'unskip' };
  const STATUS_LABELS = { watched: 'gesehen', removed: 'entfernt', gone: 'nicht verfügbar' };
  const DONE_MSG = {
    watched: 'Als gesehen markiert', skip: 'Übersprungen', remove: 'Entfernt', restore: 'Wiederhergestellt',
  };

  async function act(item, action) {
    if (!item) return;
    let updated;
    try {
      updated = await api('/items/' + item.id + '/' + action, { method: 'POST' });
    } catch (_) { return; }
    if (updated) replaceItem(updated);
    const wasPick = state.pick && state.pick.id === item.id;
    const undoAction = UNDO[action];
    let msg = DONE_MSG[action] || 'Erledigt';
    if (updated && updated.youtube_error) msg += ` (YouTube nicht aktualisiert: ${updated.youtube_error})`;
    else if (state.youtube && state.youtube.connected && (action === 'watched' || action === 'remove')) msg += ' – auch auf YouTube';
    toast(msg, undoAction ? () => undo(item.id, undoAction) : null);
    if (state.view === 'pick' && wasPick) loadPick(item.id);
    else renderView();
    if (state.view === 'history') loadHistory();
  }

  async function undo(itemId, undoAction) {
    let restored;
    try {
      restored = await api('/items/' + itemId + '/' + undoAction, { method: 'POST' });
    } catch (_) { return; }
    if (restored) replaceItem(restored);
    toast(restored && restored.youtube_error ? `Rückgängig gemacht (YouTube nicht aktualisiert: ${restored.youtube_error})` : 'Rückgängig gemacht');
    if (state.view === 'pick' && restored) {
      pickSeq++;
      state.pickLoading = false;
      state.pick = restored;
    }
    renderView();
    if (state.view === 'history') loadHistory();
  }

  // ---------- Filtering & sorting ----------

  function activeItems() {
    return state.items.filter((i) => i.status === 'active');
  }

  function matchesDuration(item, min, max) {
    if (min == null && max == null) return true;
    if (item.duration == null) return false;
    if (min != null && item.duration < min) return false;
    if (max != null && item.duration > max) return false;
    return true;
  }

  function pickMatches() {
    const f = state.filters;
    return activeItems().filter((i) =>
      matchesDuration(i, f.min, f.max) && (!f.channels.length || f.channels.includes(i.channel)));
  }

  function browseMatches() {
    const b = state.browse;
    const q = b.q.trim().toLowerCase();
    const out = state.items.filter((i) => {
      if (b.status !== 'all' && i.status !== b.status) return false;
      if (b.channels.length && !b.channels.includes(i.channel)) return false;
      if (!matchesDuration(i, b.min, b.max)) return false;
      const skips = i.skips || 0;
      if (b.skips === '0' && skips !== 0) return false;
      if (b.skips === '1' && skips < 1) return false;
      if (b.skips === '2' && skips < 2) return false;
      if (q && !((i.title || '').toLowerCase().includes(q) || (i.channel || '').toLowerCase().includes(q))) return false;
      return true;
    });
    const [field, dir] = SORTS[b.sort] || SORTS.added_desc;
    out.sort((a, c) => compare(a[field], c[field], dir) || compare(a.position, c.position, 1));
    return out;
  }

  // Nulls sort last regardless of direction.
  function compare(a, b, dir) {
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;
    if (typeof a === 'string' || typeof b === 'string') {
      return String(a).localeCompare(String(b), 'de-DE', { sensitivity: 'base', numeric: true }) * dir;
    }
    return (a - b) * dir;
  }

  function channelCounts(items) {
    const counts = new Map();
    items.forEach((i) => {
      const c = i.channel || '';
      counts.set(c, (counts.get(c) || 0) + 1);
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }

  // ---------- Rendering: topbar ----------

  function currentPlaylist() {
    return state.playlists.find((p) => p.id === state.playlistId) || null;
  }

  function renderTopbar() {
    const sel = $('#playlist-select');
    const pl = currentPlaylist();
    if (state.playlists.length > 1) {
      sel.innerHTML = '<select id="playlist-dropdown" aria-label="Playlist">' +
        state.playlists.map((p) =>
          `<option value="${p.id}"${p.id === state.playlistId ? ' selected' : ''}>${esc(p.title || p.yt_id)}</option>`).join('') +
        '</select>';
    } else if (pl) {
      sel.innerHTML = `<span class="playlist-title">${esc(pl.title || pl.yt_id)}</span>`;
    } else {
      sel.innerHTML = '<span class="playlist-title muted">Noch keine Playlist</span>';
    }
    const syncBtn = $('#sync-btn');
    syncBtn.disabled = !pl || state.syncing;
    syncBtn.classList.toggle('busy', state.syncing);
    $('#sync-time').textContent = state.syncing ? 'synchronisiere …' : (pl && pl.last_synced ? fmtRel(pl.last_synced) : '');
    $('#delete-playlist').hidden = !pl;
    const note = $('#enrich-note');
    note.hidden = !(state.enriching > 0);
    note.textContent = state.enriching > 0 ? `Datensammlung … noch ${state.enriching}` : '';
    const yt = $('#yt-note');
    yt.hidden = !pl || !!(state.youtube && state.youtube.connected);
    yt.textContent = yt.hidden ? '' : 'YouTube nicht verbunden: Status wird nur lokal gespeichert. `./hub.py auth`, siehe README.';
  }

  // ---------- Rendering: shared controls ----------

  function chipsHtml(min, max) {
    return CHIPS.map((c) =>
      `<button type="button" class="chip${c.min === min && c.max === max ? ' on' : ''}" data-min="${c.min == null ? '' : c.min}" data-max="${c.max == null ? '' : c.max}">${c.label}</button>`).join('');
  }

  function renderRange(name, f) {
    $(`[data-chips="${name}"]`).innerHTML = chipsHtml(f.min, f.max);
    const minEl = $(`[data-range="${name}-min"]`), maxEl = $(`[data-range="${name}-max"]`);
    if (document.activeElement !== minEl) minEl.value = secToMinutes(f.min);
    if (document.activeElement !== maxEl) maxEl.value = secToMinutes(f.max);
  }

  function renderPicker(name, selected, counts) {
    const host = $(`[data-picker="${name}"]`);
    const wasOpen = host.firstElementChild && host.firstElementChild.open;
    const n = selected.length;
    const label = n ? `${n} ${n === 1 ? 'Kanal' : 'Kanäle'}` : 'Alle Kanäle';
    host.innerHTML =
      `<details class="popover picker"${wasOpen ? ' open' : ''}>` +
      `<summary class="btn${n ? ' active' : ''}">${label}</summary>` +
      '<div class="popover-menu picker-menu">' +
      (counts.length ? '' : '<p class="muted">Keine Kanäle</p>') +
      counts.map(([c, cnt]) =>
        `<label class="check"><input type="checkbox" value="${esc(c)}"${selected.includes(c) ? ' checked' : ''}> <span>${esc(c) || '<em>unbekannt</em>'}</span><small>${cnt}</small></label>`).join('') +
      `<button type="button" class="btn small ghost" data-picker-clear${n ? '' : ' hidden'}>Zurücksetzen</button>` +
      '</div></details>';
  }

  function updatePickerSummary(name, selected) {
    const summary = $(`[data-picker="${name}"] summary`);
    if (!summary) return;
    const n = selected.length;
    summary.textContent = n ? `${n} ${n === 1 ? 'Kanal' : 'Kanäle'}` : 'Alle Kanäle';
    summary.classList.toggle('active', n > 0);
    const clear = $(`[data-picker="${name}"] [data-picker-clear]`);
    if (clear) clear.hidden = n === 0;
  }

  function actionButtons(item, opts) {
    const iconOnly = opts && opts.iconOnly;
    const btn = (action, cls) => {
      const label = ACTION_LABELS[action];
      const inner = ICONS[action] + (iconOnly ? '' : `<span>${label}</span>`);
      if (action === 'open') {
        return `<a class="btn ${cls}" href="${esc(item.url)}" target="_blank" rel="noopener"${iconOnly ? ` aria-label="${label}" title="${label}"` : ''}>${inner}</a>`;
      }
      return `<button type="button" class="btn ${cls}" data-action="${action}" data-id="${item.id}"${iconOnly ? ` aria-label="${label}" title="${label}"` : ''}>${inner}</button>`;
    };
    if (item.status === 'active') {
      return btn('open', 'primary') + btn('watched', '') + btn('skip', '') + btn('remove', 'danger ghost');
    }
    return btn('open', 'primary') + btn('restore', '');
  }

  // ---------- Rendering: views ----------

  function renderView() {
    VIEWS.forEach((v) => { $('#view-' + v).hidden = v !== state.view; });
    $$('.tabs a').forEach((a) => {
      if (a.dataset.tab === state.view) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    if (state.view === 'pick') renderPick();
    else if (state.view === 'browse') renderBrowse();
    else renderHistory();
  }

  function renderPick() {
    renderRange('pick', state.filters);
    renderPicker('pick', state.filters.channels, channelCounts(activeItems()));
    renderPickStats();
    renderHero();
  }

  function renderPickStats() {
    const active = activeItems();
    const total = active.reduce((s, i) => s + (i.duration || 0), 0);
    $('#pick-stats').textContent = state.playlistId
      ? `${active.length} Videos · ${pickMatches().length} gefiltert · ${fmtHours(total)}`
      : '';
  }

  function renderHero() {
    const host = $('#pick-hero');
    if (!state.playlistId) {
      host.innerHTML = '<div class="card empty"><p>Oben eine Playlist hinzufügen, um loszulegen.</p></div>';
      return;
    }
    if (state.pickLoading && !state.pick) {
      host.innerHTML = '<div class="card empty"><p class="muted">Suche etwas aus …</p></div>';
      return;
    }
    const it = state.pick;
    if (!it) {
      host.innerHTML = '<div class="card empty"><p>Nix da.</p><p class="muted">Entferne ein paar Filter oder synchronisiere die Playliste.</p></div>';
      return;
    }
    const meta = [
      it.channel ? `<a href="${esc(it.channel_url || '#')}" target="_blank" rel="noopener">${esc(it.channel)}</a>` : null,
      it.duration != null ? esc(fmtDuration(it.duration)) : null,
      it.published ? `veröffentlicht ${esc(fmtDate(it.published))}` : null,
      it.view_count != null ? `${esc(fmtCompact(it.view_count))} Aufrufe` : null,
    ].filter(Boolean).join(' · ');
    const sub = [
      it.added_at ? `hinzugefügt ${esc(fmtRel(it.added_at))}` : null,
      it.skips > 0 ? `${it.skips}× übersprungen` : null,
      it.available === false ? 'auf YouTube nicht verfügbar' : null,
    ].filter(Boolean).join(' · ');
    host.innerHTML =
      `<article class="card hero${state.pickLoading ? ' loading' : ''}" data-id="${it.id}">` +
      `<a class="thumb hero-thumb" href="${esc(it.url)}" target="_blank" rel="noopener" tabindex="-1">` +
      (it.thumbnail_large || it.thumbnail ? `<img src="${esc(it.thumbnail_large || it.thumbnail)}" alt="" loading="lazy">` : '') +
      (it.duration != null ? `<span class="badge">${esc(fmtDuration(it.duration))}</span>` : '') +
      '</a>' +
      '<div class="hero-body">' +
      `<h2><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a></h2>` +
      `<p class="meta">${meta}</p>` +
      (sub ? `<p class="meta muted">${sub}</p>` : '') +
      `<div class="actions">${actionButtons(it)}` +
      '<button type="button" class="btn ghost" data-action="repick">Neuer Vorschlag</button>' +
      '</div></div></article>';
  }

  function renderBrowse() {
    const b = state.browse;
    const q = $('#browse-q');
    if (document.activeElement !== q) q.value = b.q;
    $('#browse-status').value = b.status;
    $('#browse-skips').value = b.skips;
    $('#browse-sort').value = b.sort;
    renderRange('browse', b);
    const pool = b.status === 'all' ? state.items : state.items.filter((i) => i.status === b.status);
    renderPicker('browse', b.channels, channelCounts(pool));
    renderBrowseList();
  }

  function renderBrowseList() {
    const items = browseMatches();
    const total = items.reduce((s, i) => s + (i.duration || 0), 0);
    $('#browse-count').textContent = `${items.length} Treffer · ${fmtHours(total)}`;
    const host = $('#browse-list');
    if (!state.playlistId) {
      host.innerHTML = '<div class="empty"><p>Oben eine Playlist hinzufügen, um loszulegen.</p></div>';
      return;
    }
    if (!items.length) {
      host.innerHTML = '<div class="empty"><p>Keine Treffer.</p></div>';
      return;
    }
    const [sortField, sortDir] = SORTS[state.browse.sort] || SORTS.added_desc;
    const th = (field, label, cls) => {
      const on = field === sortField;
      return `<th class="${cls || ''}"><button type="button" class="th-sort${on ? ' on' : ''}" data-sort="${field}">${label}${on ? `<span class="arrow">${sortDir > 0 ? '▲' : '▼'}</span>` : ''}</button></th>`;
    };
    host.innerHTML =
      '<table class="items"><thead><tr>' +
      '<th class="c-thumb"></th>' +
      th('title', 'Titel', 'c-title') +
      th('channel', 'Kanal', 'c-channel') +
      th('duration', 'Länge', 'c-num') +
      th('published', 'Veröffentlicht', 'c-date') +
      th('added_at', 'Hinzugefügt', 'c-date') +
      th('skips', 'Übersprungen', 'c-num') +
      '<th class="c-num"><span class="th-sort">Aufrufe</span></th>' +
      '<th class="c-actions"></th>' +
      '</tr></thead><tbody>' +
      items.map(rowHtml).join('') +
      '</tbody></table>';
  }

  function rowHtml(it) {
    const status = it.status !== 'active' ? `<span class="tag tag-${esc(it.status)}">${esc(STATUS_LABELS[it.status] || it.status)}</span>` : '';
    const subParts = [
      it.channel ? esc(it.channel) : null,
      it.published ? esc(fmtDate(it.published)) : null,
      it.view_count != null ? `${esc(fmtCompact(it.view_count))} Aufrufe` : null,
      it.skips > 0 ? `${it.skips}× übersprungen` : null,
    ].filter(Boolean).join(' · ');
    return `<tr data-id="${it.id}" class="status-${esc(it.status)}">` +
      `<td class="c-thumb"><a class="thumb" href="${esc(it.url)}" target="_blank" rel="noopener" tabindex="-1">` +
      (it.thumbnail ? `<img src="${esc(it.thumbnail)}" alt="" loading="lazy">` : '') +
      (it.duration != null ? `<span class="badge">${esc(fmtDuration(it.duration))}</span>` : '') +
      '</a></td>' +
      `<td class="c-title"><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a> ${status}<div class="sub">${subParts}</div></td>` +
      `<td class="c-channel">${it.channel ? `<a href="${esc(it.channel_url || '#')}" target="_blank" rel="noopener">${esc(it.channel)}</a>` : '—'}</td>` +
      `<td class="c-num">${esc(fmtDuration(it.duration))}</td>` +
      `<td class="c-date">${esc(fmtDate(it.published))}</td>` +
      `<td class="c-date" title="${esc(fmtDate(it.added_at))}">${esc(fmtRel(it.added_at))}</td>` +
      `<td class="c-num">${it.skips || 0}</td>` +
      `<td class="c-num">${esc(fmtCompact(it.view_count))}</td>` +
      `<td class="c-actions"><div class="row-actions">${actionButtons(it, { iconOnly: true })}</div></td>` +
      '</tr>';
  }

  const HISTORY_LABELS = {
    skip: 'übersprungen', unskip: 'doch nicht übersprungen', watched: 'gesehen', remove: 'entfernt',
    restore: 'wiederhergestellt', added: 'hinzugefügt', gone: 'aus Playlist verschwunden',
  };

  function renderHistory() {
    const host = $('#history-list');
    if (!state.playlistId) {
      host.innerHTML = '<div class="empty"><p>Oben eine Playlist hinzufügen, um loszulegen.</p></div>';
      return;
    }
    if (!state.history.length) {
      host.innerHTML = '<div class="empty"><p class="muted">Noch nichts passiert.</p></div>';
      return;
    }
    host.innerHTML = '<ul class="history">' + state.history.map((h) => {
      const it = h.item || {};
      const restorable = ['watched', 'remove', 'gone'].includes(h.action) && it.status && it.status !== 'active';
      return `<li data-id="${esc(it.id)}">` +
        `<span class="tag tag-${esc(h.action)}">${HISTORY_LABELS[h.action] || esc(h.action)}</span>` +
        `<a class="history-title" href="${esc(it.url || '#')}" target="_blank" rel="noopener">${esc(it.title || '(unbekanntes Video)')}</a>` +
        `<time datetime="${esc(h.at)}" title="${esc(h.at)}">${esc(fmtRel(h.at))}</time>` +
        (restorable && it.id != null ? `<button type="button" class="btn small" data-action="restore" data-id="${it.id}">${ICONS.restore}<span>Wiederherstellen</span></button>` : '') +
        '</li>';
    }).join('') + '</ul>';
  }

  // ---------- Toast ----------

  let toastTimer = null;
  let toastUndo = null;

  function toast(msg, undoFn) {
    const el = $('#toast');
    toastUndo = undoFn || null;
    el.innerHTML = `<span>${esc(msg)}</span>` +
      (undoFn ? '<button type="button" class="btn small primary" data-toast-undo>Rückgängig</button>' : '') +
      '<button type="button" class="toast-close" data-toast-close aria-label="Schließen">×</button>';
    el.hidden = false;
    clearTimeout(toastTimer);
    if (!undoFn) toastTimer = setTimeout(hideToast, 4000);
  }

  function hideToast() {
    clearTimeout(toastTimer);
    $('#toast').hidden = true;
    toastUndo = null;
  }

  // ---------- Routing ----------

  function readHash() {
    const v = location.hash.replace('#', '');
    state.view = VIEWS.includes(v) ? v : 'pick';
  }

  function onHashChange() {
    readHash();
    renderView();
    if (state.view === 'pick' && !state.pick && !state.pickLoading) loadPick();
    if (state.view === 'history') loadHistory();
  }

  // ---------- Events ----------

  function itemFromEl(el) {
    const id = Number(el.dataset.id);
    return state.items.find((i) => i.id === id) || (state.pick && state.pick.id === id ? state.pick : null);
  }

  function setRange(name, f, min, max) {
    f.min = min;
    f.max = max;
    saveFilters();
    renderRange(name, f);
  }

  function afterPickFilterChange() {
    renderPickStats();
    loadPick(state.pick ? state.pick.id : null);
  }

  function bindEvents() {
    window.addEventListener('hashchange', onHashChange);

    document.addEventListener('click', (e) => {
      const t = e.target.closest('[data-action], [data-min], [data-sort], [data-picker-clear], [data-toast-undo], [data-toast-close]');
      if (!t) {
        $$('details.popover[open]').forEach((d) => { if (!d.contains(e.target)) d.open = false; });
        return;
      }
      if (t.dataset.action === 'repick') { loadPick(state.pick ? state.pick.id : null); return; }
      if (t.dataset.action) {
        const item = itemFromEl(t);
        if (item) act(item, t.dataset.action);
        return;
      }
      if (t.dataset.min !== undefined) {
        const min = t.dataset.min === '' ? null : Number(t.dataset.min);
        const max = t.dataset.max === '' ? null : Number(t.dataset.max);
        const name = t.closest('[data-chips]').dataset.chips;
        if (name === 'pick') { setRange('pick', state.filters, min, max); afterPickFilterChange(); }
        else { setRange('browse', state.browse, min, max); renderBrowseList(); }
        return;
      }
      if (t.dataset.sort) {
        const field = t.dataset.sort;
        const [curField, curDir] = SORTS[state.browse.sort] || SORTS.added_desc;
        const ids = Object.keys(SORTS).filter((k) => SORTS[k][0] === field);
        const next = curField === field ? ids.find((k) => SORTS[k][1] === -curDir) : ids[0];
        if (next) { state.browse.sort = next; saveFilters(); $('#browse-sort').value = next; renderBrowseList(); }
        return;
      }
      if (t.hasAttribute('data-picker-clear')) {
        const name = t.closest('[data-picker]').dataset.picker;
        if (name === 'pick') { state.filters.channels = []; saveFilters(); renderPicker('pick', [], channelCounts(activeItems())); afterPickFilterChange(); }
        else { state.browse.channels = []; saveFilters(); renderBrowse(); }
        return;
      }
      if (t.hasAttribute('data-toast-undo')) {
        const fn = toastUndo;
        hideToast();
        if (fn) fn();
        return;
      }
      if (t.hasAttribute('data-toast-close')) hideToast();
    });

    document.addEventListener('change', (e) => {
      const t = e.target;
      const picker = t.closest('[data-picker]');
      if (picker && t.type === 'checkbox') {
        const name = picker.dataset.picker;
        const list = name === 'pick' ? state.filters.channels : state.browse.channels;
        const idx = list.indexOf(t.value);
        if (t.checked && idx < 0) list.push(t.value);
        if (!t.checked && idx >= 0) list.splice(idx, 1);
        saveFilters();
        updatePickerSummary(name, list);
        if (name === 'pick') afterPickFilterChange(); else renderBrowseList();
        return;
      }
      if (t.dataset.range) {
        const [name, which] = t.dataset.range.split('-');
        const f = name === 'pick' ? state.filters : state.browse;
        f[which] = minutesToSec(t.value);
        if (f.min != null && f.max != null && f.max < f.min) f[which === 'min' ? 'max' : 'min'] = null;
        saveFilters();
        renderRange(name, f);
        if (name === 'pick') afterPickFilterChange(); else renderBrowseList();
        return;
      }
      if (t.id === 'playlist-dropdown') { selectPlaylist(Number(t.value)); return; }
      if (t.id === 'browse-status') { state.browse.status = t.value; saveFilters(); renderBrowse(); return; }
      if (t.id === 'browse-skips') { state.browse.skips = t.value; saveFilters(); renderBrowseList(); return; }
      if (t.id === 'browse-sort') { state.browse.sort = t.value; saveFilters(); renderBrowseList(); }
    });

    $('#browse-q').addEventListener('input', (e) => {
      state.browse.q = e.target.value;
      saveFilters();
      renderBrowseList();
    });

    $('#sync-btn').addEventListener('click', syncPlaylist);
    $('#add-form').addEventListener('submit', addPlaylist);
    $('#delete-playlist').addEventListener('click', deletePlaylist);

    document.addEventListener('keydown', (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const tag = (e.target.tagName || '').toLowerCase();
      if (['input', 'select', 'textarea'].includes(tag) || e.target.isContentEditable) return;
      if (e.key === 'Escape') { hideToast(); $$('details.popover[open]').forEach((d) => { d.open = false; }); return; }
      if (state.view !== 'pick') return;
      const it = state.pick;
      if (e.key === 'r') { e.preventDefault(); loadPick(it ? it.id : null); return; }
      if (!it) return;
      if (e.key === 'o') { e.preventDefault(); window.open(it.url, '_blank', 'noopener'); }
      else if (e.key === 'w') { e.preventDefault(); act(it, 'watched'); }
      else if (e.key === 's') { e.preventDefault(); act(it, 'skip'); }
    });
  }

  // ---------- Playlist management ----------

  async function syncPlaylist() {
    if (!state.playlistId || state.syncing) return;
    state.syncing = true;
    renderTopbar();
    try {
      const r = await api('/playlists/' + state.playlistId + '/sync', { method: 'POST' });
      if (r && r.playlist) {
        const idx = state.playlists.findIndex((p) => p.id === r.playlist.id);
        if (idx >= 0) state.playlists[idx] = r.playlist;
      }
      toast(`Synchronisiert: ${r ? r.added : 0} neu, ${r ? r.gone : 0} verschwunden, ${r ? r.total : '?'} gesamt`);
      await loadState();
      await loadItems();
      if (state.view === 'pick' && !state.pick) loadPick();
    } catch (_) { /* toast already shown */ }
    state.syncing = false;
    renderTopbar();
  }

  async function addPlaylist(e) {
    e.preventDefault();
    const input = $('#add-url');
    const url = input.value.trim();
    if (!url) return;
    const btn = $('#add-form button[type=submit]');
    btn.disabled = true;
    btn.textContent = 'Rödel rödel …';
    try {
      const pl = await api('/playlists', { method: 'POST', body: { url } });
      input.value = '';
      $('#manage').open = false;
      await loadState();
      if (pl && pl.id != null) await selectPlaylist(pl.id);
      toast(`„${pl && pl.title ? pl.title : url}“ hinzugefügt`);
    } catch (_) { /* toast already shown */ }
    btn.disabled = false;
    btn.textContent = 'Hinzufügen und synchronisieren';
  }

  async function deletePlaylist() {
    const pl = currentPlaylist();
    if (!pl) return;
    if (!window.confirm(`„${pl.title || pl.yt_id}“ und alles, was der Hub darüber weiß, entfernen?`)) return;
    try {
      await api('/playlists/' + pl.id, { method: 'DELETE' });
    } catch (_) { return; }
    $('#manage').open = false;
    state.playlistId = null;
    state.pick = null;
    state.items = [];
    state.history = [];
    await loadState();
    await loadItems();
    if (state.view === 'pick') loadPick();
    if (state.view === 'history') loadHistory();
  }

  // ---------- Boot ----------

  async function init() {
    bindEvents();
    readHash();
    renderView();
    try {
      await loadState();
      await loadItems();
    } catch (_) { renderView(); return; }
    if (state.view === 'pick') loadPick();
    if (state.view === 'history') loadHistory();
  }

  init();
})();
