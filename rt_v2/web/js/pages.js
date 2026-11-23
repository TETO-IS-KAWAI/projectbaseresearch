/* pages.js — 화면별 컨트롤러 */
'use strict';
(function (RT) {
  const { $, $$, el, esc, fmt, icon, backend, bus, toast, modal, tip, kvHTML, countUp, segmented, bindRange,
    eq2gal, gal2eq, parseRA, parseDec, raToHMS, decToDMS, cssVar, clamp, FIT_COLORS, ARM_KO, armColor, D2R, R2D } = RT;
  const pages = {};
  const S = () => RT.state || {};
  const cfg = () => S().config || {};
  const proj = () => S().project;
  const saveUI = (key, val) => RT.saveUI && RT.saveUI(key, val);

  // ═══════════════════════════ 홈 ═══════════════════════════
  pages.home = {
    async enter() { await this.render(); },
    async render() {
      const st = S(), p = proj(), c = cfg();
      $('#home-chips').innerHTML = [
        p ? `<span class="chip"><span class="dot live"></span>프로젝트 <b>${esc(p.name)}</b></span>`
          : `<span class="chip"><span class="dot"></span>열린 프로젝트 없음</span>`,
        `<span class="chip"><span>R<sub>0</sub> <b>${st.constants?.R0 ?? '—'} kpc</b> · Θ<sub>0</sub> <b>${st.constants?.V0 ?? '—'} km/s</b></span></span>`,
        `<span class="chip"><span>관측지 <b>${fmt(c.obs_lat, 2)}°N ${fmt(c.obs_lon, 2)}°E</b></span></span>`,
        `<span class="chip"><span>HEALPix <b>nside ${p ? p.nside : c.nside}</b></span></span>`,
      ].join('');
      const body = $('#home-body');
      let list = { items: [] };
      try { list = await backend.call('projects_list'); } catch (_) { }
      const projRows = list.items.length ? list.items.map((it) => `
        <div class="proj-row" data-path="${esc(it.path)}">
          <div class="sp-avatar ${p && p.path === it.path ? '' : 'off'}">${esc((it.name || '?').slice(0, 2).toUpperCase())}</div>
          <div style="min-width:0"><div class="pr-name">${esc(it.name)}</div><div class="pr-path">${esc(it.path)}</div></div>
          <div class="pr-meta"><span class="badge">관측 ${it.obs}</span><span class="badge">피크 ${it.peaks}</span>${it.nside ? `<span class="badge">nside ${it.nside}</span>` : ''}
          ${it.recent ? `<button class="icon-btn pr-forget" title="최근 목록에서 빼기" data-forget="${esc(it.path)}">${icon('x')}</button>` : ''}</div>
        </div>`).join('') : `<div class="proj-row" style="cursor:default"><span class="muted">${esc(list.dir || '')} 에 프로젝트가 없습니다.</span></div>`;

      if (!p) {
        body.innerHTML = `
          <div class="sec-head"><div><span class="eyebrow">Get started</span><h2>시작하기</h2></div></div>
          <div class="home-grid">
            <div class="card spot action-card primary" data-act="new"><div class="ac-icon">${icon('plus')}</div><span class="ac-arrow">${icon('chevron')}</span><h3>새 프로젝트</h3><p>관측을 모을 프로젝트(.json)를 만듭니다</p></div>
            <div class="card spot action-card" data-act="open"><div class="ac-icon">${icon('folder')}</div><span class="ac-arrow">${icon('chevron')}</span><h3>프로젝트 열기</h3><p>예전에 모은 관측 데이터를 불러옵니다</p></div>
            <div class="card spot action-card" data-act="demo"><div class="ac-icon">${icon('galaxy')}</div><span class="ac-arrow">${icon('chevron')}</span><h3>은하 지도 체험</h3><p>합성 데이터로 나선팔 추론을 미리 봅니다</p></div>
          </div>
          <div class="sec-head"><div><span class="eyebrow">Projects</span><h2>프로젝트</h2></div></div>
          <div class="card"><div class="proj-list">${projRows}</div></div>`;
      } else {
        const cover = p.npix ? (100 * p.pixels_observed / p.npix) : 0;
        body.innerHTML = `
          <div class="sec-head"><div><span class="eyebrow">Pipeline</span><h2>${esc(p.name)}</h2></div>
            <div class="tools"><button class="btn btn-secondary btn-sm" data-act="reveal">${icon('reveal')}폴더 열기</button><button class="btn btn-ghost btn-sm" data-act="close">${icon('close-project')}닫기</button></div></div>
          <div class="steps">
            <div class="step ${p.obs_count ? 'done' : ''}" data-go="observe"><div class="st-num"><i></i>STEP 01</div><h4>관측</h4><p>방향을 정하고 스펙트럼을 분석</p><div class="st-val" data-count="${p.obs_count}" data-d="0">0<small>건</small></div></div>
            <div class="step ${p.pixels_observed ? 'done' : ''}" data-go="sky"><div class="st-num"><i></i>STEP 02</div><h4>하늘 지도</h4><p>HEALPix 천구에 밝기온도 누적</p><div class="st-val" data-count="${cover}" data-d="1" data-unit="%">0</div></div>
            <div class="step ${p.peak_count ? 'done' : ''}" data-go="galaxy"><div class="st-num"><i></i>STEP 03</div><h4>은하 지도</h4><p>피크 → 운동학적 거리 → 나선팔</p><div class="st-val" data-count="${p.peak_count}" data-d="0" data-unit="피크">0</div></div>
          </div>
          <div class="sec-head"><div><span class="eyebrow">Recent</span><h2>최근 관측</h2></div><div class="tools"><button class="btn btn-ghost btn-sm" data-go="log">전체 보기 ${icon('chevron')}</button></div></div>
          <div class="card"><div class="table-wrap"><table class="table" id="home-recent"></table></div></div>
          <div class="sec-head"><div><span class="eyebrow">Projects</span><h2>다른 프로젝트</h2></div><div class="tools"><button class="btn btn-secondary btn-sm" data-act="new">${icon('plus')}새 프로젝트</button><button class="btn btn-secondary btn-sm" data-act="open">${icon('folder')}열기</button></div></div>
          <div class="card"><div class="proj-list">${projRows}</div></div>`;
        $$('[data-count]', body).forEach((n) => countUp(n, +n.dataset.count, +n.dataset.d, { unit: n.dataset.unit || (n.dataset.d === '0' ? '건' : '') }));
        try {
          const obs = (await backend.call('observations')).items.slice(-5).reverse();
          $('#home-recent').innerHTML = `<thead><tr><th>#</th><th class="left">시각 (UTC)</th><th>l<span class="u">deg</span></th><th>b<span class="u">deg</span></th><th>T<sub>b</sub><span class="u">K</span></th><th>피크</th></tr></thead><tbody>${obs.length ? obs.map((o) => `<tr><td>${o.index + 1}</td><td class="left">${esc(o.time || '—')}</td><td>${fmt(o.l, 1)}</td><td>${fmt(o.b, 1, { sign: true })}</td><td>${fmt(o.T, 2)}</td><td>${o.n_peaks}</td></tr>`).join('') : '<tr><td colspan="6" class="empty">아직 관측이 없습니다 — <b>관측</b>에서 시작하세요.</td></tr>'}</tbody>`;
        } catch (_) { }
      }
      $$('.card, .step', body).forEach((n, i) => { n.classList.add('rise'); n.style.setProperty('--i', i + 2); });
      body.onclick = async (e) => {
        const f = e.target.closest('[data-forget]');
        if (f) { e.stopPropagation(); await backend.call('project_forget', { path: f.dataset.forget }); RT.refresh(); return; }
        const row = e.target.closest('.proj-row[data-path]');
        if (row) { RT.openProject(row.dataset.path); return; }
        const go = e.target.closest('[data-go]'); if (go) { RT.go(go.dataset.go); return; }
        const act = e.target.closest('[data-act]'); if (!act) return;
        const a = act.dataset.act;
        if (a === 'new') RT.newProject();
        else if (a === 'open') RT.openProject();
        else if (a === 'close') { await backend.call('project_close'); await RT.refresh(); toast('프로젝트를 닫았습니다'); }
        else if (a === 'reveal' && p) backend.call('window_reveal', { path: p.path });
        else if (a === 'demo') { await pages.galaxy.generateSynthetic(); RT.go('galaxy'); }
      };
    },
    onState() { if (RT.current === 'home') this.render(); },
  };

  // ═══════════════════════════ 관측 ═══════════════════════════
  const PRESETS = [
    ['custom', '직접 입력'],
    ['zenith', '지금 천정 방향'],
    ['gal:0:0', '은하 중심 (Sgr A*) · l 0°'],
    ['gal:30:0', '은하면 l 30° · 방패자리'],
    ['gal:60:0', '은하면 l 60° · 여우자리'],
    ['gal:90:0', '은하면 l 90° · 백조자리'],
    ['gal:120:0', '은하면 l 120° · 카시오페이아'],
    ['gal:150:0', '은하면 l 150° · 기린자리'],
    ['gal:180:0', '은하 반중심 l 180° · 마차부'],
    ['gal:210:0', '은하면 l 210° · 외뿔소'],
    ['gal:0:90', '북은하극 b +90° (HI 약함)'],
  ];
  pages.observe = {
    init() {
      const sel = $('#obs-preset');
      sel.innerHTML = PRESETS.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join('');
      sel.onchange = () => this.applyPreset(sel.value);
      this.src = segmented($('#obs-source'), (v) => { $('#obs-file-row').hidden = v !== 'file'; });
      this.method = segmented($('#obs-method'));
      this.kind = segmented($('#spec-kind'), () => this.drawChart(true));
      this.axis = segmented($('#spec-axis'), () => this.drawChart(true));
      $('#obs-ra').addEventListener('input', () => { sel.value = 'custom'; this.hint(); });
      $('#obs-dec').addEventListener('input', () => { sel.value = 'custom'; this.hint(); });
      $('#obs-time').value = this.nowUTC();
      $('#obs-now').onclick = () => { $('#obs-time').value = this.nowUTC(); this.hint(); };
      $('#obs-time').addEventListener('input', () => this.hint());
      $('#obs-file-btn').onclick = () => this.pickFile();
      $('#obs-run').onclick = () => this.run();
      this.filePath = '';
      this.chart = new RT.LineChart($('#spec-chart'));
      this.wave = new RT.PixelWave($('#spec-empty-art'));
      this.wave.start();
      this.renderStats(null);
      this.renderPeaks(null);
      bus.on('backend:progress', (p) => this.progress(p.step));
      this.hint();
      backend.call('last_result').then((r) => { if (r) this.show(r, false); }).catch(() => { });
      setInterval(() => { if (RT.current === 'observe') this.hint(); }, 15000);
    },
    enter() {
      const c = cfg();
      if (!this._methodSet && c.temp_method) { this.method.set(c.temp_method); this._methodSet = true; }
      const p = proj();
      $('#obs-proj-hint').textContent = p ? `→ ${p.name}` : '저장 안 됨 (프로젝트 없음)';
      this.hint();
    },
    nowUTC() { return new Date().toISOString().slice(0, 19); },
    applyPreset(v) {
      let ra, dec;
      if (v === 'zenith') { ra = RT.zenithRA(new Date(), cfg().obs_lon ?? 127); dec = cfg().obs_lat ?? 36.5; $('#obs-time').value = this.nowUTC(); }
      else if (v.startsWith('gal:')) { const [, l, b] = v.split(':').map(Number); [ra, dec] = gal2eq(l, b); }
      else return;
      $('#obs-ra').value = raToHMS(ra); $('#obs-dec').value = decToDMS(dec).replace('−', '-').replace('°', 'd').replace('′', 'm').replace('″', 's');
      this.hint();
    },
    setDirection(ra, dec) {
      $('#obs-preset').value = 'custom';
      $('#obs-ra').value = (+ra).toFixed(4); $('#obs-dec').value = (+dec).toFixed(4); this.hint();
    },
    hint() {
      const ra = parseRA($('#obs-ra').value), dec = parseDec($('#obs-dec').value);
      $('#obs-ra').classList.toggle('invalid', !Number.isFinite(ra));
      $('#obs-dec').classList.toggle('invalid', !Number.isFinite(dec));
      const h = $('#obs-coord-hint');
      if (!Number.isFinite(ra) || !Number.isFinite(dec)) {
        h.className = 'coord-hint mono err'; h.textContent = '좌표 형식 오류 — 예: 266.4 · 17h45m40s · 17:45:40 / −28.9 · −29d00m28s'; return null;
      }
      const [l, b] = eq2gal(ra, dec);
      // 관측 시각 기준 고도
      let altTxt = '';
      const t = new Date(($('#obs-time').value || '').trim() + 'Z');
      if (!isNaN(t)) {
        const lat = (cfg().obs_lat ?? 36.5) * D2R, H = (RT.zenithRA(t, cfg().obs_lon ?? 127) - ra) * D2R;
        const alt = Math.asin(Math.sin(lat) * Math.sin(dec * D2R) + Math.cos(lat) * Math.cos(dec * D2R) * Math.cos(H)) * R2D;
        altTxt = ` · 고도 ${fmt(alt, 0, { sign: true })}°`;
        h.className = 'coord-hint mono ' + (alt < 0 ? 'err' : 'ok');
      } else h.className = 'coord-hint mono ok';
      h.textContent = `→ ${fmt(ra, 3)}°, ${fmt(dec, 3, { sign: true })}° · l ${fmt(l, 1)}° b ${fmt(b, 1, { sign: true })}°${altTxt}`;
      return { ra, dec };
    },
    async pickFile() {
      let r = await backend.call('dialog_open_iq');
      if (r.dev) {
        const p = await modal({ title: 'SDR 파일 경로', body: '개발 모드에서는 파일 대화상자 대신 경로를 직접 입력합니다.', input: { label: '경로 (.wav / .bin)', value: this.filePath } });
        r = { path: p || null, name: p ? p.split(/[\\/]/).pop() : null };
      }
      if (!r.path) return;
      this.filePath = r.path;
      $('#obs-file-name').textContent = r.name || r.path; $('#obs-file-row').classList.add('has');
    },
    progress(step) {
      const order = ['load', 'fft', 'doppler', 'bandpass', 'peaks', 'distance', 'save', 'done'];
      const k = order.indexOf(step);
      $$('#obs-pipeline li').forEach((li) => {
        const j = order.indexOf(li.dataset.s);
        li.classList.toggle('done', j < k || step === 'done');
        li.classList.toggle('now', j === k && step !== 'done');
      });
      if (this.loader) this.loader.set((k + 1) / order.length);
    },
    async run() {
      if (this.busy) return;
      const dir = this.hint();
      if (!dir) { toast('좌표 형식을 확인하세요', 'err'); return; }
      const source = this.src.value;
      if (source === 'file' && !this.filePath) { toast('SDR 데이터 파일을 먼저 선택하세요', 'warn'); this.pickFile(); return; }
      this.busy = true;
      const btn = $('#obs-run'); btn.classList.add('running');
      this.loader = new RT.PixelLoader(btn);
      $$('#obs-pipeline li').forEach((li) => li.classList.remove('done', 'now'));
      this.progress('load');
      try {
        const r = await backend.call('run_observation', {
          ra: $('#obs-ra').value, dec: $('#obs-dec').value, obs_time: $('#obs-time').value,
          source, file_path: this.filePath, temp_method: this.method.value,
        });
        this.progress('done');
        this.show(r, true);
        if (r.summary.saved) toast(`관측 #${r.project.obs_count} 저장 · 피크 ${r.peaks.length}개`, 'ok');
        else if (!proj()) toast('결과는 표시만 되고 저장되지 않았습니다', 'warn', { action: { label: '프로젝트 만들기', run: () => RT.newProject() } });
        RT.refresh();
      } catch (e) {
        $$('#obs-pipeline li').forEach((li) => li.classList.remove('now'));
        toast(e.message, 'err');
      } finally {
        this.loader.stop(); this.loader = null; btn.classList.remove('running'); this.busy = false;
      }
    },
    show(r, animate) {
      this.res = r;
      $('#spec-empty').hidden = true; this.wave.stop();
      this.renderStats(r);
      this.renderPeaks(r);
      this.drawChart(animate);
    },
    renderStats(r) {
      const s = r?.summary;
      const P = [
        ['v_corr', 'LSR 보정 속도', '--blue', s?.v_corr, 2, 'km/s', { sign: true }, s ? `${s.source === 'file' ? 'SDR 파일' : '시뮬레이션'}` : ''],
        ['T_rep', `대표 T_b (${s?.temp_method || cfg().temp_method || 'peak'})`, '--accent', s?.T, 2, s?.temp_method === 'integral' ? 'K·km/s' : 'K', {}, '하늘 지도 색'],
        ['T_peak', '선 피크 밝기온도', '--green', s?.T_peak, 2, 'K', {}, '상대 눈금 (T_sys 가정)'],
        ['W_HI', '적분 강도', '--violet', s?.W, 1, 'K·km/s', {}, '|v| < 150 km/s'],
        ['l, b', '은하 좌표', '--amber', null, 0, '', {}, s ? `RA ${fmt(s.ra, 2)}° Dec ${fmt(s.dec, 2, { sign: true })}°` : ''],
        ['v_tan', '접선점 최대 속도', '--c-perseus', s?.v_tan, 1, 'km/s', { sign: true }, '평탄 회전 곡선'],
        ['d_kin', '운동학적 거리', '--c-scutum', null, 0, '', {}, !s ? '' : (s.d_near === null || s.d_near === undefined) ? '이 방향·속도로는 거리 불가' : s.d_near === s.d_far ? '유일해' : '내부 은하: 근 / 원'],
        ['peaks', '검출 피크', '--red', r ? r.peaks.length : null, 0, '개', {}, s ? `${fmt(s.elapsed, 2)} s 소요` : ''],
      ];
      const box = $('#obs-stats');
      if (!box.children.length) {
        box.innerHTML = P.map(([k, name, c]) => `<div class="param" style="--c:var(${c})" data-k="${k}"><div class="param-key"><i></i>${esc(k)}</div><div class="param-name">${esc(name)}</div><div class="param-val na">—</div><div class="param-sub"></div></div>`).join('');
      }
      P.forEach(([k, name, , val, d, unit, o, sub]) => {
        const cell = $(`[data-k="${k}"]`, box);
        $('.param-name', cell).textContent = name;
        $('.param-sub', cell).textContent = sub || '';
        const v = $('.param-val', cell);
        if (!s) { v.className = 'param-val na'; v.textContent = '—'; v.dataset.v = ''; return; }
        if (k === 'l, b') { v.className = 'param-val'; v.innerHTML = `${fmt(s.l, 1)}<small>°</small> ${fmt(s.b, 1, { sign: true })}<small>°</small>`; return; }
        if (k === 'd_kin') {
          v.className = 'param-val';
          if (s.d_near === null || s.d_near === undefined) { v.className = 'param-val na'; v.textContent = '해 없음'; return; }
          v.innerHTML = s.d_near === s.d_far ? `${fmt(s.d_far, 2)}<small>kpc</small>` : `${fmt(s.d_near, 1)}<small>/</small>${fmt(s.d_far, 1)}<small>kpc</small>`;
          return;
        }
        v.className = 'param-val'; countUp(v, val, d, { ...o, unit });
      });
    },
    renderPeaks(r) {
      const t = $('#obs-peaks');
      $('#obs-peaks-count').textContent = r ? `${r.peaks.length} peaks · MAD 4σ` : '';
      const rows = r?.peaks?.length ? r.peaks.map((p, i) => {
        const badge = !p.valid ? '<span class="badge red">거리 없음</span>' : p.ambiguous ? '<span class="badge warn">근/원 모호</span>' : '<span class="badge accent">유일해</span>';
        return `<tr><td>${i + 1}</td><td>${fmt(p.v, 2, { sign: true })}</td><td>${fmt(p.T, 2)}</td><td>${p.ambiguous ? fmt(p.d_near, 2) : '—'}</td><td>${p.valid ? fmt(p.d_far, 2) : '—'}</td><td>${fmt(p.R, 2)}</td><td>${badge}</td></tr>`;
      }).join('') : `<tr><td colspan="7" class="empty">${r ? '유의미한 피크가 없습니다 (잡음 4σ 이하)' : '분석을 실행하면 여기에 피크가 나옵니다'}</td></tr>`;
      t.innerHTML = `<thead><tr><th>#</th><th>v<sub>LSR</sub><span class="u">km/s</span></th><th>T<sub>b</sub><span class="u">K</span></th><th>d 근<span class="u">kpc</span></th><th>d 원/유일<span class="u">kpc</span></th><th>R<span class="u">kpc</span></th><th>해</th></tr></thead><tbody>${rows}</tbody>`;
    },
    drawChart(animate) {
      const r = this.res; if (!r) return;
      const sp = r.spectrum, kind = this.kind.value, axis = this.axis.value;
      let x = axis === 'v' ? sp.v_kms.slice().reverse() : sp.f_ghz.slice();
      let y = (kind === 'tb' ? sp.tb : sp.power_db).slice(); if (axis === 'v') y.reverse();
      const acc = cssVar('--accent'), red = cssVar('--red'), amber = cssVar('--amber'), sub = cssVar('--sub');
      const markers = [];
      if (axis === 'v') markers.push({ x: 0, label: 'v = 0', color: sub, dash: true });
      else markers.push({ x: 1.42040575177, label: 'HI 1420.406', color: red, dash: true });
      if (kind === 'tb') r.peaks.forEach((p, i) => markers.push({ x: axis === 'v' ? p.v : p.f_ghz, label: `P${i + 1} ${fmt(p.v, 1, { sign: true })}`, color: amber }));
      const data = {
        series: [{ x, y, color: kind === 'tb' ? acc : cssVar('--blue'), fill: true, name: kind === 'tb' ? 'T_b [K]' : '파워 [dB]', width: 1.25 }],
        markers, hlines: kind === 'tb' && r.summary.temp_method !== 'integral' ? [{ y: r.summary.T, label: `T_rep ${fmt(r.summary.T, 2)} K`, color: rgbaVar('--green', 0.9) }] : [],
        xLabel: axis === 'v' ? 'v_LSR [km/s]' : '주파수 [GHz]', yLabel: kind === 'tb' ? 'T_b [K]' : '파워 [dB]',
      };
      if (axis === 'v') data.view = [Math.max(x[0], -300), Math.min(x[x.length - 1], 300)];
      this.chart.setData(data, { animate });
      $('#spec-legend').innerHTML = kind === 'tb'
        ? `<span><i style="--c:${acc}"></i>T<sub>b</sub> (밴드패스 제거)</span><span><i class="dash" style="--c:${amber}"></i>검출 피크</span>`
        : `<span><i style="--c:${cssVar('--blue')}"></i>평균 파워 스펙트럼</span><span><i class="dash" style="--c:${red}"></i>HI 정지 주파수</span>`;
    },
    redraw() { if (this.res) this.drawChart(false); },
  };
  function rgbaVar(name, a) { return RT.rgba(cssVar(name), a); }

  // ═══════════════════════════ 하늘 지도 ═══════════════════════════
  pages.sky = {
    init() {
      this.map = new RT.SkyMap($('#sky-canvas'), {
        rightInset: 296,
        onHover: (info) => this.hoverInfo(info),
        onCursor: (c) => {
          $('#sky-cursor').textContent = c ? (c.frame === 'gal'
            ? `l ${fmt(c.lon, 2)}°  b ${fmt(c.lat, 2, { sign: true })}°   ·   RA ${raToHMS(c.ra)}  Dec ${decToDMS(c.dec)}`
            : `RA ${raToHMS(c.ra)}  Dec ${decToDMS(c.dec)}   ·   l ${fmt(eq2gal(c.ra, c.dec)[0], 2)}°`) : '';
        },
      });
      const ui = cfg().ui?.sky || {};
      this.proj = segmented($('#sky-proj'), (v) => { this.map.set('proj', v); this.map.view = { s: 1, ox: 0, oy: 0 }; saveUI('sky', { ...this.ui(), proj: v }); });
      this.frame = segmented($('#sky-frame'), (v) => { this.map.set('frame', v); saveUI('sky', { ...this.ui(), frame: v }); });
      if (ui.proj) { this.proj.set(ui.proj); this.map.proj = ui.proj; }
      if (ui.frame) { this.frame.set(ui.frame); this.map.frame = ui.frame; }
      const L = { grid: '#sky-l-grid', plane: '#sky-l-plane', cells: '#sky-l-cells', visible: '#sky-l-visible', zenith: '#sky-l-zenith', fg: '#sky-l-fg' };
      for (const [k, sel] of Object.entries(L)) {
        const inp = $(sel);
        if (ui.layers && k in ui.layers && k !== 'fg') inp.checked = ui.layers[k];
        this.map.layers[k] = k === 'fg' ? false : inp.checked;
        inp.addEventListener('change', async () => {
          if (k === 'fg' && inp.checked && !this.map.fg) {
            try {
              const f = await backend.call('foreground');
              this.map.fgScale = f.scale; this.map.fg = RT.b64f32(f.values);
              toast(`연속체 전경 차감 (${f.method === 'fits' ? 'FITS 지도' : '|b| 해석식'})`);
            } catch (e) { toast(e.message, 'err'); inp.checked = false; return; }
          }
          this.map.layers[k] = inp.checked; this.map.redraw(); this.legend();
          saveUI('sky', this.ui());
        });
      }
      $('#sky-colorbar').style.background = RT.cmapGradient();
      $('#sky-fits').onclick = () => RT.exportFile('fits');
      $('#sky-moc').onclick = () => RT.exportFile('moc');
    },
    ui() { return { proj: this.proj.value, frame: this.frame.value, layers: { ...this.map.layers } }; },
    async enter() {
      const c = cfg();
      this.map.site = { lat: c.obs_lat ?? 36.5, lon: c.obs_lon ?? 127.2 };
      this.proj.relayout(); this.frame.relayout();
      try {
        const sky = await backend.call('sky');
        if (!this.map.geom || this.map.geom.nside !== sky.nside) {
          this.map.setGeometry(await backend.call('sky_geometry', { nside: sky.nside }));
          this.map.fg = null; $('#sky-l-fg').checked = false; this.map.layers.fg = false;
        }
        this.map.setData(sky);
        this.sky = sky;
        this.stats();
        setTimeout(() => this.legend(), 30);
        if (this.pendingFocus !== undefined) { this.map.focusPixel(this.pendingFocus); this.pendingFocus = undefined; }
      } catch (e) { toast(e.message, 'err'); }
    },
    stats() {
      const s = this.sky, g = this.map.geom; if (!s || !g) return;
      $('#sky-stats').innerHTML = [
        ['nside', s.nside], ['픽셀', `${s.npix.toLocaleString()} · ${fmt(g.pixDeg, 1)}°`],
        ['관측 픽셀', `${s.pixels.length}`], ['커버리지', `${fmt(100 * s.pixels.length / s.npix, 1)} %`],
      ].map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('');
    },
    legend() {
      const [a, b] = this.map.range();
      const has = this.map.vals.size > 0;
      $('#sky-vmin').textContent = has ? fmt(a, 2) : '—'; $('#sky-vmax').textContent = has ? fmt(b, 2) : '—';
      $('#sky-unit').textContent = this.map.layers.fg ? 'K (전경 차감)' : 'K';
    },
    hoverInfo(i) {
      const box = $('#sky-hover-kv');
      if (!i) { box.innerHTML = '<span class="muted">지도 위에 마우스를 올려 보세요</span>'; return; }
      box.innerHTML = [
        ['#', i.pix], ['RA', raToHMS(i.ra)], ['Dec', decToDMS(i.dec)], ['l, b', `${fmt(i.l, 1)}°, ${fmt(i.b, 1, { sign: true })}°`],
        ['T_b', i.T !== null ? `${fmt(i.Tdisp, 3)} K` : '<span class="muted">미관측</span>'], ['관측', `${i.hits}회`],
        ...(i.fg !== null && this.map.layers.fg ? [['전경', `${fmt(i.fg, 3)} K`]] : []),
        ...(i.hidden ? [['', '<span style="color:var(--red)">이 위도에선 안 뜸</span>']] : []),
      ].map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('');
    },
    redraw() { this.map.redraw(); },
    focus(pix) { this.pendingFocus = pix; },
  };

  // ═══════════════════════════ 은하 지도 ═══════════════════════════
  pages.galaxy = {
    init() {
      this.map = new RT.GalaxyMap($('#gal-canvas'), {
        rightInset: 372,
        onHover: (h, x, y) => this.tooltip(h, x, y),
        onCursor: (wx, wy) => this.cursor(wx, wy),
        onScale: (s) => this.scalebar(s),
        onSelect: () => { },
      });
      const ui = cfg().ui?.galaxy || {};
      this.opt = Object.assign({ mode: 'infer', amb: 'auto', bmax: 30, tol: 0.08, minpts: 4, obs: true, syn: true }, ui);
      this.mode = segmented($('#gal-mode'), (v) => this.setMode(v));
      this.amb = segmented($('#gal-amb'), (v) => { this.opt.amb = v; this.infer(); });
      this.viewSeg = segmented($('#gal-view'), (v) => { this.map.opts.view = v; this.map.draw(); this.persist(); });
      this.amb.set(this.opt.amb);
      const R = (id, key, f) => {
        const inp = $(id); inp.value = this.opt[key];
        bindRange(inp, $(id + '-o'), f);
        inp.addEventListener('input', () => { this.opt[key] = +inp.value; this.inferSoon(); });
      };
      R('#gal-bmax', 'bmax', (v) => `${v}°`);
      R('#gal-tol', 'tol', (v) => `±${fmt(v * 8.15, 2)} kpc`);
      R('#gal-minpts', 'minpts', (v) => `${v}`);
      const sw = (id, key, target) => {
        const inp = $(id);
        if (key in this.opt) inp.checked = !!this.opt[key]; else if (target && ui[key] !== undefined) inp.checked = ui[key];
        if (target) this.map.opts[target] = inp.checked;
        inp.addEventListener('change', () => {
          if (target) { this.map.opts[target] = inp.checked; this.map.draw(); this.opt[key] = inp.checked; this.persist(); }
          else { this.opt[key] = inp.checked; this.infer(); }
        });
      };
      sw('#gal-use-obs', 'obs'); sw('#gal-use-syn', 'syn');
      sw('#gal-alt', 'alt', 'alt'); sw('#gal-excl', 'excl', 'excl'); sw('#gal-band', 'band', 'band'); sw('#gal-sight', 'sight', 'sight');
      if (ui.view) { this.viewSeg.set(ui.view); this.map.opts.view = ui.view; }
      $('#gal-zin').onclick = () => this.map.zoom(1.4);
      $('#gal-zout').onclick = () => this.map.zoom(1 / 1.4);
      $('#gal-zreset').onclick = () => this.map.reset();
      $('#gal-syn-gen').onclick = () => this.generateSynthetic();
      $('#gal-syn-clear').onclick = () => this.clearSynthetic();
      this.mode.set(this.opt.mode); this.setMode(this.opt.mode, true);
    },
    persist() {
      saveUI('galaxy', { mode: this.opt.mode, amb: this.opt.amb, bmax: this.opt.bmax, tol: this.opt.tol, minpts: this.opt.minpts,
        obs: this.opt.obs, syn: this.opt.syn, alt: this.map.opts.alt, excl: this.map.opts.excl, band: this.map.opts.band, sight: this.map.opts.sight, view: this.map.opts.view });
    },
    setMode(v, silent) {
      this.opt.mode = v; this.map.setMode(v);
      $$('#gal-panel [data-when]').forEach((s) => { s.hidden = !s.dataset.when.split(' ').includes(v); });
      this.emptyState();
      if (!silent) this.persist();
    },
    async enter() {
      this.mode.relayout(); this.amb.relayout(); this.viewSeg.relayout();
      this.map.R0 = S().constants?.R0 || 8.15;
      $('#gal-n-syn').textContent = S().synthetic_count || 0;
      const first = !this._loaded; this._loaded = true;
      try {
        const [m] = await Promise.all([backend.call('spiral_model'), this.infer(first)]);
        this.model = m; this.map.setModel(m, first && this.opt.mode !== 'infer');
        this.modelList();
      } catch (e) { toast(e.message, 'err'); }
    },
    inferSoon() { clearTimeout(this._t); this._t = setTimeout(() => this.infer(false), 160); },
    async infer(animate = false) {
      this.persist();
      const seq = (this._seq = (this._seq || 0) + 1);
      const res = await backend.call('spiral_infer', {
        b_max_deg: this.opt.bmax, ambiguity: this.opt.amb, tol_lnr: this.opt.tol, min_points: this.opt.minpts,
        use_obs: this.opt.obs, use_synth: this.opt.syn,
      });
      if (seq !== this._seq) return;
      this.res = res;
      $('#gal-n-obs').textContent = res.n_obs_peaks; $('#gal-n-syn').textContent = res.n_synth_peaks;
      this.map.armOff.clear();
      this.map.setInfer(res, animate);
      this.fitPanel();
      this.emptyState();
    },
    fitPanel() {
      const r = this.res; if (!r) return;
      const badge = $('#gal-fit-badge');
      if (r.ok) { badge.className = 'badge accent'; badge.textContent = `팔 ${r.n_arms}개`; }
      else { badge.className = 'badge warn'; badge.textContent = r.n_total ? '추론 불가' : '데이터 없음'; }
      $('#gal-fit-kv').innerHTML = [
        ['사용한 피크', `${r.n_used} / ${r.n_total}`],
        ['팔에 배정', r.ok ? `${r.n_assigned}` : '—'],
        ['평균 피치각 ψ', r.ok ? `${fmt(r.pitch_deg, 1)}°` : '—'],
        ...(r.ok ? [] : [['', `<span style="color:var(--amber);white-space:normal">${esc(r.reason)}</span>`]]),
      ].map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('');
      const list = $('#gal-arms');
      list.innerHTML = r.ok ? r.arms.map((a, i) => `
        <div class="arm-row" data-id="${a.id}" style="--c:${FIT_COLORS[i % FIT_COLORS.length]}">
          <span class="sw"></span>
          <span class="an">팔 ${String.fromCharCode(65 + i)}${a.match?.name ? `<small>≈ ${esc(ARM_KO[a.match.name] || a.match.name)}</small>` : '<small>새 구조?</small>'}</span>
          <span class="am">ψ ${fmt(a.pitch_deg, 1)}°${a.pitch_clamped ? '*' : ''} · ${a.n}점 · ±${fmt(a.rms_kpc, 2)}</span>
        </div>`).join('') : '';
      $$('.arm-row', list).forEach((row) => {
        const id = +row.dataset.id;
        row.onclick = () => { const off = this.map.armOff; off.has(id) ? off.delete(id) : off.add(id); row.classList.toggle('off', off.has(id)); this.map.draw(); };
        row.onmouseenter = () => { this.map.highlightArm = id; this.map.draw(); };
        row.onmouseleave = () => { this.map.highlightArm = null; this.map.draw(); };
      });
      RT.drawHough($('#gal-hough'), r.hough, r.arms || []);
    },
    modelList() {
      const m = this.model; if (!m) return;
      const list = $('#gal-model-arms');
      list.innerHTML = m.arms.map((a) => `<div class="arm-row ${this.map.modelOff.has(a.name) ? 'off' : ''}" data-n="${esc(a.name)}" style="--c:${armColor(a.name)}"><span class="sw"></span><span class="an">${esc(ARM_KO[a.name] || a.name)}<small>${esc(a.name)}</small></span></div>`).join('');
      $$('.arm-row', list).forEach((row) => {
        const n = row.dataset.n;
        row.onclick = () => { const off = this.map.modelOff; off.has(n) ? off.delete(n) : off.add(n); row.classList.toggle('off', off.has(n)); this.map.draw(); };
        row.onmouseenter = () => { this.map.highlightArm = 'm:' + n; this.map.draw(); };
        row.onmouseleave = () => { this.map.highlightArm = null; this.map.draw(); };
      });
    },
    emptyState() {
      const box = $('#gal-empty');
      const r = this.res;
      const noData = this.opt.mode !== 'model' && r && r.n_total === 0;
      box.hidden = !noData;
      if (noData) {
        box.innerHTML = `<h3>아직 찍을 피크가 없습니다</h3>
          <p>관측에서 HI 피크가 검출되면 운동학적 거리로 이 지도에 점이 찍히고, 점이 충분히 모이면 나선팔을 추론합니다.</p>
          <div class="btn-row"><button class="btn btn-primary btn-sm" data-a="obs">${icon('antenna')}관측하러 가기</button><button class="btn btn-secondary btn-sm" data-a="syn">${icon('dice')}합성 데이터로 체험</button><button class="btn btn-ghost btn-sm" data-a="model">문헌 모델 보기</button></div>`;
        box.onclick = (e) => {
          const a = e.target.closest('[data-a]')?.dataset.a;
          if (a === 'obs') RT.go('observe');
          if (a === 'syn') this.generateSynthetic();
          if (a === 'model') this.mode.set('model', true);
        };
      }
    },
    async generateSynthetic() {
      try {
        const r = await backend.call('synthetic_generate', { n_dirs: 48, v_noise: 7 });
        if (RT.state) RT.state.synthetic_count = r.count;
        $('#gal-use-syn').checked = true; this.opt.syn = true;
        toast(`합성 피크 ${r.count}개를 만들었습니다 (실제 관측 아님)`);
        if (this._loaded) await this.infer(true);
      } catch (e) { toast(e.message, 'err'); }
    },
    async clearSynthetic() {
      this.map.burstPoints((p) => p.src === 'synthetic');
      await backend.call('synthetic_clear');
      if (RT.state) RT.state.synthetic_count = 0;
      await this.infer(false);
      toast('합성 데이터를 지웠습니다');
    },
    tooltip(h, x, y) {
      if (!h) { tip.hide(); return; }
      if (h.kind === 'pt') {
        const p = h.ref;
        const col = p.arm >= 0 ? FIT_COLORS[p.arm % FIT_COLORS.length] : cssVar('--sub');
        const kind = { near: '근거리 해', far: '원거리 해', unique: '유일해' }[p.kind] || '';
        tip.show(`<div class="tt-title" style="--c:${col}"><i></i>${p.src === 'synthetic' ? '합성 피크' : `관측 #${p.obs + 1} 피크`}${p.arm >= 0 ? ` · 팔 ${String.fromCharCode(65 + p.arm)}` : ''}</div>` + kvHTML([
          ['l, b', `${fmt(p.l, 1)}°, ${fmt(p.b, 1, { sign: true })}°`], ['v_LSR', `${fmt(p.v, 1, { sign: true })} km/s`], ['T_b', p.T !== null ? `${fmt(p.T, 1)} K` : '—'],
          ['거리', `${fmt(p.d, 2)} kpc ${kind ? `(${kind})` : ''}`], ['R', `${fmt(p.R, 2)} kpc`],
          ...(p.residual_kpc !== null ? [['팔까지', `${fmt(p.residual_kpc, 2)} kpc`]] : []),
          ...(p.excluded ? [['제외', esc(p.excluded)]] : []),
        ]), x, y);
      } else {
        const c = h.ref;
        tip.show(`<div class="tt-title" style="--c:${armColor(c.arm)}"><i></i>예상 교차점 · ${esc(ARM_KO[c.arm] || c.arm)}</div>` + kvHTML([
          ['시선 l', `${fmt(h.sl.l, 1)}°`], ['거리', `${fmt(c.d, 2)} kpc`], ['R', `${fmt(c.R, 2)} kpc`], ['예상 v_LSR', `${fmt(c.v_lsr_pred, 1, { sign: true })} km/s`],
        ]), x, y);
      }
    },
    cursor(wx, wy) {
      const box = $('#gal-cursor');
      if (wx === null || wx === undefined) { box.textContent = ''; return; }
      const R0 = this.map.R0, R = Math.hypot(wx, R0 - wy), d = Math.hypot(wx, wy);
      let l = Math.atan2(wx, wy) * R2D; if (l < 0) l += 360;
      box.textContent = `X ${fmt(wx, 2)}  Y ${fmt(wy, 2)} kpc  ·  R ${fmt(R, 2)}  ·  l ${fmt(l, 1)}°  d ${fmt(d, 2)} kpc`;
    },
    scalebar(s) {
      const nice = [0.5, 1, 2, 5, 10].find((k) => k * s >= 70) || 10;
      const bar = $('#gal-scale');
      bar.querySelector('i').style.width = nice * s + 'px';
      bar.querySelector('span').textContent = `${nice} kpc`;
    },
    redraw() { this.map.draw(); if (this.res) RT.drawHough($('#gal-hough'), this.res.hough, this.res.arms || []); },
    onState() { if (RT.current === 'galaxy') this.infer(false); },
  };

  // ═══════════════════════════ 관측 기록 ═══════════════════════════
  pages.log = {
    init() {
      this.sort = { key: 'index', dir: -1 }; this.q = ''; this.open = null;
      $('#log-search').addEventListener('input', (e) => { this.q = e.target.value.trim().toLowerCase(); this.render(); });
    },
    async enter() {
      try { this.items = (await backend.call('observations')).items; } catch (e) { this.items = []; }
      this.render();
    },
    onState() { if (RT.current === 'log') this.enter(); },
    render() {
      const t = $('#log-table');
      const cols = [
        ['index', '#', ''], ['time', '시각 (UTC)', '', 'left'], ['ra', 'RA', 'deg'], ['dec', 'Dec', 'deg'], ['l', 'l', 'deg'], ['b', 'b', 'deg'],
        ['T', 'T 대표', 'K'], ['v', 'v 보정', 'km/s'], ['n_peaks', '피크', ''], ['file', '소스', '', 'left'],
      ];
      if (!proj()) {
        t.innerHTML = `<tbody><tr><td class="empty">열린 프로젝트가 없습니다.<div class="btn-row" style="justify-content:center"><button class="btn btn-primary btn-sm" data-a="new">${icon('plus')}새 프로젝트</button><button class="btn btn-secondary btn-sm" data-a="open">${icon('folder')}열기</button></div></td></tr></tbody>`;
        t.onclick = (e) => { const a = e.target.closest('[data-a]')?.dataset.a; if (a === 'new') RT.newProject(); if (a === 'open') RT.openProject(); };
        return;
      }
      let rows = (this.items || []).slice();
      if (this.q) rows = rows.filter((o) => [o.time, o.file, fmt(o.ra, 2), fmt(o.dec, 2), fmt(o.l, 1), fmt(o.b, 1), o.index + 1].join(' ').toLowerCase().includes(this.q));
      const { key, dir } = this.sort;
      rows.sort((a, b) => { const x = a[key], y = b[key]; return (x > y ? 1 : x < y ? -1 : 0) * dir; });
      const head = cols.map(([k, n, u, cls]) => `<th class="sortable ${cls || ''}" data-k="${k}">${n}${key === k ? `<span class="arrow">${dir > 0 ? '↑' : '↓'}</span>` : ''}${u ? `<span class="u">${u}</span>` : ''}</th>`).join('');
      const body = rows.length ? rows.map((o) => {
        const main = `<tr data-i="${o.index}" class="${this.open === o.index ? 'open' : ''}"><td>${o.index + 1}</td><td class="left">${esc(o.time || '—')}</td><td>${fmt(o.ra, 2)}</td><td>${fmt(o.dec, 2, { sign: true })}</td><td>${fmt(o.l, 1)}</td><td>${fmt(o.b, 1, { sign: true })}</td><td>${fmt(o.T, 2)}</td><td>${fmt(o.v, 2, { sign: true })}</td><td>${o.n_peaks}</td><td class="left">${o.file ? esc(o.file) : `<span class="badge">${o.source === 'sim' ? '시뮬레이션' : '—'}</span>`}</td></tr>`;
        if (this.open !== o.index) return main;
        return main + `<tr class="detail"><td colspan="10"><div class="row-detail">
          <div class="kv mono">${[['HEALPix 픽셀', o.pixel], ['선 피크 T_b', `${fmt(o.T_peak, 2)} K`], ['적분 강도', `${fmt(o.W, 1)} K·km/s`], ['RA / Dec', `${raToHMS(o.ra)} ${decToDMS(o.dec)}`]].map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('')}</div>
          <div><div class="eyebrow" style="margin-bottom:6px">검출 피크</div><div class="pk-chips">${o.peaks.length ? o.peaks.map((p) => `<span class="badge">${fmt(p.v, 1, { sign: true })} km/s · ${fmt(p.T, 1)} K</span>`).join('') : '<span class="muted">없음</span>'}</div></div>
          <div class="btn-row"><button class="btn btn-secondary btn-sm" data-a="sky">${icon('globe')}하늘 지도에서</button><button class="btn btn-secondary btn-sm" data-a="again">${icon('refresh')}같은 방향 다시</button><button class="btn btn-ghost btn-sm" data-a="del" style="color:var(--red)">${icon('trash')}삭제</button></div>
        </div></td></tr>`;
      }).join('') : `<tr><td colspan="10" class="empty">${this.q ? '검색 결과가 없습니다' : '아직 관측이 없습니다 — 관측 페이지에서 분석을 실행하세요'}</td></tr>`;
      t.innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;
      t.onclick = async (e) => {
        const th = e.target.closest('th[data-k]');
        if (th) { const k = th.dataset.k; this.sort = { key: k, dir: this.sort.key === k ? -this.sort.dir : 1 }; this.render(); return; }
        const act = e.target.closest('[data-a]');
        const o = this.items.find((x) => x.index === this.open);
        if (act && o) {
          const a = act.dataset.a;
          if (a === 'sky') { pages.sky.focus(o.pixel); RT.go('sky'); }
          if (a === 'again') { pages.observe.setDirection(o.ra, o.dec); RT.go('observe'); }
          if (a === 'del') {
            const ok = await modal({ title: `관측 #${o.index + 1} 을 삭제할까요?`, body: `${esc(o.time || '')} · l ${fmt(o.l, 1)}° 관측과 그 피크가 프로젝트 파일에서 지워집니다. 되돌릴 수 없습니다.`, confirm: '삭제', danger: true });
            if (!ok) return;
            try { await backend.call('observation_delete', { index: o.index }); this.open = null; toast('삭제했습니다'); RT.refresh(); } catch (err) { toast(err.message, 'err'); }
          }
          return;
        }
        const tr = e.target.closest('tr[data-i]');
        if (tr) { const i = +tr.dataset.i; this.open = this.open === i ? null : i; this.render(); }
      };
    },
  };

  // ═══════════════════════════ 설정 ═══════════════════════════
  pages.settings = {
    init() { this.pending = {}; },
    enter() { this.render(); },
    render() {
      const c = cfg(), p = proj();
      const num = (k, label, unit, opts = {}) => `<div class="field ${opts.full ? 'full' : ''}"><label>${label}</label><div class="unit-input"><input data-k="${k}" data-scale="${opts.scale || 1}" type="text" class="mono" value="${esc(fmt((c[k] ?? 0) / (opts.scale || 1), opts.d ?? 4).replace('−', '-'))}"><span class="unit">${unit}</span></div></div>`;
      $('#settings').innerHTML = `
        <div class="card set-group"><div><h3>관측지</h3><p class="sg-desc">도플러 보정(지구 자전)과 '지금 천정', 관측 가능 하늘 계산에 쓰입니다.</p></div>
          <div class="set-fields">
            <div class="field full"><label>이름</label><input data-k="obs_name" type="text" value="${esc(c.obs_name || '')}"></div>
            ${num('obs_lat', '위도', '°N', { d: 6 })}${num('obs_lon', '경도', '°E', { d: 6 })}${num('obs_height_m', '고도', 'm', { d: 1 })}
          </div></div>
        <div class="card set-group"><div><h3>수신기 (SDR)</h3><p class="sg-desc">녹음할 때의 중심 주파수·샘플링 속도와 같아야 주파수축이 맞습니다.</p></div>
          <div class="set-fields">
            ${num('center_freq_hz', '중심 주파수', 'MHz', { scale: 1e6, d: 6 })}${num('sample_rate', '샘플링 속도', 'MHz', { scale: 1e6, d: 3 })}
            <div class="field"><label>FFT 크기 (nfft)</label><div class="select-wrap"><select data-k="nfft">${[256, 512, 1024, 2048, 4096, 8192, 16384].map((n) => `<option ${n === c.nfft ? 'selected' : ''}>${n}</option>`).join('')}</select></div></div>
            <div class="field"><label>속도 분해능</label><div class="readout" id="set-vres" style="height:36px;display:flex;align-items:center">${fmt(c.velocity_resolution_kms, 3)} km/s / 채널</div></div>
          </div></div>
        <div class="card set-group"><div><h3>복사 측정</h3><p class="sg-desc">T<sub>b</sub> = (P/B − 1)·T<sub>sys</sub>. 잡음원·hot/cold 보정이 없으므로 절대값이 아닌 <b>상대</b> 밝기온도입니다.</p></div>
          <div class="set-fields">
            ${num('T_sys', '시스템 잡음 온도 T_sys', 'K', { d: 1 })}${num('G_sys', '시스템 이득 G_sys', '×', { d: 3 })}
            <div class="field full"><label>대표값 기본 방식</label><div class="seg" id="set-method">${['peak', 'integral', 'mean', 'median'].map((m) => `<button data-v="${m}" class="${m === c.temp_method ? 'active' : ''}">${m}</button>`).join('')}</div></div>
            <div class="field full"><label>연속체 전경 차감 비율 <output class="mono" id="set-fg-o"></output></label><input type="range" class="range" data-k="fg_scale" min="0" max="1" step="0.05" value="${c.fg_scale ?? 1}"></div>
          </div></div>
        <div class="card set-group"><div><h3>하늘 지도</h3><p class="sg-desc">HEALPix nside 는 <b>새 프로젝트부터</b> 적용됩니다. 빔(~20°)보다 훨씬 작은 픽셀은 해상도를 부풀려 보이게 합니다.</p></div>
          <div class="set-fields">
            <div class="field"><label>새 프로젝트 nside</label><div class="select-wrap"><select data-k="nside">${[1, 2, 4, 8, 16, 32, 64].map((n) => `<option value="${n}" ${n === c.nside ? 'selected' : ''}>${n} · ${12 * n * n} 픽셀 · ${fmt(58.6 / n, 1)}°</option>`).join('')}</select></div></div>
            <div class="field"><label>지금 프로젝트</label><div class="readout" style="height:36px;display:flex;align-items:center">${p ? `nside ${p.nside} · ${p.npix} 픽셀` : '열린 프로젝트 없음'}</div></div>
          </div></div>
        <div class="card set-group"><div><h3>화면</h3><p class="sg-desc">애니메이션 줄이기를 켜면 픽셀 효과·전환이 꺼집니다 (느린 PC 권장).</p></div>
          <div class="set-fields">
            <div class="field full"><label>테마</label><div class="seg" id="set-theme"><button data-v="dark" class="${c.theme === 'dark' ? 'active' : ''}">${icon('moon')}다크</button><button data-v="light" class="${c.theme === 'light' ? 'active' : ''}">${icon('sun')}라이트</button><button data-v="system" class="${c.theme === 'system' ? 'active' : ''}">시스템</button></div></div>
            <label class="switch-row full"><span>애니메이션 줄이기</span><input type="checkbox" class="switch" id="set-motion" ${c.reduce_motion ? 'checked' : ''}></label>
          </div></div>
        <div class="card set-group"><div><h3>저장 위치</h3><p class="sg-desc">설정과 프로젝트 파일이 저장되는 폴더입니다.</p></div>
          <div class="set-fields">
            <div class="field full"><label>프로젝트 폴더</label><div class="path-box"><span>${esc(c.projects_dir || '')}</span><button class="btn btn-ghost btn-sm" data-reveal="${esc(c.projects_dir || '')}">${icon('reveal')}열기</button></div></div>
            <div class="field full"><label>최근 SDR 데이터 폴더</label><div class="path-box"><span>${esc(c.data_dir || '')}</span><button class="btn btn-ghost btn-sm" data-reveal="${esc(c.data_dir || '')}">${icon('reveal')}열기</button></div></div>
          </div></div>
        <div class="card set-group"><div><h3>단축키</h3><p class="sg-desc">어디서든 <kbd>Ctrl</kbd> <kbd>K</kbd> 로 모든 명령을 찾을 수 있습니다.</p></div>
          <div class="kv mono" style="align-content:start">${[['명령 검색', 'Ctrl K'], ['페이지 이동', 'Ctrl 1 – 7'], ['분석 실행', 'Ctrl Enter'], ['새 프로젝트', 'Ctrl N'], ['프로젝트 열기', 'Ctrl O'], ['사이드바', 'Ctrl B'], ['테마 전환', 'Ctrl Shift L']].map(([a, b]) => `<span>${a}</span><span>${b.split(' ').map((k) => `<kbd>${k}</kbd>`).join(' ')}</span>`).join('')}</div></div>`;
      const box = $('#settings');
      $$('.card', box).forEach((n, i) => { n.classList.add('rise'); n.style.setProperty('--i', i + 1); });
      $$('input[data-k], select[data-k]', box).forEach((inp) => {
        const ev = inp.type === 'range' || inp.tagName === 'SELECT' ? 'input' : 'change';
        inp.addEventListener(ev, () => {
          let v = inp.value;
          if (inp.dataset.k !== 'obs_name') { v = parseFloat(String(v).replace('−', '-')) * (+inp.dataset.scale || 1); if (!Number.isFinite(v)) { inp.classList.add('invalid'); return; } }
          inp.classList.remove('invalid');
          this.queue({ [inp.dataset.k]: v });
          if (inp.dataset.k === 'fg_scale') $('#set-fg-o').textContent = `${Math.round(v * 100)} %`;
        });
      });
      const fg = $('input[data-k="fg_scale"]', box); bindRange(fg, $('#set-fg-o'), (v) => `${Math.round(v * 100)} %`);
      segmented($('#set-method'), (v) => this.queue({ temp_method: v }));
      segmented($('#set-theme'), (v) => RT.setTheme(v));
      $('#set-motion').onchange = (e) => { RT.setMotion(e.target.checked); };
      $$('[data-reveal]', box).forEach((b) => b.onclick = () => backend.call('window_reveal', { path: b.dataset.reveal }));
    },
    queue(ch) {
      Object.assign(this.pending, ch);
      const st = $('#set-state'); st.className = 'save-state mono'; st.textContent = '저장 중…';
      clearTimeout(this._t);
      this._t = setTimeout(async () => {
        const changes = this.pending; this.pending = {};
        try {
          const c = await backend.call('config_update', changes);
          RT.state.config = c;
          st.className = 'save-state mono saved'; st.textContent = '✓ 저장됨';
          const vr = $('#set-vres'); if (vr) vr.textContent = `${fmt(c.velocity_resolution_kms, 3)} km/s / 채널`;
        } catch (e) { st.textContent = ''; toast(e.message, 'err'); }
      }, 450);
    },
  };

  // ═══════════════════════════ 정보 ═══════════════════════════
  pages.about = {
    init() {
      const a = S().app || {}, cr = a.credits || {};
      $('#about-body').innerHTML = `
        <div class="about-grid">
          <div class="card rise" style="--i:1"><div class="card-head"><span class="card-title">이 앱에 대하여</span><span class="eyebrow">v${esc(a.version || '')}</span></div>
            <div class="card-body"><p>직접 만든 피라미드 혼 안테나와 저잡음 수신 체인, SDR 로 녹음한 1420.406 MHz 중성수소선(HI)을 분석합니다. IQ 데이터를 FFT 로 평균 파워 스펙트럼으로 만들고, 밴드패스를 이동 중앙값으로 걷어낸 뒤 레일리–진스 근사로 상대 밝기온도로 바꿉니다.</p>
            <p>지구 자전·공전과 태양 운동(Schönrich+2010)을 빼서 LSR 속도로 옮기고, 평탄 회전 곡선(R<sub>0</sub> = 8.15 kpc, Θ<sub>0</sub> = 236 km/s, Reid+2019)으로 운동학적 거리를 구해 은하 조감도에 찍습니다. 점들이 모이면 로그 나선 허프 변환으로 나선팔을 <b>데이터에서 직접</b> 추론합니다.</p>
            <p class="muted" style="font-size:12.5px">밝기온도는 잡음원·hot/cold 부하 보정이 없는 상대값이며, 빔(~20°)과 속도 오차 때문에 실제 관측만으로 개별 나선팔을 분해하기는 어렵습니다.</p></div></div>
          <div class="card rise" style="--i:2"><div class="card-head"><span class="card-title">만든 사람</span></div>
            <div class="card-body"><div class="eyebrow">${esc(cr.school || '')}</div><div class="credit-big" style="margin-top:6px">${esc(cr.team || '')}</div>
            <p style="margin-top:10px">코드 작성 · <span class="mono">${esc(cr.devs || '')}</span></p>
            <p class="muted" style="font-size:12.5px">© ${cr.year || ''} Team RWA · ${esc(cr.license || '')}</p>
            <div class="btn-row"><button class="btn btn-secondary btn-sm" id="about-gh">${icon('external')}GitHub</button></div></div></div>
          <div class="card rise" style="--i:3"><div class="card-head"><span class="card-title">물리 상수</span></div>
            <div class="card-body"><div class="kv mono">${[['HI 정지 주파수', '1420.405 752 MHz'], ['R₀ (태양–은하중심)', `${S().constants?.R0 ?? 8.15} kpc`], ['Θ₀ (원형 속도)', `${S().constants?.V0 ?? 236} km/s`], ['태양 고유운동 UVW', '11.1, 12.24, 7.25 km/s'], ['나선팔 모델', 'Hou & Han 2014 근사']].map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('')}</div></div></div>
          <div class="card rise" style="--i:4"><div class="card-head"><span class="card-title">사용한 도구</span></div>
            <div class="card-body"><div class="lib-list">${['PySide6 · Qt WebEngine', 'NumPy', 'SciPy', 'Astropy', 'astropy-healpix', 'Geist · Geist Mono (OFL)', 'Pretendard (OFL)'].map((t) => `<span class="badge">${t}</span>`).join('')}</div>
            <p class="muted" style="font-size:12.5px;margin-top:12px">라이브러리는 MIT·BSD, 글꼴은 SIL Open Font License 1.1 입니다 (web/fonts/).</p></div></div>
        </div>`;
      $('#about-gh').onclick = () => backend.call('window_open_url', { url: cr.repo || 'https://github.com/TETO-IS-KAWAI/projectbaseresearch' });
    },
    enter() {
      const cv = $('#about-canvas');
      if (this.field) { this.field.destroy(); }
      requestAnimationFrame(() => {
        const W = cv.clientWidth, H = cv.clientHeight;
        const fs = Math.min(170, W * 0.22), cell = Math.max(5, Math.round(fs / 22));
        const smp = RT.sampleText('RWA', `700 ${fs}px Geist, sans-serif`, cell, { threshold: 0.4 });
        const f = new RT.PixelField(cv, { cell, gap: 1, hot: 0.08, repel: 90, force: 1.5, spring: 0.06, damp: 0.84, shockOnClick: true });
        f.setTargets(smp, Math.round((W - smp.box.w) / 2 - smp.box.x), Math.round((H - smp.box.h) / 2 - smp.box.y - 12), [cssVar('--text'), cssVar('--accent')]);
        f.assemble({ from: 'below', dur: 1.1 });
        this.field = f;
      });
    },
    leave() { if (this.field) { this.field.destroy(); this.field = null; } },
  };

  RT.pages = pages;
})(window.RT);
