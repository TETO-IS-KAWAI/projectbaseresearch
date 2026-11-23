/* pixel.js — 픽셀 이펙트
   · PixelField : 글자를 픽셀 입자로 쪼개서 모이기 / 흩어지기 / 마우스로 밀어내기
   · PixelTitle : 페이지 제목이 들어올 때 픽셀로 조립되고, 마우스를 대면 흩어진다
   · splash     : 시작 화면 (전파 잡음 → 'HI 21cm' 조립 → 흩어지며 앱 등장)
   · fx         : 화면 전체 이펙트 레이어 (토스트 소멸 등)
   · PixelLoader / PixelWave : 실행 버튼 로딩, 빈 화면 그림                    */
'use strict';
(function (RT) {
  const { clamp, lerp, fitCanvas, cssVar, motionOK } = RT;
  const rand = (a = 0, b = 1) => a + Math.random() * (b - a);

  /** 텍스트를 cell 크기 격자로 샘플링 → 채워진 칸 좌표 목록
   *  opts.letterSpacing : CSS 자간(px 문자열). DOM 글자와 폭을 맞추려면 반드시 같이 줘야 한다.
   *  opts.threshold     : 칸을 채울 덮임 비율. 0.5 면 원래 글자와 획 굵기(면적)가 같다.     */
  function sampleText(text, font, cell, opts = {}) {
    const ls = opts.letterSpacing && opts.letterSpacing !== 'normal' ? opts.letterSpacing : '0px';
    const meas = document.createElement('canvas').getContext('2d');
    meas.font = font; if ('letterSpacing' in meas) meas.letterSpacing = ls;
    const m = meas.measureText(text);
    const px = parseFloat((font.match(/([\d.]+)px/) || [0, 16])[1]);   // 글꼴 크기 (굵기 숫자 말고)
    const asc = Number.isFinite(m.actualBoundingBoxAscent) ? m.actualBoundingBoxAscent : px * 0.8;
    const desc = Number.isFinite(m.actualBoundingBoxDescent) ? Math.max(0, m.actualBoundingBoxDescent) : px * 0.2;
    const fAsc = m.fontBoundingBoxAscent ?? px * 0.93, fDesc = m.fontBoundingBoxDescent ?? px * 0.24;
    const w = Math.ceil(m.width + 4 + Math.abs(parseFloat(ls) || 0) * text.length), h = Math.ceil(asc + desc + 4);
    const gw = Math.ceil(w / cell), gh = Math.ceil(h / cell);
    // 2배 해상도로 그린 뒤 칸마다 덮임 비율을 직접 평균 (축소 보간에 맡기지 않음)
    const SS = 2, c = document.createElement('canvas');
    c.width = gw * cell * SS; c.height = gh * cell * SS;
    const ctx = c.getContext('2d');
    ctx.scale(SS, SS);
    ctx.font = font; if ('letterSpacing' in ctx) ctx.letterSpacing = ls;
    ctx.fillStyle = '#000'; ctx.textBaseline = 'alphabetic';
    ctx.fillText(text, 2, asc + 2);
    const data = ctx.getImageData(0, 0, c.width, c.height).data, CW = c.width;
    const th = opts.threshold ?? 0.38, blk = cell * SS, norm = 255 * blk * blk;
    const pts = [];
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (let gy = 0; gy < gh; gy++) for (let gx = 0; gx < gw; gx++) {
      let sum = 0;
      for (let yy = gy * blk; yy < (gy + 1) * blk; yy++) {
        let k = (yy * CW + gx * blk) * 4 + 3;
        for (let xx = 0; xx < blk; xx++, k += 4) sum += data[k];
      }
      const a = sum / norm;
      if (a > th) {
        pts.push([gx * cell, gy * cell, a]);
        x0 = Math.min(x0, gx * cell); y0 = Math.min(y0, gy * cell); x1 = Math.max(x1, (gx + 1) * cell); y1 = Math.max(y1, (gy + 1) * cell);
      }
    }
    // box: 실제 채워진 칸의 경계 (가운데 맞춤용) · baseline: 샘플 안 기준선 y · originX: 글자 시작 x
    return { pts, w: gw * cell, h: gh * cell, asc: asc + 2, baseline: asc + 2, originX: 2, fAsc, fDesc,
             box: pts.length ? { x: x0, y: y0, w: x1 - x0, h: y1 - y0 } : { x: 0, y: 0, w: 0, h: 0 } };
  }

  class PixelField {
    constructor(canvas, opts = {}) {
      this.c = canvas; this.o = Object.assign({ cell: 4, gap: 1, hot: 0.05, repel: 70, force: 1, spring: 0.09, damp: 0.78 }, opts);
      this.ps = []; this.mouse = null; this.running = false; this.settled = true; this.t0 = performance.now();
      this.onSettle = null; this._raf = 0; this.alpha = 1;
      if (opts.interactive !== false) this._bindPointer();
    }
    _bindPointer() {
      const tgt = this.o.pointerTarget || this.c;
      this._pm = (e) => {
        const r = this.c.getBoundingClientRect();
        this.mouse = { x: e.clientX - r.left, y: e.clientY - r.top, t: performance.now() };
        this.kick();
      };
      this._pl = () => { this.mouse = null; this.kick(); };
      tgt.addEventListener('pointermove', this._pm, { passive: true });
      tgt.addEventListener('pointerleave', this._pl);
      this._pd = (e) => {
        if (!this.o.shockOnClick) return;
        const r = this.c.getBoundingClientRect(); this.shock(e.clientX - r.left, e.clientY - r.top);
      };
      tgt.addEventListener('pointerdown', this._pd);
    }
    destroy() {
      cancelAnimationFrame(this._raf); this.running = false;
      const tgt = this.o.pointerTarget || this.c;
      tgt.removeEventListener('pointermove', this._pm); tgt.removeEventListener('pointerleave', this._pl);
      tgt.removeEventListener('pointerdown', this._pd);
    }
    /** 칸 좌표(home) 설정. ox,oy = 캔버스 안 배치 위치 */
    setTargets(sample, ox, oy, colors) {
      const cell = this.o.cell;
      this.ps = sample.pts.map(([x, y, a]) => ({
        hx: ox + x, hy: oy + y, x: ox + x, y: oy + y, vx: 0, vy: 0, a: 1, cov: a,
        hot: Math.random() < this.o.hot, delay: 0, life: 1, ph: Math.random() * 6.28,
      }));
      this.cell = cell; this.colors = colors;
    }
    assemble({ from = 'noise', dur = 0.9, spread = 1 } = {}) {
      const W = this.c.clientWidth, H = this.c.clientHeight;
      const maxX = Math.max(...this.ps.map((p) => p.hx), 1);
      for (const p of this.ps) {
        if (from === 'noise') { p.x = rand(0, W); p.y = rand(0, H); }
        else if (from === 'scatter') { p.x = p.hx + rand(-60, 60) * spread; p.y = p.hy + rand(-36, 36) * spread; }
        else if (from === 'below') { p.x = p.hx + rand(-20, 20); p.y = H + rand(0, 60); }
        p.vx = p.vy = 0; p.a = 0; p.mode = 'home';
        p.delay = (p.hx / maxX) * dur * 0.55 + rand(0, dur * 0.35);
      }
      this.t0 = performance.now(); this.kick();
    }
    disperse({ dur = 0.7, dir = 'out', power = 1 } = {}) {
      const W = this.c.clientWidth, H = this.c.clientHeight;
      const cx = W / 2, cy = H / 2;
      const maxX = Math.max(...this.ps.map((p) => p.hx), 1);
      for (const p of this.ps) {
        p.mode = 'fly';
        const ang = dir === 'up' ? rand(-Math.PI * 0.8, -Math.PI * 0.2) : Math.atan2(p.y - cy, p.x - cx) + rand(-0.6, 0.6);
        const sp = rand(2, 9) * power;
        p.vx = Math.cos(ang) * sp; p.vy = Math.sin(ang) * sp;
        p.delay = (p.hx / maxX) * dur * 0.5 + rand(0, 0.12);
        p.life = 1;
      }
      this.t0 = performance.now(); this.kick();
    }
    shock(x, y) {
      for (const p of this.ps) {
        const dx = p.x - x, dy = p.y - y, d = Math.hypot(dx, dy) + 1;
        const f = 2600 / (d * d + 400) * 8;
        p.vx += (dx / d) * f; p.vy += (dy / d) * f;
      }
      this.kick();
    }
    kick() { if (!this.running) { this.running = true; this._last = performance.now(); this._raf = requestAnimationFrame((t) => this._tick(t)); } }
    /** 물리 한 스텝 (60fps 기준). 느린 PC 에서는 프레임당 여러 번 돌려 같은 속도를 유지 */
    _step() {
      const o = this.o, m = this.mouse;
      for (const p of this.ps) {
        if (this._t < p.delay) continue;
        if (p.mode === 'fly') {
          p.x += p.vx; p.y += p.vy; p.vx *= 0.97; p.vy *= 0.97; p.vy -= 0.04;
          p.life -= 0.022; p.a = Math.max(0, p.life);
          continue;
        }
        // 스프링 귀환 + 마우스 밀어내기
        let ax = (p.hx - p.x) * o.spring, ay = (p.hy - p.y) * o.spring;
        if (m) {
          const dx = p.x - m.x, dy = p.y - m.y, d2 = dx * dx + dy * dy, R = o.repel;
          if (d2 < R * R) {
            const d = Math.sqrt(d2) + 0.01, f = (1 - d / R) ** 2 * 9 * o.force;
            ax += (dx / d) * f; ay += (dy / d) * f;
          }
        }
        p.vx = (p.vx + ax) * o.damp; p.vy = (p.vy + ay) * o.damp;
        p.x += p.vx; p.y += p.vy;
        p.a = Math.min(1, p.a + 0.08);
      }
    }
    _tick(now) {
      const steps = clamp(Math.round((now - this._last) / 16.67), 1, 5);
      this._last = now;
      this._t = (now - this.t0) / 1000;
      for (let k = 0; k < steps; k++) this._step();
      const { ctx, w, h } = fitCanvas(this.c);
      ctx.clearRect(0, 0, w, h);
      const t = this._t, o = this.o, cell = this.cell, size = Math.max(1, cell - o.gap);
      let moving = 0;
      const m = this.mouse;
      const base = this.colors?.[0] || cssVar('--text'), hot = this.colors?.[1] || cssVar('--accent');
      const buckets = [[], []];
      for (const p of this.ps) {
        if (t < p.delay) {
          moving++;
          if (p.mode === 'home') { if (Math.random() < 0.04) buckets[1].push([p.x, p.y, 0.35]); continue; }
          buckets[p.hot ? 1 : 0].push([p.x, p.y, p.a]); continue;
        }
        if (p.mode === 'fly') {
          if (p.life > 0) { moving++; buckets[p.hot || Math.random() < 0.1 ? 1 : 0].push([p.x, p.y, p.a]); }
          continue;
        }
        const off = Math.abs(p.hx - p.x) + Math.abs(p.hy - p.y);
        if (off > 0.25 || Math.abs(p.vx) + Math.abs(p.vy) > 0.05 || p.a < 1) moving++;
        const disp = Math.min(1, off / 30);
        buckets[p.hot || disp > 0.4 ? 1 : 0].push([p.x, p.y, p.a * (p.hot ? 0.75 + 0.25 * Math.sin(now / 300 + p.ph) : 1)]);
      }
      for (let b = 0; b < 2; b++) {
        ctx.fillStyle = b ? hot : base;
        for (const [x, y, a] of buckets[b]) { ctx.globalAlpha = a * this.alpha; ctx.fillRect(x, y, size, size); }
      }
      ctx.globalAlpha = 1;
      const keep = this.o.alwaysOn || moving > 0 || (m && now - m.t < 400);
      if (keep) this._raf = requestAnimationFrame((tt) => this._tick(tt));
      else { this.running = false; this.onSettle && this.onSettle(); }
    }
  }

  // ─────────── 페이지 제목 ───────────
  // 픽셀은 DOM 글자와 '같은 자리·같은 폭·같은 굵기'로 모이고, 다 모이면 픽셀이 사라지는 동안
  // 진짜 글자가 함께 나타난다(교차 페이드). 즉시 바꿔치기하면 미세한 차이가 튀어 보인다.
  class PixelTitle {
    constructor(h1) {
      this.h = h1; this.field = null; this.canvas = null;
      // 글자만 따로 흐림/투명도를 주려면 캔버스와 분리된 감싸개가 필요하다
      // (h1 에 filter 를 걸면 안에 든 캔버스까지 같이 흐려짐)
      if (!h1.querySelector(':scope > .pt-text')) {
        const span = document.createElement('span');
        span.className = 'pt-text'; span.textContent = h1.textContent.trim();
        h1.textContent = ''; h1.appendChild(span);
      }
      this.t = h1.querySelector(':scope > .pt-text');
      h1.addEventListener('pointerenter', () => this.hover());
    }
    _style() {
      const cs = getComputedStyle(this.h);
      return {
        cs, fs: parseFloat(cs.fontSize),
        font: `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`,
        ls: cs.letterSpacing,
      };
    }
    /** DOM 글자의 기준선·시작점 (h1 기준, 소수점까지). 높이 0 인 인라인 블록을 잠깐 꽂아 잰다
     *  (offsetTop 은 정수로 반올림돼서 1px 가까이 어긋나므로 getBoundingClientRect 를 쓴다) */
    _domOrigin() {
      const mk = document.createElement('span');
      mk.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline;';
      this.t.insertBefore(mk, this.t.firstChild);
      const a = mk.getBoundingClientRect(), b = this.h.getBoundingClientRect();
      mk.remove();
      return { x: a.left - b.left, y: a.top - b.top };
    }
    _mount(pad) {
      this.unmount(false);
      const { cs, font, ls } = this._style();
      const text = this.t.textContent.trim();
      if (document.fonts && !document.fonts.check(font, text)) return null;   // 글꼴 로딩 전이면 효과 생략
      const cell = 2;
      const smp = sampleText(text, font, cell, { letterSpacing: ls, threshold: 0.4 });   // 0.4: 화면 글자의 안티에일리어싱 굵기와 맞춤 (측정값)
      const org = this._domOrigin();
      const c = document.createElement('canvas');
      const r = this.h.getBoundingClientRect();
      const W = Math.max(r.width, smp.w) + pad * 2, H = r.height + pad * 2;
      Object.assign(c.style, { left: -pad + 'px', top: -pad + 'px', width: W + 'px', height: H + 'px' });
      this.h.appendChild(c);
      const f = new PixelField(c, { cell, gap: 0, hot: 0.02, repel: 46, spring: 0.12, damp: 0.74, pointerTarget: this.h });
      f.setTargets(smp, pad + org.x - smp.originX, pad + org.y - smp.baseline, [cs.color.startsWith('rgba(0, 0, 0, 0') ? cssVar('--text') : cssVar('--text'), cssVar('--accent')]);
      this.canvas = c; this.field = f;
      this.h.classList.add('px-hide');
      f.onSettle = () => this.unmount(true);
      return f;
    }
    /** fade=true: 픽셀은 흐려지며 녹아 없어지고, 진짜 글자는 흐린 상태에서 또렷해지며 나타난다 */
    unmount(fade) {
      if (this.field) this.field.destroy();
      const c = this.canvas;
      this.field = this.canvas = null;
      this.h.classList.remove('px-hide');
      if (!c) return;
      if (fade && motionOK()) {
        c.classList.remove('px-quick');
        c.classList.add('px-out');
        setTimeout(() => c.remove(), 760);
      } else c.remove();
    }
    enter() {
      if (!motionOK() || !this.h.offsetWidth) return;
      const f = this._mount(60);
      if (f) f.assemble({ from: 'scatter', dur: 0.75, spread: 1.4 });
    }
    hover() {
      if (!motionOK() || this.field || !this.h.offsetWidth) return;
      const f = this._mount(60);
      if (!f) return;
      for (const p of f.ps) p.a = 1;
      // 마우스를 댈 때도 글자 → 픽셀을 짧게 교차 (글자는 살짝 흐려지며 빠짐)
      const c = this.canvas;
      c.classList.add('px-quick', 'px-out');
      requestAnimationFrame(() => requestAnimationFrame(() => c.classList.remove('px-out')));
      f.kick();
    }
  }

  // ─────────── 화면 전체 이펙트 레이어 ───────────
  const fx = {
    parts: [], running: false,
    burstRect(rect, color, cell = 4, opts = {}) {
      if (!motionOK()) return;
      for (let y = rect.top; y < rect.bottom; y += cell) for (let x = rect.left; x < rect.right; x += cell) {
        if (opts.round) {
          const rr = rect.height / 2;
          const cx = clamp(x, rect.left + rr, rect.right - rr);
          if (Math.hypot(x - cx, y - (rect.top + rr)) > rr) continue;
        }
        if (Math.random() > (opts.density ?? 0.55)) continue;
        this.parts.push({ x, y, vx: rand(-1.2, 1.2), vy: rand(-2.6, -0.2), life: rand(0.6, 1), size: cell - 1, color: Math.random() < 0.18 ? cssVar('--accent') : color, delay: (x - rect.left) / (rect.width || 1) * 0.15 });
      }
      this.kick();
    },
    burstPoints(pts, color, n = 10) {   // pts: [{x,y}] 화면 좌표
      if (!motionOK()) return;
      for (const q of pts) for (let i = 0; i < n; i++) {
        const a = rand(0, 6.28), s = rand(0.6, 3.2);
        this.parts.push({ x: q.x, y: q.y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: rand(0.5, 1), size: 2, color: q.color || color, delay: rand(0, 0.08) });
      }
      this.kick();
    },
    kick() { if (!this.running) { this.running = true; this._last = performance.now(); requestAnimationFrame((t) => this.tick(t)); } },
    tick(now) {
      const cv = document.getElementById('fx-layer');
      const { ctx, w, h } = fitCanvas(cv);
      ctx.clearRect(0, 0, w, h);
      const steps = clamp(Math.round((now - this._last) / 16.67), 1, 5); this._last = now;
      const dt = 1 / 60;
      for (let k = 0; k < steps; k++) for (const p of this.parts) {
        if (p.delay > 0) { p.delay -= dt; continue; }
        p.x += p.vx; p.y += p.vy; p.vx *= 0.96; p.vy = p.vy * 0.96 - 0.03; p.life -= 0.028;
      }
      this.parts = this.parts.filter((p) => p.life > 0);
      for (const p of this.parts) {
        ctx.globalAlpha = p.delay > 0 ? 1 : Math.max(0, p.life); ctx.fillStyle = p.color; ctx.fillRect(p.x, p.y, p.size, p.size);
      }
      ctx.globalAlpha = 1;
      if (this.parts.length) requestAnimationFrame((t) => this.tick(t)); else { this.running = false; ctx.clearRect(0, 0, w, h); }
    },
  };
  RT.pixelBurstFromElement = (elm) => {
    const r = elm.getBoundingClientRect();
    fx.burstRect(r, getComputedStyle(elm).backgroundColor, 4, { round: true, density: 0.5 });
  };

  // ─────────── 스플래시 ───────────
  async function splash({ fast = false } = {}) {
    const box = document.getElementById('splash');
    const cv = document.getElementById('splash-canvas');
    if (!motionOK() || fast) { box.classList.add('gone'); return; }
    try { await Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 900))]); } catch (_) { }
    const W = cv.clientWidth, H = cv.clientHeight;
    const fs = Math.round(clamp(W * 0.15, 90, 190));
    const cell = Math.max(5, Math.round(fs / 26));
    const smp = sampleText('HI 21cm', `650 ${fs}px Geist, 'Pretendard Variable', sans-serif`, cell, { threshold: 0.42 });
    const f = new PixelField(cv, { cell, gap: 1, hot: 0.07, repel: 110, force: 1.4, spring: 0.075, damp: 0.8, alwaysOn: true });
    f.setTargets(smp, Math.round((W - smp.box.w) / 2 - smp.box.x), Math.round((H - smp.box.h) / 2 - smp.box.y - 30), [cssVar('--text'), cssVar('--accent')]);
    f.assemble({ from: 'noise', dur: 1.0 });
    // 부제: 숫자 디코딩 효과
    const sub = document.getElementById('splash-sub');
    const final = sub.textContent; const glyphs = '0123456789.·∙';
    const t0 = performance.now();
    const dec = () => {
      const k = clamp((performance.now() - t0) / 1100, 0, 1);
      sub.textContent = final.split('').map((ch, i) => (i / final.length < k || ch === ' ' ? ch : glyphs[(Math.random() * glyphs.length) | 0])).join('');
      if (k < 1) requestAnimationFrame(dec);
    };
    dec();
    let skip;
    const skipped = new Promise((r) => { skip = r; });
    const onSkip = () => skip();
    box.addEventListener('pointerdown', onSkip); window.addEventListener('keydown', onSkip, { once: true });
    await Promise.race([new Promise((r) => setTimeout(r, 2100)), skipped]);
    f.disperse({ dur: 0.5, power: 1.6 });
    await new Promise((r) => setTimeout(r, 260));
    box.classList.add('gone');
    setTimeout(() => { f.destroy(); }, 900);
  }

  // ─────────── 실행 버튼 로딩 ───────────
  class PixelLoader {
    constructor(host) {
      this.c = document.createElement('canvas'); this.c.className = 'run-pixels'; host.appendChild(this.c);
      this.on = true; this.t0 = performance.now(); this.progress = 0;
      requestAnimationFrame((t) => this.tick(t));
    }
    tick(now) {
      if (!this.on) return;
      const { ctx, w, h } = fitCanvas(this.c);
      ctx.clearRect(0, 0, w, h);
      const cell = 4, cols = Math.ceil(w / cell), rows = Math.ceil(h / cell);
      const t = (now - this.t0) / 1000;
      const col = cssVar('--invert'), acc = cssVar('--accent');
      const front = this.progress * cols;
      for (let x = 0; x < cols; x++) for (let y = 0; y < rows; y++) {
        const wave = Math.sin(x * 0.35 - t * 9 + Math.sin(y * 0.9 + t * 3) * 0.8);
        const done = x < front;
        if (!done && wave < 0.82) continue;
        ctx.globalAlpha = done ? (0.18 + 0.12 * Math.sin(t * 6 + x * 0.3 + y)) : (wave - 0.82) * 4;
        ctx.fillStyle = done ? acc : col;
        ctx.fillRect(x * cell, y * cell, cell - 1, cell - 1);
      }
      ctx.globalAlpha = 1;
      requestAnimationFrame((tt) => this.tick(tt));
    }
    set(p) { this.progress = clamp(p, 0, 1); }
    stop() {
      this.on = false;
      const r = this.c.getBoundingClientRect();
      fx.burstRect(r, cssVar('--accent'), 4, { density: 0.25 });
      this.c.remove();
    }
  }

  // ─────────── 빈 화면 그림: 픽셀 스펙트럼 ───────────
  class PixelWave {
    constructor(canvas) { this.c = canvas; this.on = false; }
    start() { if (this.on) return; this.on = true; this.t0 = performance.now(); requestAnimationFrame((t) => this.tick(t)); }
    stop() { this.on = false; }
    tick(now) {
      if (!this.on) return;
      if (!this.c.offsetParent) { requestAnimationFrame((t) => this.tick(t)); return; }
      const { ctx, w, h } = fitCanvas(this.c);
      ctx.clearRect(0, 0, w, h);
      const cell = 5, cols = Math.floor(w / cell), rows = Math.floor(h / cell);
      const t = (now - this.t0) / 1000;
      const mu = cols * (0.5 + 0.18 * Math.sin(t * 0.6));
      const base = cssVar('--line-3'), acc = cssVar('--accent');
      for (let x = 0; x < cols; x++) {
        const g = Math.exp(-0.5 * ((x - mu) / (cols * 0.07)) ** 2);
        const noise = (Math.sin(x * 1.7 + t * 5) + Math.sin(x * 0.63 - t * 3.3)) * 0.06 + Math.random() * 0.05;
        const v = clamp(0.12 + g * 0.75 + noise, 0, 1);
        const n = Math.round(v * rows);
        for (let y = 0; y < n; y++) {
          ctx.globalAlpha = 0.35 + 0.65 * (y / rows);
          ctx.fillStyle = g > 0.25 ? acc : base;
          ctx.fillRect(x * cell, h - (y + 1) * cell, cell - 1, cell - 1);
        }
      }
      ctx.globalAlpha = 1;
      setTimeout(() => requestAnimationFrame((tt) => this.tick(tt)), 50);
    }
  }

  Object.assign(RT, { sampleText, PixelField, PixelTitle, fx, splash, PixelLoader, PixelWave });
})(window.RT);
