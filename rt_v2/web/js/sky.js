/* sky.js — 전천 HEALPix 지도
   투영: 몰바이데(확대·이동) / 천구 정사영(드래그 회전, 관성)
   천문 관례대로 경도는 왼쪽으로 증가 (하늘을 안쪽에서 올려다본 모습)           */
'use strict';
(function (RT) {
  const { clamp, fitCanvas, cssVar, rgba, cmap, D2R, R2D, eq2gal, gal2eq, radecToPix, b64f32, tween } = RT;
  const SQ2 = Math.SQRT2;

  function mollTheta(lat) {
    if (Math.abs(lat) > 1.5707) return Math.sign(lat) * Math.PI / 2;
    let t = lat; const k = Math.PI * Math.sin(lat);
    for (let i = 0; i < 12; i++) { const d = (2 * t + Math.sin(2 * t) - k) / (2 + 2 * Math.cos(2 * t)); t -= d; if (Math.abs(d) < 1e-7) break; }
    return t;
  }
  // 몰바이데: (경도[-180,180], 위도) → 단위 좌표 x∈[-2√2,2√2], y∈[-√2,√2]
  function moll(lonDeg, latDeg) {
    const t = mollTheta(latDeg * D2R);
    return [(2 * SQ2 / Math.PI) * lonDeg * D2R * Math.cos(t), SQ2 * Math.sin(t)];
  }
  function mollInv(x, y) {
    if (Math.abs(y) > SQ2) return null;
    const t = Math.asin(y / SQ2);
    const lat = Math.asin(clamp((2 * t + Math.sin(2 * t)) / Math.PI, -1, 1));
    const lon = (Math.PI * x) / (2 * SQ2 * Math.cos(t));
    if (Math.abs(lon) > Math.PI) return null;
    return [lon * R2D, lat * R2D];
  }
  const wrap180 = (l) => ((((l + 180) % 360) + 360) % 360) - 180;

  class SkyMap {
    constructor(canvas, opts = {}) {
      this.c = canvas; this.o = opts;
      this.proj = 'moll'; this.frame = 'gal';
      this.layers = { grid: true, plane: true, cells: true, visible: true, zenith: true, fg: false };
      this.geom = null; this.vals = new Map(); this.hits = new Map(); this.fg = null;
      this.view = { s: 1, ox: 0, oy: 0 };          // 몰바이데 확대/이동
      this.rot = { lon: 0, lat: 20, vl: 0, vb: 0 }; // 천구 회전
      this.hoverPix = -1; this.alpha = 1; this.site = { lat: 36.5, lon: 127.2 };
      this._dirty = true; this._loop = false; this._idle = 0; this.autoSpin = true;
      new ResizeObserver(() => this.redraw()).observe(canvas);
      this._bind();
    }
    setGeometry(g) {
      this.geom = {
        nside: g.nside, npix: g.npix, nv: g.nv,
        eq: b64f32(g.eq), gal: b64f32(g.gal), ceq: b64f32(g.centers_eq), cgal: b64f32(g.centers_gal), pixDeg: g.pix_deg,
      };
      this._mc = null; this._scr = null; this._ver = (this._ver || 0) + 1;
      this.redraw();
    }
    setData(d) {
      this._ver = (this._ver || 0) + 1;
      this.vals = new Map(d.pixels.map((p, i) => [p, d.values[i]]));
      this.hits = new Map(d.pixels.map((p, i) => [p, d.hits[i]]));
      this.alpha = 0;
      tween(700, (t) => { this.alpha = t; this.redraw(); });
    }
    setForeground(arr) { this.fg = arr; this._ver = (this._ver || 0) + 1; this.redraw(); }
    value(p) {
      let v = this.vals.get(p);
      if (v === undefined || v === null) return null;
      if (this.layers.fg && this.fg) v -= this.fg[p] * (this.fgScale ?? 1);
      return v;
    }
    range() {
      let lo = Infinity, hi = -Infinity;
      for (const p of this.vals.keys()) { const v = this.value(p); if (v !== null && Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }
      if (!Number.isFinite(lo)) return [0, 1];
      if (hi - lo < 1e-6) { lo -= 0.5; hi += 0.5; }
      return [lo, hi];
    }
    set(key, val) { this[key] = val; this.redraw(); }
    redraw() { this._dirty = true; this._kick(); }
    _kick() { if (!this._loop) { this._loop = true; requestAnimationFrame((t) => this._tick(t)); } }
    _tick(now) {
      let again = false;
      if (this.proj === 'globe') {
        const r = this.rot;
        if (!this._drag) {
          if (Math.abs(r.vl) + Math.abs(r.vb) > 0.01) { r.lon += r.vl; r.lat = clamp(r.lat + r.vb, -89, 89); r.vl *= 0.94; r.vb *= 0.94; this._dirty = true; again = true; }
          else if (this.autoSpin && RT.motionOK() && this.c.offsetParent) { r.lon += 0.06; this._dirty = true; again = true; }
        }
      }
      if (this._dirty && this.c.offsetParent) { this._dirty = false; this.draw(); }
      if (again) requestAnimationFrame((t) => this._tick(t)); else this._loop = false;
    }

    // 표시 좌표계 경위도 배열 (frame 에 따라)
    _lonlat() { return this.frame === 'gal' ? this.geom.gal : this.geom.eq; }
    _toDisp(ra, dec) { return this.frame === 'gal' ? eq2gal(ra, dec) : [ra, dec]; }
    _fromDisp(lon, lat) { return this.frame === 'gal' ? gal2eq(lon, lat) : [lon, lat]; }

    _layout() {
      const w = this.c.clientWidth, h = this.c.clientHeight;
      const right = this.o.rightInset || 0;
      const aw = w - right - 40, ah = h - 140;
      if (this.proj === 'moll') {
        const base = Math.min(aw / (4 * SQ2), ah / (2 * SQ2));
        return { w, h, cx: (w - right) / 2 + this.view.ox, cy: h / 2 + 24 + this.view.oy, s: base * this.view.s };
      }
      const R = Math.min(aw, ah - 40) / 2 * 0.92 * this.view.s;
      return { w, h, cx: (w - right) / 2 + 10, cy: h / 2 + 44, R };
    }
    // 표시 경위도 → 화면 (보이지 않으면 null)
    _project(L, lon, lat) {
      if (this.proj === 'moll') {
        const [x, y] = moll(wrap180(lon), lat);
        return [L.cx - x * L.s, L.cy - y * L.s];
      }
      const l0 = this.rot.lon * D2R, b0 = this.rot.lat * D2R, l = lon * D2R, b = lat * D2R;
      const cosc = Math.sin(b0) * Math.sin(b) + Math.cos(b0) * Math.cos(b) * Math.cos(l - l0);
      let x = Math.cos(b) * Math.sin(l - l0);
      let y = Math.cos(b0) * Math.sin(b) - Math.sin(b0) * Math.cos(b) * Math.cos(l - l0);
      if (cosc < 0) {
        // 뒤쪽 반구 꼭짓점: 테두리 위로 밀어서 다각형이 앞면 안에서 접히지 않게 한다
        const n = Math.hypot(x, y) || 1; x /= n; y /= n;
      }
      return [L.cx - x * L.R, L.cy - y * L.R, cosc];
    }
    _unproject(L, sx, sy) {
      if (this.proj === 'moll') return mollInv(-(sx - L.cx) / L.s, -(sy - L.cy) / L.s);
      const x = -(sx - L.cx) / L.R, y = -(sy - L.cy) / L.R, rho = Math.hypot(x, y);
      if (rho > 1) return null;
      const c = Math.asin(rho), l0 = this.rot.lon * D2R, b0 = this.rot.lat * D2R;
      if (rho < 1e-9) return [this.rot.lon, this.rot.lat];
      const lat = Math.asin(Math.cos(c) * Math.sin(b0) + (y * Math.sin(c) * Math.cos(b0)) / rho);
      const lon = l0 + Math.atan2(x * Math.sin(c), rho * Math.cos(c) * Math.cos(b0) - y * Math.sin(c) * Math.sin(b0));
      return [((lon * R2D) % 360 + 360) % 360, lat * R2D];
    }
    _outline(ctx, L) {
      ctx.beginPath();
      if (this.proj === 'moll') ctx.ellipse(L.cx, L.cy, 2 * SQ2 * L.s, SQ2 * L.s, 0, 0, Math.PI * 2);
      else ctx.arc(L.cx, L.cy, L.R, 0, Math.PI * 2);
    }
    // 위경도 폴리라인 (이음매에서 끊기)
    _polyline(ctx, L, pts) {
      let prev = null; ctx.beginPath();
      for (const [lon, lat] of pts) {
        const p = this._project(L, lon, lat);
        if (!p || (p[2] !== undefined && p[2] < 0)) { prev = null; continue; }
        if (prev && Math.hypot(p[0] - prev[0], p[1] - prev[1]) > 80 * (L.s || L.R / 3) / 60) { prev = null; }
        prev ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]);
        prev = p;
      }
      ctx.stroke();
    }

    // ───── 픽셀 경로: 꼭짓점 투영을 한 번에 계산해 버퍼에 담고, 경로는 버퍼에서 바로 만든다 ─────
    _ensureMoll() {
      const g = this.geom, key = this.frame + ':' + g.nside;
      if (this._mc && this._mc.key === key) return this._mc;
      const ll = this._lonlat(), nv = g.nv, n = g.npix;
      const xy = new Float32Array(n * nv * 2), wraps = new Uint8Array(n);
      for (let i = 0; i < n; i++) {
        let mn = 999, mx = -999;
        for (let k = 0; k < nv; k++) {
          const j = (i * nv + k) * 2, lon = wrap180(ll[j]), lat = ll[j + 1];
          if (Math.abs(lat) < 89.9) { if (lon < mn) mn = lon; if (lon > mx) mx = lon; }
          const t = mollTheta(lat * D2R);
          xy[j] = (2 * SQ2 / Math.PI) * lon * D2R * Math.cos(t); xy[j + 1] = SQ2 * Math.sin(t);
        }
        wraps[i] = mx - mn > 180 ? 1 : 0;
      }
      this._mc = { key, xy, wraps };
      return this._mc;
    }
    _buildScreen(L) {
      const g = this.geom, n = g.npix, nv = g.nv;
      if (!this._scr || this._scr.length !== n * nv * 2) { this._scr = new Float32Array(n * nv * 2); this._vis = new Uint8Array(n); }
      const scr = this._scr, vis = this._vis;
      if (this.proj === 'moll') {
        const xy = this._ensureMoll().xy;
        for (let j = 0; j < xy.length; j += 2) { scr[j] = L.cx - xy[j] * L.s; scr[j + 1] = L.cy - xy[j + 1] * L.s; }
        vis.fill(1);
        return;
      }
      const ll = this._lonlat(), cc = this.frame === 'gal' ? g.cgal : g.ceq;
      const l0 = this.rot.lon * D2R, b0 = this.rot.lat * D2R, sb0 = Math.sin(b0), cb0 = Math.cos(b0);
      const thr = -Math.sin(Math.min(60, g.pixDeg * 0.8) * D2R);
      for (let i = 0; i < n; i++) {
        const lc = cc[2 * i] * D2R, bc = cc[2 * i + 1] * D2R;
        if (sb0 * Math.sin(bc) + cb0 * Math.cos(bc) * Math.cos(lc - l0) < thr) { vis[i] = 0; continue; }
        let any = 0;
        for (let k = 0; k < nv; k++) {
          const j = (i * nv + k) * 2, l = ll[j] * D2R, b = ll[j + 1] * D2R;
          const cb = Math.cos(b), dl = l - l0;
          const cosc = sb0 * Math.sin(b) + cb0 * cb * Math.cos(dl);
          let x = cb * Math.sin(dl), y = cb0 * Math.sin(b) - sb0 * cb * Math.cos(dl);
          if (cosc < 0) { const m = Math.hypot(x, y) || 1; x /= m; y /= m; } else any = 1;
          scr[j] = L.cx - x * L.R; scr[j + 1] = L.cy - y * L.R;
        }
        vis[i] = any;
      }
    }
    /** 현재 경로에 픽셀 i 의 부분경로를 덧붙인다 (beginPath 안 함). 보이면 true */
    _addPix(ctx, L, i) {
      if (!this._vis[i]) return false;
      const g = this.geom, nv = g.nv, o = i * nv * 2;
      if (this.proj === 'moll' && this._mc.wraps[i]) {
        // 이음매를 걸친 픽셀: 양쪽에 한 번씩 (타원 밖은 클립됨)
        const ll = this._lonlat();
        for (const side of [1, -1]) {
          for (let k = 0; k < nv; k++) {
            let lon = wrap180(ll[o + 2 * k]); const lat = ll[o + 2 * k + 1];
            if (side === 1 && lon < 0) lon += 360; if (side === -1 && lon > 0) lon -= 360;
            const t = mollTheta(lat * D2R);
            const sx = L.cx - (2 * SQ2 / Math.PI) * lon * D2R * Math.cos(t) * L.s, sy = L.cy - SQ2 * Math.sin(t) * L.s;
            k ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy);
          }
          ctx.closePath();
        }
        return true;
      }
      const s = this._scr;
      ctx.moveTo(s[o], s[o + 1]);
      for (let k = 1; k < nv; k++) ctx.lineTo(s[o + 2 * k], s[o + 2 * k + 1]);
      ctx.closePath();
      return true;
    }
    _eachPixPath(ctx, L, i, fn) { ctx.beginPath(); if (this._addPix(ctx, L, i)) fn(); }

    draw() {
      const { ctx, w, h, dpr } = fitCanvas(this.c);
      ctx.clearRect(0, 0, w, h);
      if (!this.geom) return;
      const L = this._layout(); this._L = L;
      if (this.proj === 'moll') {
        // 몰바이데는 정적인 바탕을 따로 그려 두고, 마우스 강조·천정만 매번 덧그린다
        const key = [w, h, dpr, L.s, L.cx, L.cy, this.frame, this.geom.nside, document.documentElement.dataset.theme,
          JSON.stringify(this.layers), this._ver, this.alpha, this.site.lat, this.fgScale].join('|');
        if (key !== this._baseKey) {
          const bc = this._baseCv || (this._baseCv = document.createElement('canvas'));
          bc.width = this.c.width; bc.height = this.c.height;
          const bctx = bc.getContext('2d'); bctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          this._buildScreen(L);
          this._drawBase(bctx, L);
          this._baseKey = key;
        }
        ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.drawImage(this._baseCv, 0, 0); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      } else {
        this._buildScreen(L);
        this._drawBase(ctx, L);
      }
      this._drawOverlay(ctx, L);
    }

    _drawBase(ctx, L) {
      const g = this.geom;
      const line = cssVar('--line'), line2 = cssVar('--line-2'), muted = cssVar('--muted'), acc = cssVar('--accent');
      const dark = document.documentElement.dataset.theme !== 'light';

      // 바탕 (구/타원)
      ctx.save();
      this._outline(ctx, L);
      const grd = this.proj === 'globe'
        ? ctx.createRadialGradient(L.cx - L.R * 0.3, L.cy - L.R * 0.35, L.R * 0.1, L.cx, L.cy, L.R)
        : ctx.createRadialGradient(L.cx, L.cy, 0, L.cx, L.cy, 2 * SQ2 * L.s);
      grd.addColorStop(0, dark ? '#16161b' : '#ffffff'); grd.addColorStop(1, dark ? '#0c0c0f' : '#f1f1f3');
      ctx.fillStyle = grd; ctx.fill();
      ctx.clip();

      const [vmin, vmax] = this.range(); this._range = [vmin, vmax];
      const gridAlpha = g.nside <= 8 ? 1 : g.nside <= 16 ? 0.5 : 0.22;
      const lat0 = this.site.lat;
      // 픽셀 — 꼭짓점은 버퍼에서 읽고, 픽셀마다 짧은 경로를 그린다
      // (경로 하나에 1만 개 넘는 부분경로를 붙이면 Chromium 에서 오히려 수백 배 느려짐)
      const hiddenFill = dark ? 'rgba(255,90,82,.06)' : 'rgba(229,56,59,.06)';
      const obsLine = rgba(dark ? '#000000' : '#ffffff', 0.25);
      ctx.lineWidth = 1;
      for (let i = 0; i < g.npix; i++) {
        if (!this._vis[i]) continue;
        const v = this.value(i);
        const hidden = v === null && this.layers.visible && g.ceq[2 * i + 1] < lat0 - 90;
        if (v === null && !hidden && !this.layers.cells) continue;
        ctx.beginPath(); this._addPix(ctx, L, i);
        if (v !== null) {
          const c = cmap((v - vmin) / (vmax - vmin));
          ctx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${this.alpha})`; ctx.fill();
        } else if (hidden) { ctx.fillStyle = hiddenFill; ctx.fill(); }
        if (this.layers.cells) {
          ctx.strokeStyle = v !== null ? obsLine : line; ctx.globalAlpha = v !== null ? 1 : gridAlpha;
          ctx.stroke(); ctx.globalAlpha = 1;
        }
      }

      // 경위선
      if (this.layers.grid) {
        ctx.strokeStyle = line2; ctx.lineWidth = 1; ctx.setLineDash([2, 4]);
        for (let lon = -180; lon <= 180; lon += 30) { const pts = []; for (let lat = -90; lat <= 90; lat += 3) pts.push([lon === 180 ? 179.999 : lon, lat]); this._polyline(ctx, L, pts); }
        for (let lat = -60; lat <= 60; lat += 30) { const pts = []; for (let lon = -180; lon <= 180; lon += 3) pts.push([lon, lat]); this._polyline(ctx, L, pts); }
        ctx.setLineDash([]);
      }
      // 은하면(적도좌표일 때) / 천구적도(은하좌표일 때)
      if (this.layers.plane) {
        const pts = [];
        for (let a = 0; a <= 360; a += 2) pts.push(this.frame === 'gal' ? eq2gal(a, 0) : gal2eq(a, 0));
        ctx.strokeStyle = rgba(cssVar('--violet'), 0.75); ctx.lineWidth = 1.25; this._polyline(ctx, L, pts); ctx.lineWidth = 1;
        const gc = this.frame === 'gal' ? [0, 0] : gal2eq(0, 0);
        const p = this._project(L, gc[0], gc[1]);
        if (p && !(p[2] < 0)) {
          ctx.strokeStyle = cssVar('--red'); ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.moveTo(p[0] - 5, p[1] - 5); ctx.lineTo(p[0] + 5, p[1] + 5); ctx.moveTo(p[0] + 5, p[1] - 5); ctx.lineTo(p[0] - 5, p[1] + 5); ctx.stroke(); ctx.lineWidth = 1;
          ctx.fillStyle = cssVar('--red'); ctx.font = `500 11px ${cssVar('--sans')}`; ctx.textAlign = 'left'; ctx.fillText('은하 중심', p[0] + 8, p[1] - 12);
        }
      }
      // 관측 가능 한계 (적위 = 위도-90)
      if (this.layers.visible) {
        const pts = []; for (let a = 0; a <= 360; a += 2) pts.push(this._toDisp(a, lat0 - 90));
        ctx.strokeStyle = rgba(cssVar('--red'), 0.55); ctx.setLineDash([5, 4]); this._polyline(ctx, L, pts); ctx.setLineDash([]);
      }
      ctx.restore();

      // 가장자리
      this._outline(ctx, L); ctx.strokeStyle = line2; ctx.lineWidth = 1; ctx.stroke();
      if (this.proj === 'globe') {
        const sh = ctx.createRadialGradient(L.cx, L.cy, L.R * 0.97, L.cx, L.cy, L.R * 1.07);
        sh.addColorStop(0, rgba(acc, dark ? 0.14 : 0.1)); sh.addColorStop(1, rgba(acc, 0));
        ctx.fillStyle = sh; ctx.beginPath(); ctx.arc(L.cx, L.cy, L.R * 1.07, 0, 7); ctx.arc(L.cx, L.cy, L.R, 0, 7, true); ctx.fill();
      }
      // 경도 눈금 라벨 (몰바이데)
      if (this.proj === 'moll' && this.layers.grid) {
        ctx.fillStyle = muted; ctx.font = `11px ${cssVar('--mono')}`; ctx.textAlign = 'center';
        for (let lon = -150; lon <= 180; lon += 30) {
          const p = this._project(L, lon, 0);
          const lab = this.frame === 'gal' ? `${((lon % 360) + 360) % 360}°` : `${(((lon % 360) + 360) % 360) / 15}h`;
          ctx.fillText(lab, p[0], p[1] + 14);
        }
        ctx.textAlign = 'right';
        for (const lat of [-60, -30, 30, 60]) { const p = this._project(L, 180, lat); ctx.fillText(`${lat > 0 ? '+' : '−'}${Math.abs(lat)}°`, p[0] - 6, p[1] + 4); }
      }
    }

    _drawOverlay(ctx, L) {
      ctx.save();
      this._outline(ctx, L); ctx.clip();
      // 지금의 천정 + 지평선
      if (this.layers.zenith) {
        const zr = RT.zenithRA(new Date(), this.site.lon), zd = this.site.lat;
        const zv = [Math.cos(zd * D2R) * Math.cos(zr * D2R), Math.cos(zd * D2R) * Math.sin(zr * D2R), Math.sin(zd * D2R)];
        const u = [-Math.sin(zr * D2R), Math.cos(zr * D2R), 0];
        const vv = [zv[1] * u[2] - zv[2] * u[1], zv[2] * u[0] - zv[0] * u[2], zv[0] * u[1] - zv[1] * u[0]];
        const pts = [];
        for (let a = 0; a <= 360; a += 2) {
          const ca = Math.cos(a * D2R), sa = Math.sin(a * D2R);
          const p = [u[0] * ca + vv[0] * sa, u[1] * ca + vv[1] * sa, u[2] * ca + vv[2] * sa];
          let ra = Math.atan2(p[1], p[0]) * R2D; if (ra < 0) ra += 360;
          pts.push(this._toDisp(ra, Math.asin(clamp(p[2], -1, 1)) * R2D));
        }
        ctx.strokeStyle = rgba(cssVar('--amber'), 0.7); ctx.setLineDash([1, 3]); ctx.lineWidth = 1.25; this._polyline(ctx, L, pts); ctx.setLineDash([]); ctx.lineWidth = 1;
        const zp = this._toDisp(zr, zd), p = this._project(L, zp[0], zp[1]);
        if (p && !(p[2] < 0)) {
          const amber = cssVar('--amber');
          ctx.strokeStyle = amber; ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(p[0], p[1], 6, 0, 7); ctx.moveTo(p[0] - 11, p[1]); ctx.lineTo(p[0] - 3, p[1]); ctx.moveTo(p[0] + 3, p[1]); ctx.lineTo(p[0] + 11, p[1]); ctx.moveTo(p[0], p[1] - 11); ctx.lineTo(p[0], p[1] - 3); ctx.moveTo(p[0], p[1] + 3); ctx.lineTo(p[0], p[1] + 11); ctx.stroke(); ctx.lineWidth = 1;
          ctx.fillStyle = amber; ctx.font = `500 11px ${cssVar('--sans')}`; ctx.textAlign = 'left'; ctx.fillText('지금 천정', p[0] + 13, p[1] + 4);
        }
      }
      // 호버 픽셀
      if (this.hoverPix >= 0 && this._scr) {
        this._eachPixPath(ctx, L, this.hoverPix, () => { ctx.strokeStyle = cssVar('--accent'); ctx.lineWidth = 2; ctx.stroke(); ctx.lineWidth = 1; });
      }
      ctx.restore();
    }

    _bind() {
      const c = this.c;
      c.addEventListener('pointermove', (e) => {
        const r = c.getBoundingClientRect(), sx = e.clientX - r.left, sy = e.clientY - r.top;
        if (this._drag) {
          const dx = sx - this._drag.x, dy = sy - this._drag.y; this._drag.x = sx; this._drag.y = sy;
          if (this.proj === 'moll') { this.view.ox += dx; this.view.oy += dy; }
          else { const k = 90 / (this._L?.R || 300); this.rot.lon += dx * k; this.rot.lat = clamp(this.rot.lat + dy * k, -89, 89); this.rot.vl = dx * k; this.rot.vb = dy * k; }
          this.redraw(); return;
        }
        if (!this.geom || !this._L) return;
        const ll = this._unproject(this._L, sx, sy);
        let pix = -1;
        if (ll) {
          const [ra, dec] = this._fromDisp(((ll[0] % 360) + 360) % 360, ll[1]);
          pix = radecToPix(this.geom.nside, ra, dec);
          this.o.onCursor && this.o.onCursor({ ra, dec, lon: ((ll[0] % 360) + 360) % 360, lat: ll[1], frame: this.frame });
        } else this.o.onCursor && this.o.onCursor(null);
        if (pix !== this.hoverPix) { this.hoverPix = pix; this.redraw(); this.o.onHover && this.o.onHover(pix >= 0 ? this.pixInfo(pix) : null); }
      });
      c.addEventListener('pointerleave', () => { this.hoverPix = -1; this.redraw(); this.o.onHover && this.o.onHover(null); this.o.onCursor && this.o.onCursor(null); });
      c.addEventListener('pointerdown', (e) => {
        c.setPointerCapture(e.pointerId); const r = c.getBoundingClientRect();
        this._drag = { x: e.clientX - r.left, y: e.clientY - r.top }; this.autoSpin = false; c.style.cursor = 'grabbing';
      });
      const up = () => { this._drag = null; c.style.cursor = ''; this._kick(); };
      c.addEventListener('pointerup', up); c.addEventListener('pointercancel', up);
      c.addEventListener('wheel', (e) => {
        e.preventDefault();
        const k = Math.exp(-e.deltaY * 0.0015);
        const r = c.getBoundingClientRect(), L = this._L;
        const ns = clamp(this.view.s * k, 0.6, 8);
        if (this.proj === 'moll' && L) {
          const sx = e.clientX - r.left, sy = e.clientY - r.top, f = ns / this.view.s;
          this.view.ox = (this.view.ox + (L.cx - this.view.ox) - sx) * f - (L.cx - this.view.ox) + sx;
          this.view.oy = (this.view.oy + (L.cy - this.view.oy) - sy) * f - (L.cy - this.view.oy) + sy;
        }
        this.view.s = ns; this.redraw();
      }, { passive: false });
      c.addEventListener('dblclick', () => {
        const v0 = { ...this.view };
        tween(420, (t) => { this.view.s = RT.lerp(v0.s, 1, t); this.view.ox = RT.lerp(v0.ox, 0, t); this.view.oy = RT.lerp(v0.oy, 0, t); this.redraw(); });
      });
    }
    pixInfo(p) {
      const g = this.geom;
      return {
        pix: p, ra: g.ceq[2 * p], dec: g.ceq[2 * p + 1], l: g.cgal[2 * p], b: g.cgal[2 * p + 1],
        T: this.vals.has(p) ? this.vals.get(p) : null, Tdisp: this.value(p), hits: this.hits.get(p) || 0,
        fg: this.fg ? this.fg[p] : null, hidden: g.ceq[2 * p + 1] < this.site.lat - 90,
      };
    }
    focusPixel(p) {
      if (!this.geom || p < 0) return;
      const [lon, lat] = this.frame === 'gal' ? [this.geom.cgal[2 * p], this.geom.cgal[2 * p + 1]] : [this.geom.ceq[2 * p], this.geom.ceq[2 * p + 1]];
      this.hoverPix = p;
      if (this.proj === 'globe') {
        const from = { ...this.rot }; let dl = wrap180(lon - from.lon);
        tween(700, (t) => { this.rot.lon = from.lon + dl * t; this.rot.lat = RT.lerp(from.lat, lat, t); this.redraw(); });
        this.autoSpin = false;
      }
      this.redraw();
      this.o.onHover && this.o.onHover(this.pixInfo(p));
    }
  }

  RT.SkyMap = SkyMap;
})(window.RT);
