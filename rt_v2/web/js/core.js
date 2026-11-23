/* core.js — 공용 유틸 · 백엔드 연결 · UI 기본 부품
   (전역 RT 네임스페이스. 파일 하나하나는 classic script 로 읽힌다) */
'use strict';
window.RT = window.RT || {};

(function (RT) {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const D2R = Math.PI / 180, R2D = 180 / Math.PI;
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ease = {
    out: (t) => 1 - Math.pow(1 - t, 3),
    outExpo: (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
    inOut: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
    outBack: (t) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
  };
  const motionOK = () => document.documentElement.dataset.motion !== 'reduce'
    && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function fmt(v, d = 2, opts = {}) {
    if (v === null || v === undefined || !Number.isFinite(+v)) return opts.na ?? '—';
    const s = (+v).toFixed(d);
    return opts.sign && +v > 0 ? '+' + s : s.replace('-', '−');
  }
  function el(tag, attrs = {}, html = '') {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') e.className = v;
      else if (k === 'style') e.style.cssText = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else if (v !== false && v !== null && v !== undefined) e.setAttribute(k, v === true ? '' : v);
    }
    if (html) e.innerHTML = html;
    return e;
  }
  const icon = (name, cls = '') => `<svg class="ic ${cls}"><use href="#i-${name}"/></svg>`;
  const cssVar = (name, elm = document.documentElement) => getComputedStyle(elm).getPropertyValue(name).trim();

  // ─────────── 이벤트 버스 ───────────
  const bus = {
    _h: {},
    on(ev, fn) { (this._h[ev] ||= []).push(fn); return () => this.off(ev, fn); },
    off(ev, fn) { this._h[ev] = (this._h[ev] || []).filter((f) => f !== fn); },
    emit(ev, data) { (this._h[ev] || []).slice().forEach((f) => { try { f(data); } catch (e) { console.error(e); } }); },
  };

  // ─────────── 백엔드 (Qt WebChannel → 없으면 HTTP 개발 서버) ───────────
  const backend = {
    mode: 'none', _obj: null, _seq: 0, _pending: new Map(),
    ready: null,
    init() {
      this.ready = new Promise((resolve) => {
        if (window.qt && window.qt.webChannelTransport && window.QWebChannel) {
          new QWebChannel(qt.webChannelTransport, (ch) => {
            this._obj = ch.objects.backend;
            this._obj.response.connect((rid, json) => this._resolve(rid, json));
            this._obj.event.connect((name, json) => {
              let p = {}; try { p = JSON.parse(json); } catch (_) { }
              bus.emit('backend:' + name, p);
            });
            this.mode = 'qt';
            resolve();
          });
        } else {
          this.mode = location.protocol.startsWith('http') ? 'http' : 'none';
          resolve();
        }
      });
      return this.ready;
    },
    _resolve(rid, json) {
      const p = this._pending.get(rid);
      if (!p) return;
      this._pending.delete(rid);
      let res; try { res = JSON.parse(json); } catch (e) { res = { ok: false, error: 'JSON 파싱 실패' }; }
      res.ok ? p.resolve(res.data) : p.reject(new Error(res.error || '오류'));
    },
    async call(method, args = {}) {
      await this.ready;
      if (this.mode === 'qt') {
        const rid = 'r' + (++this._seq);
        return new Promise((resolve, reject) => {
          this._pending.set(rid, { resolve, reject });
          this._obj.request(rid, method, JSON.stringify(args));
        });
      }
      if (this.mode === 'http') {
        let poll = null;
        if (method === 'run_observation') {
          poll = setInterval(async () => {
            try {
              const ev = await (await fetch('/api/events')).json();
              ev.forEach(([n, p]) => bus.emit('backend:' + n, p));
            } catch (_) { }
          }, 120);
        }
        try {
          const r = await fetch('/api', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ method, args }) });
          const res = await r.json();
          if (!res.ok) throw new Error(res.error || '오류');
          return res.data;
        } finally {
          if (poll) { clearInterval(poll); try { (await (await fetch('/api/events')).json()).forEach(([n, p]) => bus.emit('backend:' + n, p)); } catch (_) { } }
        }
      }
      throw new Error('백엔드에 연결되지 않았습니다');
    },
  };

  // ─────────── 좌표 ───────────
  // ICRS(J2000) → 은하 좌표 회전 행렬
  const M_EQ2GAL = [
    [-0.0548755604162154, -0.8734370902348850, -0.4838350155487132],
    [0.4941094278755837, -0.4448296299600112, 0.7469822444972189],
    [-0.8676661490190047, -0.1980763734312015, 0.4559837761750669],
  ];
  function vec(lon, lat) {
    const a = lon * D2R, b = lat * D2R, cb = Math.cos(b);
    return [cb * Math.cos(a), cb * Math.sin(a), Math.sin(b)];
  }
  function unvec(v) {
    let lon = Math.atan2(v[1], v[0]) * R2D; if (lon < 0) lon += 360;
    return [lon, Math.asin(clamp(v[2], -1, 1)) * R2D];
  }
  function mul(M, v) { return [0, 1, 2].map((i) => M[i][0] * v[0] + M[i][1] * v[1] + M[i][2] * v[2]); }
  function mulT(M, v) { return [0, 1, 2].map((i) => M[0][i] * v[0] + M[1][i] * v[1] + M[2][i] * v[2]); }
  const eq2gal = (ra, dec) => unvec(mul(M_EQ2GAL, vec(ra, dec)));
  const gal2eq = (l, b) => unvec(mulT(M_EQ2GAL, vec(l, b)));

  // 적경/적위 문자열 파서 (python api.parse_ra_deg 와 같은 규칙)
  function parseSexa(s) {
    const t = s.replace(/[hdms°'"′″:]/gi, ' ').trim().split(/\s+/).map(Number);
    if (!t.length || t.some((x) => !Number.isFinite(x))) return NaN;
    const neg = /^\s*-/.test(s);
    const [a, b = 0, c = 0] = t.map(Math.abs);
    return (neg ? -1 : 1) * (a + b / 60 + c / 3600);
  }
  function parseRA(text) {
    const s = String(text).trim(); if (!s) return NaN;
    const low = s.toLowerCase();
    const isHour = low.includes('h') || (s.includes(':') && !low.includes('d'));
    const isSexa = /[hdms:°'"]/i.test(s) || /\s/.test(s);
    let v = isSexa ? parseSexa(s) : Number(s);
    if (!Number.isFinite(v)) return NaN;
    if (isHour) v *= 15;
    return ((v % 360) + 360) % 360;
  }
  function parseDec(text) {
    const s = String(text).trim(); if (!s) return NaN;
    const v = /[dms:°'"]/i.test(s) || /\s/.test(s) ? parseSexa(s) : Number(s);
    return Number.isFinite(v) && Math.abs(v) <= 90 ? v : NaN;
  }
  function raToHMS(deg) {
    const h = ((deg / 15) % 24 + 24) % 24; const H = Math.floor(h); const m = (h - H) * 60; const M = Math.floor(m); const S = (m - M) * 60;
    return `${String(H).padStart(2, '0')}h${String(M).padStart(2, '0')}m${S.toFixed(1).padStart(4, '0')}s`;
  }
  function decToDMS(deg) {
    const sgn = deg < 0 ? '−' : '+'; const a = Math.abs(deg); const D = Math.floor(a); const m = (a - D) * 60; const M = Math.floor(m); const S = (m - M) * 60;
    return `${sgn}${String(D).padStart(2, '0')}°${String(M).padStart(2, '0')}′${S.toFixed(0).padStart(2, '0')}″`;
  }
  // 지방항성시 → 천정 적경 [deg]
  function zenithRA(date, lonDeg) {
    const jd = date.getTime() / 86400000 + 2440587.5;
    const gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0);
    return (((gmst + lonDeg) % 360) + 360) % 360;
  }

  // HEALPix RING ang2pix (theta = 여위도, phi = 경도) — healpix_base 알고리즘
  function ang2pixRing(nside, theta, phi) {
    const z = Math.cos(theta), za = Math.abs(z);
    const TWOPI = 2 * Math.PI;
    let tt = (((phi % TWOPI) + TWOPI) % TWOPI) / (Math.PI / 2); // [0,4)
    const ncap = 2 * nside * (nside - 1), npix = 12 * nside * nside;
    if (za <= 2 / 3) {
      const t1 = nside * (0.5 + tt), t2 = nside * z * 0.75;
      const jp = Math.floor(t1 - t2), jm = Math.floor(t1 + t2);
      const ir = nside + 1 + jp - jm;
      const kshift = 1 - (ir & 1);
      let ip = Math.floor((jp + jm - nside + kshift + 1) / 2);
      ip = ((ip % (4 * nside)) + 4 * nside) % (4 * nside);
      return ncap + (ir - 1) * 4 * nside + ip;
    }
    const tp = tt - Math.floor(tt);
    const tmp = nside * Math.sqrt(3 * (1 - za));
    const jp = Math.floor(tp * tmp), jm = Math.floor((1 - tp) * tmp);
    const ir = jp + jm + 1;
    let ip = Math.floor(tt * ir);
    ip = ((ip % (4 * ir)) + 4 * ir) % (4 * ir);
    return z > 0 ? 2 * ir * (ir - 1) + ip : npix - 2 * ir * (ir + 1) + ip;
  }
  const radecToPix = (nside, ra, dec) => ang2pixRing(nside, (90 - dec) * D2R, ra * D2R);

  function b64f32(b64) {
    const bin = atob(b64); const n = bin.length; const u8 = new Uint8Array(n);
    for (let i = 0; i < n; i++) u8[i] = bin.charCodeAt(i);
    return new Float32Array(u8.buffer);
  }

  // ─────────── 색 ───────────
  function hexToRgb(h) {
    h = h.replace('#', ''); if (h.length === 3) h = h.split('').map((c) => c + c).join('');
    const n = parseInt(h, 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const rgba = (hex, a) => { const [r, g, b] = hexToRgb(hex); return `rgba(${r},${g},${b},${a})`; };
  // 수소선 팔레트: 깊은 남색 → 청록 → 민트 → 상아
  const CMAP_HI = ['#0b0d2a', '#1b1f5e', '#2a3a8f', '#1f6fa8', '#17a2a8', '#3fd1a0', '#a8ef8e', '#fff6c8'];
  function cmap(t, stops = CMAP_HI) {
    t = clamp(t, 0, 1) * (stops.length - 1);
    const i = Math.min(Math.floor(t), stops.length - 2), f = t - i;
    const a = hexToRgb(stops[i]), b = hexToRgb(stops[i + 1]);
    return [Math.round(lerp(a[0], b[0], f)), Math.round(lerp(a[1], b[1], f)), Math.round(lerp(a[2], b[2], f))];
  }
  const cmapCss = (t, stops) => { const c = cmap(t, stops); return `rgb(${c[0]},${c[1]},${c[2]})`; };
  const cmapGradient = (stops = CMAP_HI) => `linear-gradient(90deg, ${stops.join(', ')})`;
  const ARM_COLORS = { 'Norma': '--c-norma', 'Scutum-Crux': '--c-scutum', 'Sagittarius': '--c-sgr', 'Orion (Local)': '--c-local', 'Perseus': '--c-perseus', 'Outer': '--c-outer' };
  const ARM_KO = { 'Norma': '직각자자리 팔', 'Scutum-Crux': '방패-남십자 팔', 'Sagittarius': '궁수 팔', 'Orion (Local)': '오리온(국부) 팔', 'Perseus': '페르세우스 팔', 'Outer': '바깥 팔' };
  const armColor = (name) => cssVar(ARM_COLORS[name] || '--accent');
  // 추론된 팔: 문헌 팔과 섞이지 않는 별도 팔레트
  const FIT_COLORS = ['#5af0c4', '#ff7eb6', '#ffb86b', '#7aa2ff', '#e5f27a', '#c792ff'];

  // ─────────── 애니메이션 ───────────
  function tween(dur, fn, easing = ease.out) {
    return new Promise((resolve) => {
      if (!motionOK()) { fn(1); resolve(); return; }
      const t0 = performance.now();
      const step = (now) => {
        const t = clamp((now - t0) / dur, 0, 1);
        fn(easing(t));
        t < 1 ? requestAnimationFrame(step) : resolve();
      };
      requestAnimationFrame(step);
    });
  }
  // 숫자 카운트업 + 자릿수 스크램블
  function countUp(node, value, digits = 2, opts = {}) {
    const target = +value;
    if (!Number.isFinite(target)) { node.textContent = '—'; node.classList.add('na'); return; }
    node.classList.remove('na');
    const from = Number.isFinite(+node.dataset.v) ? +node.dataset.v : 0;
    node.dataset.v = target;
    const unit = opts.unit ? `<small>${opts.unit}</small>` : '';
    tween(opts.dur || 900, (t) => {
      const v = lerp(from, target, t);
      node.innerHTML = fmt(v, digits, opts) + unit;
    }, ease.outExpo);
  }

  // ─────────── 세그먼트 컨트롤 (움직이는 썸) ───────────
  function segmented(root, onChange) {
    const thumb = el('span', { class: 'seg-thumb' });
    root.prepend(thumb);
    const btns = $$('button', root);
    const place = (animate = true) => {
      const a = btns.find((b) => b.classList.contains('active')) || btns[0];
      if (!a || !a.offsetWidth) return;
      if (!animate) thumb.style.transition = 'none';
      thumb.style.width = a.offsetWidth + 'px';
      thumb.style.transform = `translateX(${a.offsetLeft}px)`;
      if (!animate) { thumb.offsetWidth; thumb.style.transition = ''; }
    };
    btns.forEach((b) => b.addEventListener('click', () => {
      if (b.classList.contains('active')) return;
      btns.forEach((x) => x.classList.toggle('active', x === b));
      place(); onChange && onChange(b.dataset.v);
    }));
    new ResizeObserver(() => place(false)).observe(root);
    requestAnimationFrame(() => place(false));
    return {
      get value() { return (btns.find((b) => b.classList.contains('active')) || {}).dataset?.v; },
      set(v, fire = false) {
        const b = btns.find((x) => x.dataset.v === v); if (!b) return;
        btns.forEach((x) => x.classList.toggle('active', x === b)); place();
        if (fire && onChange) onChange(v);
      },
      relayout: () => place(false),
    };
  }

  function bindRange(input, out, format) {
    const upd = () => {
      const p = ((input.value - input.min) / (input.max - input.min)) * 100;
      input.style.setProperty('--p', p + '%');
      if (out) out.textContent = format ? format(+input.value) : input.value;
    };
    input.addEventListener('input', upd); upd();
    return upd;
  }

  // ─────────── 토스트 ───────────
  function toast(msg, kind = 'ok', opts = {}) {
    const box = $('#toasts');
    const ic = kind === 'err' ? 'x' : kind === 'warn' ? 'alert' : 'check';
    const t = el('div', { class: `toast ${kind}` }, `<span class="t-icon">${icon(ic)}</span><span>${esc(msg)}</span>`);
    if (opts.action) {
      const a = el('span', { class: 't-action' }, esc(opts.action.label));
      a.addEventListener('click', () => { opts.action.run(); close(); });
      t.appendChild(a);
    }
    box.appendChild(t);
    while (box.children.length > 3) box.firstChild.remove();
    let closed = false;
    const close = () => {
      if (closed) return; closed = true;
      if (RT.pixelBurstFromElement) RT.pixelBurstFromElement(t);
      t.classList.add('out'); setTimeout(() => t.remove(), 360);
    };
    setTimeout(close, opts.ms || (kind === 'err' ? 5200 : 2800));
    return close;
  }

  // ─────────── 모달 ───────────
  function modal({ title, body = '', confirm = '확인', cancel = '취소', danger = false, input = null, onOpen }) {
    return new Promise((resolve) => {
      const back = $('#modal'), box = $('#modal-box');
      box.innerHTML = `<div class="modal-body"><h3>${esc(title)}</h3>${body ? `<p>${body}</p>` : ''}
        ${input ? `<div class="field"><label>${esc(input.label || '')}</label><input id="modal-input" value="${esc(input.value || '')}" placeholder="${esc(input.placeholder || '')}" spellcheck="false" autocomplete="off"></div>` : ''}
        </div><div class="modal-foot">${cancel ? `<button class="btn btn-ghost" data-r="0">${esc(cancel)}</button>` : ''}
        <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-r="1">${esc(confirm)}</button></div>`;
      back.hidden = false;
      const inp = $('#modal-input', box);
      const done = (ok) => {
        back.hidden = true; document.removeEventListener('keydown', key, true);
        resolve(ok ? (input ? inp.value : true) : (input ? null : false));
      };
      const key = (e) => {
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(false); }
        if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); done(true); }
      };
      document.addEventListener('keydown', key, true);
      $$('button', box).forEach((b) => b.addEventListener('click', () => done(b.dataset.r === '1')));
      back.onclick = (e) => { if (e.target === back) done(false); };
      setTimeout(() => { (inp || $('[data-r="1"]', box)).focus(); inp && inp.select(); onOpen && onOpen(box); }, 30);
    });
  }

  // ─────────── 툴팁 ───────────
  const tip = {
    show(html, x, y) {
      const t = $('#tooltip'); t.innerHTML = html; t.hidden = false;
      const r = t.getBoundingClientRect();
      let left = x + 14, top = y + 14;
      if (left + r.width > innerWidth - 8) left = x - r.width - 14;
      if (top + r.height > innerHeight - 8) top = y - r.height - 14;
      t.style.left = left + 'px'; t.style.top = top + 'px';
    },
    hide() { $('#tooltip').hidden = true; },
  };
  const kvHTML = (rows) => `<div class="kv">${rows.map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('')}</div>`;

  // ─────────── 카드 스포트라이트 ───────────
  document.addEventListener('pointermove', (e) => {
    const c = e.target.closest && e.target.closest('.card.spot');
    if (!c) return;
    const r = c.getBoundingClientRect();
    c.style.setProperty('--mx', e.clientX - r.left + 'px');
    c.style.setProperty('--my', e.clientY - r.top + 'px');
  }, { passive: true });

  // 캔버스 HiDPI 맞춤
  function fitCanvas(canvas) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w, h, dpr };
  }

  Object.assign(RT, {
    $, $$, clamp, lerp, D2R, R2D, esc, ease, fmt, el, icon, cssVar, motionOK,
    bus, backend, eq2gal, gal2eq, parseRA, parseDec, raToHMS, decToDMS, zenithRA,
    ang2pixRing, radecToPix, b64f32, hexToRgb, rgba, cmap, cmapCss, cmapGradient, CMAP_HI,
    ARM_COLORS, ARM_KO, armColor, FIT_COLORS, tween, countUp, segmented, bindRange,
    toast, modal, tip, kvHTML, fitCanvas,
  });
})(window.RT);
