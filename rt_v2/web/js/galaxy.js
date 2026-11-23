/* galaxy.js — 은하 조감도 (태양 원점, kpc)
   세계 좌표: +Y = 태양→은하 중심, +X = l=90° (spiral_arm.py 규약)
   화면: 은하 중심이 위.  '북은하극' 보기에서는 l=90° 가 왼쪽 (IAU 관례)        */
'use strict';
(function (RT) {
  const { clamp, lerp, fitCanvas, cssVar, rgba, tween, ease, D2R, R2D, FIT_COLORS, armColor } = RT;

  class GalaxyMap {
    constructor(canvas, opts = {}) {
      this.c = canvas; this.o = opts;
      this.R0 = 8.15;
      this.mode = 'infer';
      this.opts = { alt: true, excl: true, band: false, sight: true, view: 'ngp' };
      this.infer = null; this.model = null;
      this.armOff = new Set(); this.modelOff = new Set();
      this.view = { x: 0, y: 4.2, s: 1 }; this._target = null;
      this.armProg = 1; this.modelProg = 1; this.sweep = 1;
      this.hover = null; this.selected = null; this.highlightArm = null;
      this.fade = 1;            // 등장 애니메이션: 배경·팔 전체 불투명도
      this._ver = 0;            // 데이터가 바뀔 때마다 +1 (정적 레이어 캐시 키)
      new ResizeObserver(() => this.requestDraw()).observe(canvas);
      this._bind();
    }
    get mirror() { return this.opts.view === 'ngp' ? -1 : 1; }
    _base() {
      const w = this.c.clientWidth, h = this.c.clientHeight, right = this.o.rightInset || 0;
      return { w, h, cx: (w - right) / 2 + 20, cy: h / 2 + 30, k: Math.min(w - right - 60, h - 110) / 31 };
    }
    toScreen(x, y) {
      const B = this._base(), s = B.k * this.view.s;
      return [B.cx + this.mirror * (x - this.view.x) * s, B.cy - (y - this.view.y) * s];
    }
    toWorld(sx, sy) {
      const B = this._base(), s = B.k * this.view.s;
      return [this.mirror * (sx - B.cx) / s + this.view.x, -(sy - B.cy) / s + this.view.y];
    }
    get scale() { return this._base().k * this.view.s; }

    /** 그리기는 한 프레임에 한 번만 (마우스 이벤트가 프레임당 여러 번 와도) */
    requestDraw() {
      if (this._pending) return;
      this._pending = true;
      requestAnimationFrame(() => { this._pending = false; this.draw(); });
    }
    setInfer(res, animate = true) {
      this.infer = res; this._ver++;
      if (animate && RT.motionOK()) {
        this.sweep = 0; this.armProg = 0;
        tween(1100, (t) => { this.sweep = t; this.requestDraw(); }, ease.inOut)
          .then(() => tween(1100, (t) => { this.armProg = t; this.requestDraw(); }, ease.out));
      } else { this.sweep = 1; this.armProg = 1; this.requestDraw(); }
    }
    setModel(m, animate = true) {
      this.model = m; this._ver++;
      if (animate && RT.motionOK()) { this.modelProg = 0; tween(1300, (t) => { this.modelProg = t; this.requestDraw(); }, ease.out); }
      else { this.modelProg = 1; this.requestDraw(); }
    }
    setMode(m) {
      const prev = this.mode; this.mode = m;
      if (m !== 'infer' && prev === 'infer' && this.model) this.setModel(this.model, true);
      else if (m !== 'model' && prev === 'model' && this.infer) { this.armProg = 0; tween(900, (t) => { this.armProg = t; this.requestDraw(); }); }
      this.requestDraw();
    }
    /** 페이지에 들어올 때마다: 살짝 멀리서 다가오며 나타나고 → 레이더가 돌며 점이 찍히고 → 팔이 그려진다 */
    hide() { this._introRun = (this._introRun || 0) + 1; this.fade = 0; this.requestDraw(); }
    intro() {
      if (!RT.motionOK()) { this.fade = 1; this.sweep = this.armProg = this.modelProg = 1; this.requestDraw(); return; }
      const run = (this._introRun = (this._introRun || 0) + 1);
      const to = { x: 0, y: 4.2, s: 1 }, from = { x: 0, y: 5.4, s: 0.78 };
      this.fade = 0; this.sweep = 0; this.armProg = 0; this.modelProg = 0;
      tween(950, (t) => {
        if (run !== this._introRun) return;
        this.fade = t; this.view = { x: lerp(from.x, to.x, t), y: lerp(from.y, to.y, t), s: lerp(from.s, to.s, t) };
        this.modelProg = t; this.requestDraw();
      }, ease.outExpo);
      tween(1150, (t) => { if (run === this._introRun) { this.sweep = t; this.requestDraw(); } }, ease.inOut)
        .then(() => tween(900, (t) => { if (run === this._introRun) { this.armProg = t; this.requestDraw(); } }, ease.out));
    }
    zoom(f, sx, sy) {
      const B = this._base(); sx ??= B.cx; sy ??= B.cy;
      const [wx, wy] = this.toWorld(sx, sy);
      const ns = clamp(this.view.s * f, 0.45, 12);
      const from = { ...this.view };
      // 커서 아래 점을 고정
      const s1 = B.k * ns;
      const to = { s: ns, x: wx - this.mirror * (sx - B.cx) / s1, y: wy + (sy - B.cy) / s1 };
      this._animView(from, to, 220);
    }
    reset() { this._animView({ ...this.view }, { x: 0, y: 4.2, s: 1 }, 520); }
    _animView(from, to, dur) {
      tween(dur, (t) => { this.view = { x: lerp(from.x, to.x, t), y: lerp(from.y, to.y, t), s: lerp(from.s, to.s, t) }; this.requestDraw(); }, ease.out);
    }

    // ───────── 그리기 ─────────
    // 정적 레이어(광채·동심원·경도선·팔·시선)는 화면 상태가 같으면 다시 그리지 않고 붙여넣기만 한다.
    // 마우스를 올려 점을 강조할 때처럼 '위 레이어'만 바뀌면 점·표식만 새로 그린다.
    draw() {
      const { ctx, w, h, dpr } = fitCanvas(this.c);
      ctx.clearRect(0, 0, w, h);
      const C = this._colors();
      const key = [w, h, dpr, this.view.x, this.view.y, this.view.s, C.theme, this.mode,
        JSON.stringify(this.opts), this.armProg, this.modelProg, this._ver, [...this.armOff].join(','),
        [...this.modelOff].join(','), this.highlightArm].join('|');
      if (key !== this._baseKey) {
        const bc = this._baseCv || (this._baseCv = document.createElement('canvas'));
        bc.width = this.c.width; bc.height = this.c.height;
        const b = bc.getContext('2d'); b.setTransform(dpr, 0, 0, dpr, 0, 0);
        this._drawBase(b, w, h, C);
        this._baseKey = key;
      }
      ctx.globalAlpha = this.fade;
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.drawImage(this._baseCv, 0, 0); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.globalAlpha = 1;
      this._drawTop(ctx, C);
      this.o.onScale && this.o.onScale(this.scale);
    }
    _colors() {
      const theme = document.documentElement.dataset.theme;
      if (this._C && this._C.theme === theme) return this._C;
      this._C = {
        theme, line: cssVar('--line'), line2: cssVar('--line-2'), line3: cssVar('--line-3'), sub: cssVar('--sub'), muted: cssVar('--muted'),
        text: cssVar('--text'), acc: cssVar('--accent'), amber: cssVar('--amber'), red: cssVar('--red'), surf: cssVar('--surface'), mono: cssVar('--mono'), sans: cssVar('--sans'),
        arm: Object.fromEntries(Object.keys(RT.ARM_COLORS).map((n) => [n, armColor(n)])),
      };
      return this._C;
    }
    _drawBase(ctx, w, h, C) {
      const dark = C.theme !== 'light';
      ctx.clearRect(0, 0, w, h);
      const s = this.scale, S = (x, y) => this.toScreen(x, y);
      const [gx, gy] = S(0, this.R0);

      // 원반 광채
      const glow = ctx.createRadialGradient(gx, gy, 0, gx, gy, 16 * s);
      glow.addColorStop(0, dark ? 'rgba(120,140,255,.10)' : 'rgba(80,100,200,.06)');
      glow.addColorStop(0.35, dark ? 'rgba(90,240,196,.035)' : 'rgba(0,163,122,.025)');
      glow.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = glow; ctx.fillRect(0, 0, w, h);

      // 은하중심 기준 동심원
      ctx.font = `10.5px ${C.mono}`; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      for (const R of [4, 8.15, 12, 16, 20]) {
        ctx.strokeStyle = R === 8.15 ? C.line3 : C.line2; ctx.setLineDash(R === 8.15 ? [] : [2, 5]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(gx, gy, R * s, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
        const [lx, ly] = S(0, this.R0 + R);
        ctx.fillStyle = C.muted; ctx.fillText(R === 8.15 ? 'R₀ 8.15' : `R ${R}`, lx + 4, ly + 7);
      }
      // 태양 기준 경도선
      ctx.strokeStyle = C.line; ctx.lineWidth = 1;
      const [sx0, sy0] = S(0, 0);
      for (let l = 0; l < 360; l += 30) {
        const d = 22, [ex, ey] = S(d * Math.sin(l * D2R), d * Math.cos(l * D2R));
        ctx.beginPath(); ctx.moveTo(sx0, sy0); ctx.lineTo(ex, ey); ctx.stroke();
        const [tx, ty] = S(3.2 * Math.sin(l * D2R), 3.2 * Math.cos(l * D2R));
        ctx.fillStyle = C.muted; ctx.textAlign = 'center'; ctx.fillText(`${l}°`, tx, ty);
      }
      // 사분면
      ctx.font = `600 11px ${C.mono}`; ctx.fillStyle = C.line3;
      [['I', 45], ['II', 135], ['III', 225], ['IV', 315]].forEach(([q, l]) => {
        const [tx, ty] = S(5.2 * Math.sin(l * D2R), 5.2 * Math.cos(l * D2R)); ctx.fillText(q, tx, ty);
      });

      this._labels = [];
      const showInfer = this.mode !== 'model' && this.infer;
      const showModel = this.mode !== 'infer' && this.model;

      // 문헌 모델 팔
      if (showModel) {
        for (const arm of this.model.arms) {
          if (this.modelOff.has(arm.name)) continue;
          const col = C.arm[arm.name] || C.acc;
          const cmp = this.mode === 'compare';
          this._armLine(ctx, arm.xy, col, {
            prog: this.modelProg, width: cmp ? 1 : 1.35, alpha: cmp ? 0.55 : 0.95, dash: cmp ? [5, 5] : null,
            glow: !cmp, label: RT.ARM_KO[arm.name] || arm.name, labelColor: col, hl: this.highlightArm === 'm:' + arm.name,
          });
        }
        if (this.opts.sight && this.model.sightlines && this.mode === 'model') this._sightlines(ctx, C);
      }
      // 추론된 팔
      if (showInfer && this.infer.ok) {
        const tolK = this.infer.tol_lnr || 0.08;
        this.infer.arms.forEach((arm, i) => {
          if (this.armOff.has(arm.id)) return;
          const col = FIT_COLORS[i % FIT_COLORS.length];
          if (this.opts.band) this._band(ctx, arm, col, tolK);
          this._armLine(ctx, arm.xy, col, { prog: this.armProg, width: 1.6, alpha: 1, glow: true, hl: this.highlightArm === arm.id,
            label: `팔 ${String.fromCharCode(65 + i)}`, labelColor: col, endDot: true });
        });
      }
    }

    _drawTop(ctx, C) {
      const s = this.scale, S = (x, y) => this.toScreen(x, y);
      const [gx, gy] = S(0, this.R0), [sx0, sy0] = S(0, 0);
      const showInfer = this.mode !== 'model' && this.infer;
      ctx.globalAlpha = this.fade;
      // 마우스를 올린 예상 교차점 강조
      if (this.hover && this.hover.kind === 'cross') {
        const [px, py] = S(this.hover.ref.x, this.hover.ref.y), r = 7;
        ctx.strokeStyle = C.arm[this.hover.ref.arm] || C.text; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(px, py - r); ctx.lineTo(px + r, py); ctx.lineTo(px, py + r); ctx.lineTo(px - r, py); ctx.closePath(); ctx.stroke(); ctx.lineWidth = 1;
      }
      // 점
      if (showInfer) this._points(ctx, C);

      // 레이더 스윕
      if (showInfer && this.sweep < 1) {
        const ang = this.sweep * 360, d = 24;
        const [ex, ey] = S(d * Math.sin(ang * D2R), d * Math.cos(ang * D2R));
        const g = ctx.createLinearGradient(sx0, sy0, ex, ey);
        g.addColorStop(0, rgba(C.acc, 0.9)); g.addColorStop(1, rgba(C.acc, 0));
        ctx.strokeStyle = g; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(sx0, sy0); ctx.lineTo(ex, ey); ctx.stroke(); ctx.lineWidth = 1;
        ctx.fillStyle = rgba(C.acc, 0.06); ctx.beginPath(); ctx.moveTo(sx0, sy0);
        const a0 = -Math.PI / 2, dir = this.mirror === 1 ? 1 : -1;
        ctx.arc(sx0, sy0, d * s, a0, a0 + dir * ang * D2R, dir < 0); ctx.closePath(); ctx.fill();
      }

      // 은하 중심 · 태양
      ctx.strokeStyle = C.red; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(gx - 5, gy - 5); ctx.lineTo(gx + 5, gy + 5); ctx.moveTo(gx + 5, gy - 5); ctx.lineTo(gx - 5, gy + 5); ctx.stroke();
      ctx.font = `500 11.5px ${C.sans}`; ctx.fillStyle = C.red; ctx.textAlign = 'left'; ctx.fillText('은하 중심', gx + 9, gy - 9);
      const sg = ctx.createRadialGradient(sx0, sy0, 0, sx0, sy0, 18);
      sg.addColorStop(0, rgba(C.amber, 0.55)); sg.addColorStop(1, rgba(C.amber, 0));
      ctx.fillStyle = sg; ctx.beginPath(); ctx.arc(sx0, sy0, 18, 0, 7); ctx.fill();
      ctx.strokeStyle = C.amber; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(sx0, sy0, 5.5, 0, 7); ctx.stroke();
      ctx.fillStyle = C.amber; ctx.beginPath(); ctx.arc(sx0, sy0, 1.6, 0, 7); ctx.fill(); ctx.lineWidth = 1;
      ctx.fillText('태양', sx0 + 10, sy0 + 12);
      ctx.globalAlpha = 1;
    }

    _armLine(ctx, xy, col, o) {
      if (!xy || xy.length < 2) return;
      const n = Math.max(2, Math.floor(xy.length * clamp(o.prog, 0, 1)));
      ctx.save();
      ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      if (o.dash) ctx.setLineDash(o.dash);
      // 끝으로 갈수록 옅어지게: 구간별로 그리기
      const pts = xy.slice(0, n).map(([x, y]) => this.toScreen(x, y));
      const W = (o.width || 1.4) * (o.hl ? 1.8 : 1);
      // 빛번짐: shadowBlur 는 느려서(저사양 현장 PC) 넓고 옅은 선 두 겹으로 대신한다
      const passes = o.glow ? [[W * 7, 0.05], [W * 3.2, 0.11], [W, 1]] : [[W, 1]];
      const seg = 12;
      for (const [lw, a] of passes) {
        for (let i = 0; i < pts.length - 1; i += seg) {
          const j = Math.min(pts.length - 1, i + seg);
          const f = i / (xy.length - 1);
          const fade = Math.min(1, Math.min(f, 1 - f) * 7 + 0.15);
          ctx.globalAlpha = (o.alpha ?? 1) * fade * a * (o.hl && a < 1 ? 1.8 : 1);
          ctx.strokeStyle = col; ctx.lineWidth = lw;
          ctx.beginPath(); ctx.moveTo(pts[i][0], pts[i][1]);
          for (let k = i + 1; k <= j; k++) ctx.lineTo(pts[k][0], pts[k][1]);
          ctx.stroke();
        }
      }
      ctx.setLineDash([]);
      // 라벨: 태양·은하중심·다른 라벨과 가장 먼, 화면 안의 점에 (붐비는 중앙을 피함)
      if (o.label && o.prog > 0.95) {
        const [sx, sy] = this.toScreen(0, 0), [gx, gy] = this.toScreen(0, this.R0);
        const W = this.c.clientWidth - (this.o.rightInset || 0), H = this.c.clientHeight;
        this._labels ||= [];
        let bi = 0, bs = -1;
        for (let i = 2; i < pts.length - 2; i += 3) {
          const [px, py] = pts[i];
          if (px < 60 || px > W - 60 || py < 150 || py > H - 40) continue;
          let sc = Math.min(Math.hypot(px - sx, py - sy), Math.hypot(px - gx, py - gy) * 1.2);
          for (const [lx, ly] of this._labels) sc = Math.min(sc, Math.hypot(px - lx, py - ly) * 1.5);
          if (sc > bs) { bs = sc; bi = i; }
        }
        this._labels.push(pts[bi]);
        const [x0, y0] = pts[bi], [x1, y1] = pts[Math.min(bi + 3, pts.length - 1)];
        let ang = Math.atan2(y1 - y0, x1 - x0);
        if (ang > Math.PI / 2 || ang < -Math.PI / 2) ang += Math.PI;
        ctx.globalAlpha = Math.min(1, (o.prog - 0.95) * 20) * (o.alpha ?? 1);
        ctx.translate(x0, y0); ctx.rotate(ang);
        ctx.font = `500 11px ${cssVar('--sans')}`; ctx.fillStyle = o.labelColor; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
        ctx.fillText(o.label, 0, -5);
      }
      ctx.restore();
    }
    _band(ctx, arm, col, tol) {
      // ±tol(ln r) 폭의 띠: r·e^{±tol}
      const k = Math.tan(arm.pitch_deg * D2R), n = 90, R0 = this.R0;
      const t0 = arm.theta_min, t1 = lerp(arm.theta_min, arm.theta_max, clamp(this.armProg, 0, 1));
      const edge = (sgn) => {
        const out = [];
        for (let i = 0; i <= n; i++) {
          const th = lerp(t0, t1, i / n), r = Math.exp(arm.xi - k * th + sgn * tol);
          out.push(this.toScreen(r * Math.sin(th), R0 - r * Math.cos(th)));
        }
        return out;
      };
      const a = edge(1), b = edge(-1).reverse();
      ctx.fillStyle = rgba(col, this.highlightArm === arm.id ? 0.14 : 0.07);
      ctx.beginPath(); ctx.moveTo(a[0][0], a[0][1]); for (const p of a) ctx.lineTo(p[0], p[1]); for (const p of b) ctx.lineTo(p[0], p[1]); ctx.closePath(); ctx.fill();
    }
    _sightlines(ctx, C) {
      const [sx, sy] = this.toScreen(0, 0);
      for (const sl of this.model.sightlines) {
        const d = 20, [ex, ey] = this.toScreen(d * Math.sin(sl.l * D2R), d * Math.cos(sl.l * D2R));
        const g = ctx.createLinearGradient(sx, sy, ex, ey);
        g.addColorStop(0, rgba(C.amber, 0.45)); g.addColorStop(1, rgba(C.amber, 0));
        ctx.strokeStyle = g; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(ex, ey); ctx.stroke();
        for (const c of sl.crossings) {
          if (this.modelOff.has(c.arm)) continue;
          const [px, py] = this.toScreen(c.x, c.y), r = 4.5;
          ctx.fillStyle = C.surf; ctx.strokeStyle = C.arm[c.arm] || C.acc; ctx.lineWidth = 1.4;
          ctx.beginPath(); ctx.moveTo(px, py - r); ctx.lineTo(px + r, py); ctx.lineTo(px, py + r); ctx.lineTo(px - r, py); ctx.closePath(); ctx.fill(); ctx.stroke();
        }
      }
      ctx.lineWidth = 1;
    }
    _points(ctx, C) {
      const pts = this.infer?.points || [];
      const sweepDeg = this.sweep * 360;
      const Tmax = Math.max(10, ...pts.map((p) => p.T || 0));
      // 근/원거리 모호성: 다른 해는 옅은 빈 원, 잇는 선은 마우스를 올린/선택한 점만
      const focus = (p) => (this.hover && this.hover.kind === 'pt' && this.hover.ref === p) || this.selected === p.id;
      for (const p of pts) {
        if (p.x === null || !p.alt?.length || (p.excluded && !this.opts.excl) || p.l > sweepDeg) continue;
        const f = focus(p);
        if (!this.opts.alt && !f) continue;
        const [x1, y1] = this.toScreen(p.x, p.y);
        for (const q of p.alt) {
          const [x2, y2] = this.toScreen(q.x, q.y);
          if (f) {
            ctx.strokeStyle = rgba(C.text, 0.6); ctx.setLineDash([2, 3]);
            ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]);
          }
          ctx.strokeStyle = rgba(f ? C.text : C.sub, f ? 0.9 : 0.28); ctx.beginPath(); ctx.arc(x2, y2, f ? 3.5 : 2.2, 0, 7); ctx.stroke();
        }
      }
      for (const p of pts) {
        if (p.x === null) continue;
        if (p.excluded && !this.opts.excl) continue;
        if (p.l > sweepDeg) continue;
        const age = clamp((sweepDeg - p.l) / 25, 0, 1);
        const [x, y] = this.toScreen(p.x, p.y);
        const col = p.arm >= 0 && !this.armOff.has(p.arm) ? FIT_COLORS[p.arm % FIT_COLORS.length] : C.sub;
        const r = (2.2 + 2.6 * Math.sqrt((p.T || 5) / Tmax)) * ease.outBack(age);
        const hov = this.hover && this.hover.kind === 'pt' && this.hover.ref === p;
        const sel = this.selected === p.id;
        ctx.globalAlpha = p.excluded ? 0.28 : 1;
        if (p.excluded) {
          ctx.strokeStyle = C.muted; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.stroke();
        } else if (p.src === 'synthetic') {
          ctx.fillStyle = col; const q = Math.max(2, r * 1.4); ctx.fillRect(Math.round(x - q / 2), Math.round(y - q / 2), q, q);
        } else {
          ctx.fillStyle = col; ctx.beginPath(); ctx.arc(x, y, r + 0.6, 0, 7); ctx.fill();
          ctx.strokeStyle = C.surf; ctx.lineWidth = 1; ctx.stroke();
        }
        if (age < 1) { ctx.strokeStyle = rgba(C.acc, 1 - age); ctx.beginPath(); ctx.arc(x, y, r + 10 * age, 0, 7); ctx.stroke(); }
        if (hov || sel) {
          ctx.globalAlpha = 1; ctx.strokeStyle = sel ? C.text : col; ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(x, y, r + 5, 0, 7); ctx.stroke(); ctx.lineWidth = 1;
        }
        ctx.globalAlpha = 1;
      }
    }

    // ───────── 상호작용 ─────────
    _pick(sx, sy) {
      let best = null, bd = 12;
      if (this.mode !== 'model' && this.infer?.points) {
        for (const p of this.infer.points) {
          if (p.x === null || (p.excluded && !this.opts.excl)) continue;
          const [x, y] = this.toScreen(p.x, p.y), d = Math.hypot(x - sx, y - sy);
          if (d < bd) { bd = d; best = { kind: 'pt', ref: p }; }
        }
      }
      if (this.mode === 'model' && this.opts.sight && this.model?.sightlines) {
        for (const sl of this.model.sightlines) for (const c of sl.crossings) {
          if (this.modelOff.has(c.arm)) continue;
          const [x, y] = this.toScreen(c.x, c.y), d = Math.hypot(x - sx, y - sy);
          if (d < bd) { bd = d; best = { kind: 'cross', ref: c, sl }; }
        }
      }
      return best;
    }
    _bind() {
      const c = this.c;
      c.addEventListener('pointermove', (e) => {
        const r = c.getBoundingClientRect(), sx = e.clientX - r.left, sy = e.clientY - r.top;
        if (this._drag) {
          const s = this.scale;
          this.view.x -= this.mirror * (sx - this._drag.x) / s; this.view.y += (sy - this._drag.y) / s;
          this._drag.x = sx; this._drag.y = sy; this.requestDraw(); return;
        }
        const [wx, wy] = this.toWorld(sx, sy);
        this.o.onCursor && this.o.onCursor(wx, wy);
        const h = this._pick(sx, sy);
        const same = (h && this.hover && h.ref === this.hover.ref) || (!h && !this.hover);
        this.hover = h;
        if (!same) this.requestDraw();
        this.o.onHover && this.o.onHover(h, e.clientX, e.clientY);
        c.style.cursor = h ? 'pointer' : '';
      });
      c.addEventListener('pointerleave', () => { this.hover = null; this.requestDraw(); this.o.onHover && this.o.onHover(null); this.o.onCursor && this.o.onCursor(null); });
      c.addEventListener('pointerdown', (e) => {
        const r = c.getBoundingClientRect();
        this._down = { x: e.clientX, y: e.clientY };
        this._drag = { x: e.clientX - r.left, y: e.clientY - r.top };
        c.setPointerCapture(e.pointerId);
      });
      const up = (e) => {
        const click = this._down && Math.hypot(e.clientX - this._down.x, e.clientY - this._down.y) < 4;
        this._drag = null; this._down = null;
        if (click) {
          const h = this.hover;
          this.selected = h && h.kind === 'pt' ? (this.selected === h.ref.id ? null : h.ref.id) : null;
          this.requestDraw(); this.o.onSelect && this.o.onSelect(h);
        }
      };
      c.addEventListener('pointerup', up); c.addEventListener('pointercancel', () => { this._drag = null; });
      c.addEventListener('wheel', (e) => {
        e.preventDefault();
        const r = c.getBoundingClientRect(), sx = e.clientX - r.left, sy = e.clientY - r.top;
        const [wx, wy] = this.toWorld(sx, sy);
        const ns = clamp(this.view.s * Math.exp(-e.deltaY * 0.0016), 0.45, 12);
        const B = this._base(), s1 = B.k * ns;
        this.view = { s: ns, x: wx - this.mirror * (sx - B.cx) / s1, y: wy + (sy - B.cy) / s1 };
        this.requestDraw();
      }, { passive: false });
      c.addEventListener('dblclick', () => this.reset());
    }
    /** 지워질 때 점들을 픽셀로 흩뿌리기 */
    burstPoints(filter) {
      const r = this.c.getBoundingClientRect();
      const pts = (this.infer?.points || []).filter(filter).filter((p) => p.x !== null).map((p) => {
        const [x, y] = this.toScreen(p.x, p.y);
        return { x: r.left + x, y: r.top + y, color: p.arm >= 0 ? FIT_COLORS[p.arm % FIT_COLORS.length] : cssVar('--sub') };
      });
      RT.fx.burstPoints(pts, cssVar('--sub'), 6);
    }
  }

  // 허프 공간 미니맵
  function drawHough(canvas, hough, arms) {
    const { ctx, w, h } = fitCanvas(canvas);
    ctx.clearRect(0, 0, w, h);
    if (!hough || !hough.acc?.length) return;
    const A = hough.acc, nP = A.length, nX = A[0].length;
    const img = ctx.createImageData(nP, nX);
    for (let i = 0; i < nP; i++) for (let j = 0; j < nX; j++) {
      const v = Math.pow(A[i][j], 0.6), c = RT.cmap(v), k = ((nX - 1 - j) * nP + i) * 4;
      img.data[k] = c[0]; img.data[k + 1] = c[1]; img.data[k + 2] = c[2]; img.data[k + 3] = 255;
    }
    const off = document.createElement('canvas'); off.width = nP; off.height = nX;
    off.getContext('2d').putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = true; ctx.drawImage(off, 0, 0, w, h);
    const p0 = hough.pitches[0], p1 = hough.pitches[nP - 1], [x0, x1] = hough.xi;
    const X = (p) => ((p - p0) / (p1 - p0)) * w, Y = (xi) => h - ((xi - x0) / (x1 - x0)) * h;
    (hough.peaks || []).forEach(([p, xi], i) => {
      const arm = arms.find((a) => Math.abs(a.pitch_deg - p) < 1e-6 && Math.abs(a.xi - xi) < 1e-6);
      const idx = arm ? arm.id : i;
      ctx.strokeStyle = FIT_COLORS[idx % FIT_COLORS.length]; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(X(p), Y(xi), 6, 0, 7); ctx.stroke();
      ctx.fillStyle = '#fff'; ctx.font = `600 10px ${cssVar('--mono')}`; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      ctx.fillText(String.fromCharCode(65 + idx), X(p) + 9, Y(xi));
    });
    ctx.fillStyle = 'rgba(255,255,255,.7)'; ctx.font = `10px ${cssVar('--mono')}`; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
    ctx.fillText(`ψ ${p0}°`, 4, h - 3); ctx.textAlign = 'right'; ctx.fillText(`${p1}°`, w - 4, h - 3);
  }

  RT.GalaxyMap = GalaxyMap;
  RT.drawHough = drawHough;
})(window.RT);
