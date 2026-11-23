/* chart.js — 스펙트럼용 캔버스 선 그래프
   휠 = x 확대/축소, 드래그 = 이동, 더블클릭 = 원래대로, 마우스 = 십자선 읽기 */
'use strict';
(function (RT) {
  const { clamp, fitCanvas, cssVar, rgba, tip, kvHTML, fmt, tween, ease } = RT;

  function niceStep(span, count) {
    const raw = span / Math.max(1, count);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const n = raw / mag;
    return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
  }
  function ticks(a, b, count) {
    if (!(b > a)) return [a];
    const s = niceStep(b - a, count), out = [];
    for (let v = Math.ceil(a / s) * s; v <= b + s * 1e-9; v += s) out.push(+v.toPrecision(12));
    return out;
  }
  const decimalsFor = (step) => Math.max(0, Math.min(6, -Math.floor(Math.log10(step) + 1e-9)));
  function lowerBound(arr, v) { let lo = 0, hi = arr.length; while (lo < hi) { const m = (lo + hi) >> 1; arr[m] < v ? lo = m + 1 : hi = m; } return lo; }

  class LineChart {
    constructor(host, opts = {}) {
      this.host = host; this.o = opts;
      this.c = document.createElement('canvas'); host.appendChild(this.c);
      this.pad = { l: 58, r: 18, t: 18, b: 36 };
      this.data = null; this.view = null; this.hover = null; this.reveal = 1; this.drag = null;
      new ResizeObserver(() => this.requestDraw()).observe(host);
      this._bind();
    }
    requestDraw() {
      if (this._pending) return;
      this._pending = true;
      requestAnimationFrame(() => { this._pending = false; this.draw(); });
    }
    setData(d, { animate = true } = {}) {
      this.data = d;
      const xs = d.series.flatMap((s) => [s.x[0], s.x[s.x.length - 1]]);
      this.full = [Math.min(...xs), Math.max(...xs)];
      this.view = d.view ? [...d.view] : [...this.full];
      if (animate && RT.motionOK()) {
        this.reveal = 0;
        tween(900, (t) => { this.reveal = t; this.draw(); }, ease.inOut);
      } else { this.reveal = 1; this.draw(); }
    }
    clear() { this.data = null; this.draw(); }
    _plot() { const w = this.c.clientWidth, h = this.c.clientHeight, p = this.pad; return { x: p.l, y: p.t, w: w - p.l - p.r, h: h - p.t - p.b }; }
    _yRange() {
      const d = this.data, [x0, x1] = this.view;
      let lo = Infinity, hi = -Infinity;
      for (const s of d.series) {
        const i0 = Math.max(0, lowerBound(s.x, x0) - 1), i1 = Math.min(s.x.length, lowerBound(s.x, x1) + 1);
        for (let i = i0; i < i1; i++) { const v = s.y[i]; if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }
      }
      for (const hl of d.hlines || []) if (Number.isFinite(hl.y)) { lo = Math.min(lo, hl.y); hi = Math.max(hi, hl.y); }
      if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
      if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
      const m = (hi - lo) * 0.09;
      return [lo - m, hi + m];
    }
    draw() {
      const { ctx, w, h } = fitCanvas(this.c);
      ctx.clearRect(0, 0, w, h);
      if (!this.data) return;
      const P = this._plot(), d = this.data, [x0, x1] = this.view, [y0, y1] = this._yRange();
      const X = (v) => P.x + ((v - x0) / (x1 - x0)) * P.w;
      const Y = (v) => P.y + P.h - ((v - y0) / (y1 - y0)) * P.h;
      this._X = X; this._Y = Y; this._yr = [y0, y1];
      const line = cssVar('--line'), muted = cssVar('--muted'), sub = cssVar('--sub');
      const mono = `11px ${cssVar('--mono') || 'monospace'}`;
      ctx.font = mono; ctx.textBaseline = 'middle';

      // 격자 + 눈금
      const xt = ticks(x0, x1, Math.max(3, Math.floor(P.w / 110)));
      const yt = ticks(y0, y1, Math.max(3, Math.floor(P.h / 56)));
      const xd = decimalsFor(xt.length > 1 ? xt[1] - xt[0] : 1), yd = decimalsFor(yt.length > 1 ? yt[1] - yt[0] : 1);
      ctx.strokeStyle = line; ctx.lineWidth = 1;
      ctx.beginPath();
      for (const v of xt) { const x = Math.round(X(v)) + 0.5; ctx.moveTo(x, P.y); ctx.lineTo(x, P.y + P.h); }
      for (const v of yt) { const y = Math.round(Y(v)) + 0.5; ctx.moveTo(P.x, y); ctx.lineTo(P.x + P.w, y); }
      ctx.stroke();
      ctx.fillStyle = muted; ctx.textAlign = 'center';
      for (const v of xt) ctx.fillText(fmt(v, xd), X(v), P.y + P.h + 16);
      ctx.textAlign = 'right';
      for (const v of yt) ctx.fillText(fmt(v, yd), P.x - 8, Y(v));
      // 0 선
      if (y0 < 0 && y1 > 0) { ctx.strokeStyle = cssVar('--line-2'); ctx.beginPath(); ctx.moveTo(P.x, Math.round(Y(0)) + 0.5); ctx.lineTo(P.x + P.w, Math.round(Y(0)) + 0.5); ctx.stroke(); }
      // 축 이름
      ctx.fillStyle = sub; ctx.textAlign = 'right'; ctx.fillText(d.xLabel || '', P.x + P.w, P.y + P.h + 30);
      ctx.save(); ctx.translate(14, P.y + P.h / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'center'; ctx.fillText(d.yLabel || '', 0, 0); ctx.restore();

      // 데이터 (드러나기 애니메이션 = 왼→오 클립)
      ctx.save();
      ctx.beginPath(); ctx.rect(P.x, P.y - 2, P.w * this.reveal, P.h + 4); ctx.clip();
      for (const hl of d.hlines || []) {
        if (!Number.isFinite(hl.y)) continue;
        ctx.strokeStyle = hl.color; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(P.x, Y(hl.y)); ctx.lineTo(P.x + P.w, Y(hl.y)); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = hl.color; ctx.textAlign = 'right'; ctx.fillText(hl.label, P.x + P.w - 6, Y(hl.y) - 9);
      }
      for (const s of d.series) this._series(ctx, s, P, X, Y);
      ctx.restore();

      // 세로 마커 (HI 정지주파수, 검출 피크) — 라벨이 겹치면 아랫줄로
      const rows = [];
      const mks = (d.markers || []).filter((mk) => mk.x >= x0 && mk.x <= x1).sort((a, b) => a.x - b.x);
      for (const mk of mks) {
        const x = Math.round(X(mk.x)) + 0.5;
        ctx.font = `500 10.5px ${cssVar('--mono')}`;
        const tw0 = mk.label ? ctx.measureText(mk.label).width + 10 : 0;
        const bx0 = clamp(x - tw0 / 2, P.x, P.x + P.w - tw0);
        let row = rows.findIndex((r) => bx0 > r + 4); if (row < 0) { row = rows.length; rows.push(0); }
        rows[row] = bx0 + tw0;
        const ly = P.y + row * 18;
        ctx.strokeStyle = mk.color; ctx.globalAlpha = 0.9 * this.reveal; ctx.setLineDash(mk.dash ? [3, 4] : []);
        ctx.beginPath(); ctx.moveTo(x, ly + 14); ctx.lineTo(x, P.y + P.h); ctx.stroke(); ctx.setLineDash([]);
        if (mk.label) {
          ctx.fillStyle = mk.color; ctx.globalAlpha = 0.16 * this.reveal;
          ctx.beginPath(); ctx.roundRect(bx0, ly, tw0, 15, 4); ctx.fill();
          ctx.globalAlpha = this.reveal; ctx.textAlign = 'center'; ctx.fillText(mk.label, bx0 + tw0 / 2, ly + 7.5);
        }
        ctx.font = mono;
        ctx.globalAlpha = 1;
      }

      // 스캔 헤드
      if (this.reveal < 1) {
        const x = P.x + P.w * this.reveal, acc = cssVar('--accent');
        const g = ctx.createLinearGradient(x - 40, 0, x, 0); g.addColorStop(0, rgba(acc, 0)); g.addColorStop(1, rgba(acc, 0.25));
        ctx.fillStyle = g; ctx.fillRect(x - 40, P.y, 40, P.h);
        ctx.fillStyle = acc; ctx.fillRect(x - 1, P.y, 2, P.h);
      }

      // 십자선
      if (this.hover && this.reveal >= 1) {
        const hx = this.hover.x;
        if (hx >= P.x && hx <= P.x + P.w) {
          const xv = x0 + ((hx - P.x) / P.w) * (x1 - x0);
          ctx.strokeStyle = cssVar('--line-3'); ctx.beginPath(); ctx.moveTo(Math.round(hx) + 0.5, P.y); ctx.lineTo(Math.round(hx) + 0.5, P.y + P.h); ctx.stroke();
          const rows = [[d.xLabel, fmt(xv, xd + 2)]];
          for (const s of d.series) {
            const i = clamp(lowerBound(s.x, xv), 0, s.x.length - 1);
            const yv = s.y[i]; if (!Number.isFinite(yv)) continue;
            ctx.fillStyle = cssVar('--surface'); ctx.strokeStyle = s.color; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(X(s.x[i]), Y(yv), 4, 0, 7); ctx.fill(); ctx.stroke(); ctx.lineWidth = 1;
            rows.push([s.name, fmt(yv, 3)]);
          }
          tip.show(kvHTML(rows), this.hover.cx, this.hover.cy);
        }
      }
      // 확대 상태 표시
      const zoomed = this.view[0] > this.full[0] + 1e-9 || this.view[1] < this.full[1] - 1e-9;
      if (zoomed) { ctx.fillStyle = muted; ctx.textAlign = 'left'; ctx.fillText('확대됨 · 더블클릭으로 원래대로', P.x + 8, P.y + P.h - 10); }
    }
    _series(ctx, s, P, X, Y) {
      const [x0, x1] = this.view;
      const i0 = Math.max(0, lowerBound(s.x, x0) - 1), i1 = Math.min(s.x.length, lowerBound(s.x, x1) + 2);
      const n = i1 - i0; if (n < 2) return;
      // 픽셀 열마다 최소/최대만 그리기 (점이 많을 때)
      const pts = [];
      const perPx = n / P.w;
      if (perPx > 2) {
        let col = -1, mn = 0, mx = 0, cx = 0;
        for (let i = i0; i < i1; i++) {
          const x = Math.floor(X(s.x[i])), y = s.y[i]; if (!Number.isFinite(y)) continue;
          if (x !== col) { if (col >= 0) { pts.push([cx, Y(mn)], [cx, Y(mx)]); } col = x; cx = x; mn = mx = y; }
          else { if (y < mn) mn = y; if (y > mx) mx = y; }
        }
        if (col >= 0) pts.push([cx, Y(mn)], [cx, Y(mx)]);
      } else {
        for (let i = i0; i < i1; i++) if (Number.isFinite(s.y[i])) pts.push([X(s.x[i]), Y(s.y[i])]);
      }
      if (pts.length < 2) return;
      if (s.fill) {
        const base = Y(Math.max(this._yr[0], Math.min(0, this._yr[1])));
        const g = ctx.createLinearGradient(0, P.y, 0, P.y + P.h);
        g.addColorStop(0, rgba(s.color, 0.22)); g.addColorStop(1, rgba(s.color, 0));
        ctx.fillStyle = g; ctx.beginPath(); ctx.moveTo(pts[0][0], base);
        for (const [x, y] of pts) ctx.lineTo(x, y);
        ctx.lineTo(pts[pts.length - 1][0], base); ctx.closePath(); ctx.fill();
      }
      ctx.strokeStyle = s.color; ctx.lineWidth = s.width || 1.25; ctx.lineJoin = 'round';
      ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
      for (let k = 1; k < pts.length; k++) ctx.lineTo(pts[k][0], pts[k][1]);
      ctx.stroke(); ctx.lineWidth = 1;
    }
    _bind() {
      const c = this.c;
      c.addEventListener('pointermove', (e) => {
        const r = c.getBoundingClientRect();
        const x = e.clientX - r.left;
        if (this.drag && this.data) {
          const P = this._plot(), span = this.drag.v[1] - this.drag.v[0];
          const dx = ((x - this.drag.x) / P.w) * span;
          let a = this.drag.v[0] - dx, b = this.drag.v[1] - dx;
          if (a < this.full[0]) { b += this.full[0] - a; a = this.full[0]; }
          if (b > this.full[1]) { a -= b - this.full[1]; b = this.full[1]; }
          this.view = [a, b];
        }
        this.hover = { x, cx: e.clientX, cy: e.clientY };
        this.requestDraw();
      });
      c.addEventListener('pointerleave', () => { this.hover = null; tip.hide(); this.requestDraw(); });
      c.addEventListener('pointerdown', (e) => {
        if (!this.data) return;
        c.setPointerCapture(e.pointerId);
        this.drag = { x: e.clientX - c.getBoundingClientRect().left, v: [...this.view] };
        c.style.cursor = 'grabbing';
      });
      const end = () => { this.drag = null; c.style.cursor = ''; };
      c.addEventListener('pointerup', end); c.addEventListener('pointercancel', end);
      c.addEventListener('wheel', (e) => {
        if (!this.data) return;
        e.preventDefault();
        const P = this._plot(), r = c.getBoundingClientRect();
        const fx = clamp((e.clientX - r.left - P.x) / P.w, 0, 1);
        const [a, b] = this.view, xv = a + fx * (b - a);
        const k = Math.exp(e.deltaY * 0.0015);
        const minSpan = (this.full[1] - this.full[0]) / 400;
        let span = clamp((b - a) * k, minSpan, this.full[1] - this.full[0]);
        let na = xv - fx * span, nb = na + span;
        if (na < this.full[0]) { na = this.full[0]; nb = na + span; }
        if (nb > this.full[1]) { nb = this.full[1]; na = nb - span; }
        this.view = [na, nb]; this.requestDraw();
      }, { passive: false });
      c.addEventListener('dblclick', () => {
        if (!this.data) return;
        const from = [...this.view], to = [...this.full];
        tween(380, (t) => { this.view = [RT.lerp(from[0], to[0], t), RT.lerp(from[1], to[1], t)]; this.draw(); });
      });
    }
  }

  RT.LineChart = LineChart;
  RT.niceTicks = ticks;
})(window.RT);
