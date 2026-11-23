/* app.js — 부팅 · 라우터 · 명령 팔레트 · 단축키 · 테마 · 프로젝트 동작 */
'use strict';
(function (RT) {
  const { $, $$, esc, fmt, icon, backend, bus, toast, modal } = RT;
  const PAGES = ['home', 'observe', 'sky', 'galaxy', 'log', 'settings', 'about'];
  const NAMES = { home: '홈', observe: '관측', sky: '하늘 지도', galaxy: '은하 지도', log: '관측 기록', settings: '설정', about: '정보' };
  const titles = new Map();
  const inited = new Set();
  RT.current = null;

  // ─────────── 상태 ───────────
  async function refresh() {
    try { RT.state = await backend.call('state'); } catch (e) { toast(e.message, 'err'); return; }
    renderChrome();
    for (const k of PAGES) RT.pages[k]?.onState && inited.has(k) && RT.pages[k].onState();
  }
  RT.refresh = refresh;

  function renderChrome() {
    const p = RT.state.project;
    $('#project-chip-name').textContent = p ? p.name : '프로젝트 없음';
    $('#project-chip .dot').className = 'dot' + (p ? ' live' : '');
    $('#brand-ver').textContent = 'v' + (RT.state.app?.version || '2').split('.').slice(0, 2).join('.');
    $('#side-project').innerHTML = p
      ? `<div class="sp-card" data-go="home"><div class="sp-avatar">${esc(p.name.slice(0, 2).toUpperCase())}</div><div class="sp-text"><div class="sp-name">${esc(p.name)}</div><div class="sp-meta">관측 ${p.obs_count} · 피크 ${p.peak_count}</div></div></div>`
      : `<div class="sp-card" data-act="new"><div class="sp-avatar off">${icon('plus')}</div><div class="sp-text"><div class="sp-name">프로젝트 없음</div><div class="sp-meta">눌러서 새로 만들기</div></div></div>`;
    backend.call('window_title', { title: p ? `${p.name} — HI 21cm 전파망원경` : 'HI 21cm 전파망원경' }).catch(() => { });
  }

  // ─────────── 라우터 ───────────
  function placeIndicator(animate = true) {
    const a = $(`.nav-item[data-page="${RT.current}"]`), ind = $('#nav-indicator');
    if (!a) return;
    if (!animate) ind.style.transition = 'none';
    ind.style.transform = `translateY(${a.offsetTop}px)`; ind.style.opacity = 1;
    if (!animate) { ind.offsetHeight; ind.style.transition = ''; }
  }
  async function go(page) {
    if (!PAGES.includes(page) || page === RT.current) return;
    const prev = RT.current, prevEl = prev && $(`.page[data-page="${prev}"]`), el = $(`.page[data-page="${page}"]`);
    if (prev && RT.pages[prev]?.leave) RT.pages[prev].leave();
    RT.tip.hide();
    if (prevEl) {
      prevEl.classList.add('leave');
      setTimeout(() => prevEl.classList.remove('active', 'leave', 'enter'), 170);
    }
    RT.current = page;
    $$('.nav-item').forEach((n) => n.classList.toggle('active', n.dataset.page === page));
    placeIndicator();
    $('#crumb-page').textContent = NAMES[page];
    el.classList.add('active', 'enter');
    el.scrollTop = 0;
    $$(':scope > .wrap > *', el).forEach((n, i) => n.style.setProperty('--i', i));
    setTimeout(() => el.classList.remove('enter'), 1100);
    const ctl = RT.pages[page];
    if (ctl && !inited.has(page)) { inited.add(page); ctl.init && ctl.init(); }
    const h1 = $('.pixel-title', el);
    if (h1) { if (!titles.has(h1)) titles.set(h1, new RT.PixelTitle(h1)); setTimeout(() => titles.get(h1).enter(), 60); }
    if (ctl && ctl.enter) { try { await ctl.enter(); } catch (e) { console.error(e); } }
    RT.saveUI('page', page);
  }
  RT.go = go;

  // ─────────── UI 상태 저장 (config.ui, 몰아서) ───────────
  let uiPending = {}, uiTimer = 0;
  RT.saveUI = (key, val) => {
    uiPending[key] = val;
    clearTimeout(uiTimer);
    uiTimer = setTimeout(() => {
      const ui = uiPending; uiPending = {};
      backend.call('config_update', { ui }).then((c) => { if (RT.state) RT.state.config = c; }).catch(() => { });
    }, 600);
  };

  // ─────────── 테마 / 동작 ───────────
  const sysDark = window.matchMedia('(prefers-color-scheme: dark)');
  function applyTheme(pref, persist) {
    const t = pref === 'system' ? (sysDark.matches ? 'dark' : 'light') : pref;
    document.documentElement.dataset.theme = t;
    backend.call('window_theme', { theme: t }).catch(() => { });
    setTimeout(() => { for (const k of inited) RT.pages[k]?.redraw && RT.pages[k].redraw(); }, 30);
    if (persist) backend.call('config_update', { theme: pref }).then((c) => { RT.state.config = c; }).catch((e) => toast(e.message, 'err'));
  }
  RT.setTheme = (pref) => applyTheme(pref, true);
  RT.toggleTheme = () => {
    const cur = document.documentElement.dataset.theme;
    const next = cur === 'dark' ? 'light' : 'dark';
    // 픽셀 와이프 느낌: 버튼 위치에서 퍼지는 원형 전환
    const b = $('#btn-theme').getBoundingClientRect();
    RT.fx.burstPoints([{ x: b.left + b.width / 2, y: b.top + b.height / 2 }], RT.cssVar('--accent'), 28);
    RT.setTheme(next);
    if (RT.current === 'settings') RT.pages.settings.render();
  };
  sysDark.addEventListener('change', () => { if (RT.state?.config?.theme === 'system') applyTheme('system', false); });
  RT.setMotion = (reduce) => {
    document.documentElement.dataset.motion = reduce ? 'reduce' : '';
    backend.call('config_update', { reduce_motion: reduce }).then((c) => { RT.state.config = c; }).catch(() => { });
  };

  // ─────────── 프로젝트 동작 ───────────
  RT.newProject = async () => {
    const name = await modal({ title: '새 프로젝트', body: '관측 결과가 이 프로젝트 파일(.json)에 자동으로 쌓입니다.', input: { label: '프로젝트 이름', placeholder: '예: 2026-07 전천 관측' }, confirm: '만들기' });
    if (!name || !name.trim()) return;
    try {
      RT.state = await backend.call('project_new', { name: name.trim() });
      renderChrome(); toast(`'${name.trim()}' 프로젝트를 만들었습니다`);
      await refresh();
    } catch (e) { toast(e.message, 'err'); }
  };
  RT.openProject = async (path) => {
    if (!path) {
      const r = await backend.call('dialog_open_project');
      if (r.dev) path = await modal({ title: '프로젝트 열기', body: '개발 모드: 프로젝트 .json 경로를 입력하세요.', input: { label: '경로' }, confirm: '열기' });
      else path = r.path;
    }
    if (!path) return;
    try {
      RT.state = await backend.call('project_open', { path });
      renderChrome();
      toast(`${RT.state.project.name} · 관측 ${RT.state.project.obs_count}건을 불러왔습니다`);
      await refresh();
    } catch (e) { toast(e.message, 'err'); }
  };
  RT.exportFile = async (kind) => {
    const p = RT.state?.project;
    if (!p) { toast('열린 프로젝트가 없습니다', 'warn'); return; }
    const spec = kind === 'fits' ? { title: 'FITS 내보내기', name: `${p.name}.fits`, filter: 'FITS (*.fits)' } : { title: 'MOC 내보내기', name: `${p.name}_moc.fits`, filter: 'MOC FITS (*.fits)' };
    let r = await backend.call('dialog_save_file', spec);
    let path = r.path;
    if (r.dev) path = await modal({ title: spec.title, input: { label: '저장 경로', value: spec.name }, confirm: '저장' });
    if (!path) return;
    try {
      const out = await backend.call(kind === 'fits' ? 'export_fits' : 'export_moc', { path });
      toast(`저장했습니다 · ${out.path.split(/[\\/]/).pop()}`, 'ok', { action: { label: '폴더 열기', run: () => backend.call('window_reveal', { path: out.path }) } });
    } catch (e) { toast(e.message, 'err'); }
  };

  // ─────────── 명령 팔레트 ───────────
  function commands() {
    const st = RT.state || {}, p = st.project;
    const c = [
      ...PAGES.map((k, i) => ({ g: '페이지', t: NAMES[k], ic: ['home', 'antenna', 'globe', 'galaxy', 'list', 'settings', 'info'][i], k: [`Ctrl`, `${i + 1}`], run: () => go(k) })),
      { g: '프로젝트', t: '새 프로젝트…', ic: 'plus', k: ['Ctrl', 'N'], run: RT.newProject },
      { g: '프로젝트', t: '프로젝트 열기…', ic: 'folder', k: ['Ctrl', 'O'], run: () => RT.openProject() },
      ...(st.recent || []).filter((r) => !p || r.path !== p.path).slice(0, 5).map((r) => ({ g: '최근 프로젝트', t: `${r.name}`, sub: `관측 ${r.obs}`, ic: 'clock', run: () => RT.openProject(r.path) })),
      ...(p ? [
        { g: '프로젝트', t: '프로젝트 닫기', ic: 'close-project', run: async () => { await backend.call('project_close'); await refresh(); toast('프로젝트를 닫았습니다'); } },
        { g: '프로젝트', t: 'FITS 하늘 지도 내보내기', ic: 'download', run: () => RT.exportFile('fits') },
        { g: '프로젝트', t: 'MOC 커버리지 내보내기', ic: 'download', run: () => RT.exportFile('moc') },
        { g: '프로젝트', t: '프로젝트 폴더 열기', ic: 'reveal', run: () => backend.call('window_reveal', { path: p.path }) },
      ] : []),
      { g: '관측', t: '분석 실행', ic: 'play', k: ['Ctrl', '↵'], run: async () => { await go('observe'); RT.pages.observe.run(); } },
      { g: '관측', t: '방향: 은하 중심', ic: 'target', run: async () => { await go('observe'); $('#obs-preset').value = 'gal:0:0'; RT.pages.observe.applyPreset('gal:0:0'); } },
      { g: '관측', t: '방향: 지금 천정', ic: 'target', run: async () => { await go('observe'); $('#obs-preset').value = 'zenith'; RT.pages.observe.applyPreset('zenith'); } },
      { g: '은하 지도', t: '관측 데이터로 나선팔 추론', ic: 'spark', run: async () => { await go('galaxy'); RT.pages.galaxy.mode.set('infer', true); } },
      { g: '은하 지도', t: '문헌 모델 예측 보기', ic: 'layers', run: async () => { await go('galaxy'); RT.pages.galaxy.mode.set('model', true); } },
      { g: '은하 지도', t: '추론과 모델 겹쳐 보기', ic: 'layers', run: async () => { await go('galaxy'); RT.pages.galaxy.mode.set('compare', true); } },
      { g: '은하 지도', t: '합성 데이터 만들기', ic: 'dice', run: async () => { await go('galaxy'); RT.pages.galaxy.generateSynthetic(); } },
      { g: '은하 지도', t: '합성 데이터 지우기', ic: 'trash', run: async () => { await go('galaxy'); RT.pages.galaxy.clearSynthetic(); } },
      { g: '화면', t: '테마 전환 (다크/라이트)', ic: 'moon', k: ['Ctrl', 'Shift', 'L'], run: RT.toggleTheme },
      { g: '화면', t: '사이드바 접기/펴기', ic: 'sidebar', k: ['Ctrl', 'B'], run: toggleSidebar },
      { g: '화면', t: '애니메이션 줄이기 켜기/끄기', ic: 'spark', run: () => { const on = document.documentElement.dataset.motion !== 'reduce'; RT.setMotion(on); toast(on ? '애니메이션을 줄였습니다' : '애니메이션을 켰습니다'); } },
    ];
    return c;
  }
  const pal = { open: false, items: [], idx: 0 };
  function score(q, t) {
    if (!q) return { s: 1, h: esc(t) };
    const lt = t.toLowerCase(), lq = q.toLowerCase();
    const i = lt.indexOf(lq);
    if (i >= 0) return { s: 100 - i, h: esc(t.slice(0, i)) + '<mark>' + esc(t.slice(i, i + q.length)) + '</mark>' + esc(t.slice(i + q.length)) };
    let j = 0, h = '';
    for (const ch of t) { if (j < lq.length && ch.toLowerCase() === lq[j]) { h += `<mark>${esc(ch)}</mark>`; j++; } else h += esc(ch); }
    return j === lq.length ? { s: 10, h } : null;
  }
  function renderPalette() {
    const q = $('#palette-input').value.trim();
    const list = commands().map((c) => { const m = score(q, c.t + (c.sub ? ' ' + c.sub : '')) || score(q, c.g + ' ' + c.t); return m ? { ...c, ...m } : null; }).filter(Boolean);
    if (q) list.sort((a, b) => b.s - a.s);
    pal.items = list; pal.idx = Math.min(pal.idx, Math.max(0, list.length - 1));
    let g = null, html = '';
    list.forEach((c, i) => {
      if (!q && c.g !== g) { g = c.g; html += `<div class="pl-group">${esc(g)}</div>`; }
      html += `<div class="pl-item ${i === pal.idx ? 'active' : ''}" data-i="${i}">${icon(c.ic)}<span>${c.h}</span>${c.k ? `<span class="pl-hint">${c.k.map((k) => `<kbd>${k}</kbd>`).join('')}</span>` : ''}</div>`;
    });
    $('#palette-list').innerHTML = html || '<div class="pl-empty">일치하는 명령이 없습니다</div>';
    const a = $('.pl-item.active'); a && a.scrollIntoView({ block: 'nearest' });
  }
  function openPalette(q = '') {
    pal.open = true; pal.idx = 0; $('#palette').hidden = false;
    const inp = $('#palette-input'); inp.value = q; renderPalette(); setTimeout(() => inp.focus(), 10);
  }
  function closePalette() { pal.open = false; $('#palette').hidden = true; }
  function runPalette(i) { const c = pal.items[i]; closePalette(); if (c) setTimeout(() => c.run(), 60); }

  function toggleSidebar() { $('#app').classList.toggle('collapsed'); setTimeout(() => placeIndicator(false), 420); RT.saveUI('collapsed', $('#app').classList.contains('collapsed')); }

  // ─────────── 이벤트 연결 ───────────
  function wire() {
    $$('.nav-item').forEach((n) => n.addEventListener('click', () => go(n.dataset.page)));
    $('.brand').addEventListener('click', () => go('home'));
    $('#side-project').addEventListener('click', (e) => {
      const c = e.target.closest('.sp-card'); if (!c) return;
      c.dataset.act === 'new' ? RT.newProject() : go('home');
    });
    $('#btn-sidebar').onclick = toggleSidebar;
    $('#btn-theme').onclick = RT.toggleTheme;
    $('#btn-palette').onclick = () => openPalette();
    $('#project-chip').onclick = () => openPalette('프로젝트');
    $('#palette-input').addEventListener('input', () => { pal.idx = 0; renderPalette(); });
    $('#palette-list').addEventListener('click', (e) => { const it = e.target.closest('.pl-item'); if (it) runPalette(+it.dataset.i); });
    $('#palette-list').addEventListener('pointermove', (e) => {
      const it = e.target.closest('.pl-item'); if (!it || +it.dataset.i === pal.idx) return;
      pal.idx = +it.dataset.i; $$('.pl-item').forEach((x) => x.classList.toggle('active', x === it));
    });
    $('#palette').addEventListener('click', (e) => { if (e.target.id === 'palette') closePalette(); });

    document.addEventListener('keydown', (e) => {
      if (pal.open) {
        if (e.key === 'Escape') { e.preventDefault(); closePalette(); }
        else if (e.key === 'ArrowDown') { e.preventDefault(); pal.idx = Math.min(pal.items.length - 1, pal.idx + 1); renderPalette(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); pal.idx = Math.max(0, pal.idx - 1); renderPalette(); }
        else if (e.key === 'Enter') { e.preventDefault(); runPalette(pal.idx); }
        return;
      }
      if (!$('#modal').hidden) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); }
      else if (mod && e.shiftKey && e.key.toLowerCase() === 'l') { e.preventDefault(); RT.toggleTheme(); }
      else if (mod && e.key.toLowerCase() === 'b') { e.preventDefault(); toggleSidebar(); }
      else if (mod && e.key.toLowerCase() === 'n') { e.preventDefault(); RT.newProject(); }
      else if (mod && e.key.toLowerCase() === 'o') { e.preventDefault(); RT.openProject(); }
      else if (mod && e.key === 'Enter') { e.preventDefault(); go('observe').then(() => RT.pages.observe.run()); }
      else if (mod && /^[1-7]$/.test(e.key)) { e.preventDefault(); go(PAGES[+e.key - 1]); }
      else if (RT.current === 'galaxy' && !e.target.closest('input, select, textarea')) {
        if (e.key === '+' || e.key === '=') RT.pages.galaxy.map.zoom(1.3);
        if (e.key === '-') RT.pages.galaxy.map.zoom(1 / 1.3);
        if (e.key === '0') RT.pages.galaxy.map.reset();
      }
    });
    window.addEventListener('resize', () => placeIndicator(false));
  }

  // ─────────── 부팅 ───────────
  async function boot() {
    await backend.init();
    let ok = true;
    try { RT.state = await backend.call('state'); }
    catch (e) { ok = false; RT.state = { config: {}, constants: {}, app: {} }; }
    const c = RT.state.config || {};
    if (c.reduce_motion) document.documentElement.dataset.motion = 'reduce';
    if (c.theme) applyTheme(c.theme, false);
    if (c.ui?.collapsed) $('#app').classList.add('collapsed');
    wire();
    const splashDone = RT.splash();
    renderChrome && ok && renderChrome();
    await splashDone;
    $('#app').classList.add('ready');
    const start = c.ui?.page && PAGES.includes(c.ui.page) ? c.ui.page : 'home';
    await go(start);
    placeIndicator(false);
    if (!ok) toast('백엔드에 연결하지 못했습니다 — main_app.py 또는 scripts/dev_server.py 로 실행하세요', 'err', { ms: 9000 });
  }
  document.addEventListener('DOMContentLoaded', boot);
})(window.RT);
