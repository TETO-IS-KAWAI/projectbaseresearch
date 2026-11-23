"""
api.py
웹 UI ↔ 계산 모듈 사이의 백엔드 API  (Qt 에 의존하지 않음)

  · main_app.py  : Qt WebEngine 창 + QWebChannel 로 이 API 를 노출
  · scripts/dev_server.py : 같은 API 를 HTTP 로 노출 (브라우저에서 UI 개발/점검용)

모든 공개 메서드는 `api_<이름>` 이고, 인자는 키워드, 반환은 JSON 직렬화
가능한 dict/list 이다. NaN/inf 는 None 으로 바뀐다.
"""

from __future__ import annotations

import base64
import json
import math
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import astropy.units as u
from astropy.coordinates import Angle, SkyCoord
from astropy_healpix import HEALPix

from config import Config
from data_manager import get_project
from astro_processing import (
    HI_FREQ_HZ, R_SUN_KPC, V_CIRC_KMS,
    process_observation, icrs_to_galactic, galactocentric_velocity,
)
from spiral_arm import (
    analyze_observation, velocity_to_distance, get_reference_spiral_arms,
    infer_spiral_arms, predict_sightline_crossings, synthetic_arm_peaks,
    peak_candidates,
)

APP_NAME    = 'HI 21cm Radio Telescope'
APP_NAME_KO = 'HI 21cm 전파망원경'
APP_VERSION = '2.0.0'
CREDITS = dict(
    school='SASA · 10기',
    team='팀 RWA',
    devs='TETO-IS-KAWAI',
    license='MIT License',
    year=2026,
    repo='https://github.com/TETO-IS-KAWAI/projectbaseresearch',
)
_C_KMS = 299792.458


# ═══════════════════════════════════════════════════════════
# 좌표 입력 파서 (소수 도 / 시분초 HMS / 도분초 DMS 모두 허용)
# ═══════════════════════════════════════════════════════════

def parse_ra_deg(text) -> float:
    """적경 → 도.  '266.4'(도), '17h45m40s', '17:45:40'(시), '266.4d'(도)."""
    s = str(text).strip()
    if not s:
        raise ValueError('적경이 비어 있습니다')
    low = s.lower()
    if 'h' in low or (':' in s and 'd' not in low):
        return float(Angle(s, unit=u.hourangle).to_value(u.deg)) % 360.0
    return float(Angle(s, unit=u.deg).to_value(u.deg)) % 360.0


def parse_dec_deg(text) -> float:
    """적위 → 도.  '-28.9', '-29d00m28s', '-29:00:28', "-29°00'28\"" ."""
    s = str(text).strip()
    if not s:
        raise ValueError('적위가 비어 있습니다')
    v = float(Angle(s, unit=u.deg).to_value(u.deg))
    if not -90.0 <= v <= 90.0:
        raise ValueError('적위는 −90° ~ +90° 범위여야 합니다')
    return v


# ═══════════════════════════════════════════════════════════
# JSON 정리
# ═══════════════════════════════════════════════════════════

def clean(obj):
    """numpy·NaN 섞인 값을 JSON 안전한 파이썬 기본형으로."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return clean(obj.tolist())
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, Path):
        return str(obj)
    return obj


def _f32_b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype=np.float32).tobytes()).decode('ascii')


class ApiError(Exception):
    """사용자에게 그대로 보여줄 오류 메시지."""


# ═══════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════

class Api:
    """프런트엔드가 호출하는 백엔드. 상태(설정·프로젝트·합성 데이터)를 보관."""

    def __init__(self, emit: Optional[Callable[[str, dict], None]] = None):
        self._emit = emit or (lambda name, payload: None)
        self.cfg = Config.get()
        self.proj = get_project()
        self._synthetic: list[dict] = []
        self._geom_cache: dict[int, dict] = {}
        self._last: Optional[dict] = None

    # ── 디스패치 ─────────────────────────────────────────────

    def dispatch(self, method: str, args: Optional[dict] = None) -> dict:
        """{'ok': True, 'data': ...} 또는 {'ok': False, 'error': '...'}"""
        fn = getattr(self, f'api_{method}', None)
        if fn is None:
            return {'ok': False, 'error': f'알 수 없는 요청: {method}'}
        try:
            return {'ok': True, 'data': clean(fn(**(args or {})))}
        except ApiError as e:
            return {'ok': False, 'error': str(e)}
        except Exception as e:                       # 예상 못 한 오류 — 상세는 콘솔로
            traceback.print_exc()
            return {'ok': False, 'error': f'{type(e).__name__}: {e}'}

    # ── 상태 / 설정 ──────────────────────────────────────────

    def _config_dict(self) -> dict:
        c = self.cfg
        return dict(
            obs_name=c.obs_name, obs_lat=c.obs_lat, obs_lon=c.obs_lon,
            obs_height_m=c.obs_height_m, center_freq_hz=c.center_freq_hz,
            sample_rate=c.sample_rate, nfft=c.nfft, T_sys=c.T_sys, G_sys=c.G_sys,
            nside=c.nside, temp_method=c.temp_method, theme=c.theme,
            reduce_motion=c.reduce_motion, fg_scale=c.fg_scale, ui=c.ui,
            projects_dir=str(c.projects_dir_path), data_dir=str(c.data_dir_path),
            velocity_resolution_kms=c.velocity_resolution_kms,
        )

    def _project_dict(self) -> Optional[dict]:
        p = self.proj
        if not p.is_open:
            return None
        n_peaks = sum(len(o.get('spiral_peaks', [])) for o in p.observations)
        hits = p.hit_map
        return dict(
            name=p.name, path=str(p.path), nside=p.nside, meta=p.meta,
            obs_count=p.obs_count, peak_count=n_peaks,
            pixels_observed=int((hits > 0).sum()) if hits is not None else 0,
            npix=12 * p.nside ** 2,
        )

    def api_state(self) -> dict:
        try:
            import mocpy  # noqa: F401
            has_moc = True
        except Exception:
            has_moc = False
        from foreground_processing import find_foreground_fits
        return dict(
            app=dict(name=APP_NAME, name_ko=APP_NAME_KO, version=APP_VERSION, credits=CREDITS),
            config=self._config_dict(),
            project=self._project_dict(),
            recent=self._recent(),
            features=dict(mocpy=has_moc, fg_fits=find_foreground_fits() is not None),
            constants=dict(R0=R_SUN_KPC, V0=V_CIRC_KMS, HI_FREQ_HZ=HI_FREQ_HZ),
            synthetic_count=len(self._synthetic),
            has_last=self._last is not None,
        )

    _CONFIG_TYPES = dict(
        obs_name=str, obs_lat=float, obs_lon=float, obs_height_m=float,
        center_freq_hz=float, sample_rate=float, nfft=int, T_sys=float, G_sys=float,
        nside=int, temp_method=str, theme=str, reduce_motion=bool, fg_scale=float,
        ui=dict,
    )

    def api_config_update(self, **changes) -> dict:
        for k, v in changes.items():
            typ = self._CONFIG_TYPES.get(k)
            if typ is None:
                raise ApiError(f'바꿀 수 없는 설정: {k}')
            try:
                val = typ(v)
            except (TypeError, ValueError):
                raise ApiError(f'{k} 값이 올바르지 않습니다: {v!r}')
            if k == 'obs_lat' and not -90 <= val <= 90:
                raise ApiError('위도는 −90 ~ 90° 여야 합니다')
            if k == 'obs_lon' and not -180 <= val <= 360:
                raise ApiError('경도는 −180 ~ 360° 여야 합니다')
            if k == 'nside' and val not in (1, 2, 4, 8, 16, 32, 64, 128):
                raise ApiError('nside 는 2의 거듭제곱(1~128)이어야 합니다')
            if k == 'nfft' and (val < 64 or val & (val - 1)):
                raise ApiError('nfft 는 64 이상의 2의 거듭제곱이어야 합니다')
            if k in ('T_sys', 'sample_rate', 'center_freq_hz', 'G_sys') and val <= 0:
                raise ApiError(f'{k} 는 양수여야 합니다')
            if k == 'temp_method' and val not in ('peak', 'integral', 'mean', 'median'):
                raise ApiError('대푯값 방식이 올바르지 않습니다')
            if k == 'theme' and val not in ('dark', 'light', 'system'):
                raise ApiError('테마 값이 올바르지 않습니다')
            if k == 'ui':
                merged = dict(self.cfg.ui)
                merged.update(val)
                val = merged
            setattr(self.cfg, k, val)
        if 'theme' in changes:
            self.cfg.dark_mode = self.cfg.theme != 'light'
        self.cfg.save()
        return self._config_dict()

    # ── 프로젝트 ─────────────────────────────────────────────

    def _remember(self, path: Path) -> None:
        p = str(Path(path).resolve())
        rec = [x for x in self.cfg.recent_projects if x != p]
        self.cfg.recent_projects = [p] + rec[:9]
        self.cfg.save()

    @staticmethod
    def _peek_project(path: Path) -> Optional[dict]:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            meta = data.get('meta', {})
            obs = data.get('observations', [])
            if not isinstance(obs, list):
                return None
            return dict(path=str(path), name=meta.get('name', path.stem),
                        obs=len(obs), nside=meta.get('nside'),
                        created=meta.get('created', ''),
                        mtime=path.stat().st_mtime,
                        peaks=sum(len(o.get('spiral_peaks', [])) for o in obs))
        except Exception:
            return None

    def _recent(self) -> list:
        out = []
        for p in self.cfg.recent_projects:
            info = self._peek_project(Path(p)) if Path(p).is_file() else None
            if info:
                out.append(info)
        return out

    def api_projects_list(self) -> dict:
        seen, items = set(), []
        for info in self._recent():
            seen.add(info['path']); items.append(dict(info, recent=True))
        d = self.cfg.projects_dir_path
        for f in sorted(d.glob('*.json'), key=lambda x: -x.stat().st_mtime):
            key = str(f.resolve())
            if key in seen:
                continue
            info = self._peek_project(f)
            if info:
                info['path'] = key
                items.append(dict(info, recent=False))
        return dict(items=items, dir=str(d))

    def api_project_new(self, name: str, path: Optional[str] = None) -> dict:
        name = (name or '').strip()
        if not name:
            raise ApiError('프로젝트 이름을 입력하세요')
        if path:
            target = Path(path)
        else:
            safe = ''.join(ch for ch in name if ch not in '\\/:*?"<>|').strip() or 'project'
            target = self.cfg.projects_dir_path / f'{safe}.json'
            i = 2
            while target.exists():
                target = self.cfg.projects_dir_path / f'{safe} ({i}).json'
                i += 1
        if target.suffix.lower() != '.json':
            target = target.with_suffix('.json')
        self.proj.create(target, name=name)
        self._remember(target)
        self._geom_cache.clear()
        return self.api_state()

    def api_project_open(self, path: str) -> dict:
        p = Path(path)
        if not p.is_file():
            raise ApiError(f'파일이 없습니다: {p}')
        try:
            self.proj.open(p)
        except Exception as e:
            raise ApiError(f'프로젝트를 열 수 없습니다 — {e}')
        self._remember(p)
        return self.api_state()

    def api_project_close(self) -> dict:
        self.proj.close()
        return self.api_state()

    def api_project_forget(self, path: str) -> dict:
        p = str(Path(path).resolve())
        self.cfg.recent_projects = [x for x in self.cfg.recent_projects if x != p]
        self.cfg.save()
        return self.api_projects_list()

    # ── 관측 목록 ────────────────────────────────────────────

    def api_observations(self) -> dict:
        if not self.proj.is_open:
            return dict(items=[])
        obs = self.proj.observations
        if not obs:
            return dict(items=[])
        ra = np.array([o['ra'] for o in obs], float)
        dec = np.array([o['dec'] for o in obs], float)
        gal = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame='icrs').galactic
        hp = HEALPix(nside=self.proj.nside, order='ring', frame='icrs')
        pix = hp.lonlat_to_healpix(ra * u.deg, dec * u.deg)
        items = []
        for i, o in enumerate(obs):
            items.append(dict(
                index=i, ra=o['ra'], dec=o['dec'],
                l=float(gal.l.deg[i]), b=float(gal.b.deg[i]),
                time=o.get('obs_time', ''), file=o.get('bin_file', ''),
                T=o.get('T_brightness'), T_peak=o.get('T_b_peak', o.get('T_b_raw')),
                W=o.get('W_HI_K_kms'), v=o.get('v_radial_kms'),
                n_peaks=len(o.get('spiral_peaks', [])),
                peaks=[dict(v=p.get('v_lsr_kms'), T=p.get('T_b_peak'))
                       for p in o.get('spiral_peaks', [])],
                pixel=int(pix[i]), source=o.get('source', 'file' if o.get('bin_file') else ''),
            ))
        return dict(items=items)

    def api_observation_delete(self, index: int) -> dict:
        if not self.proj.is_open:
            raise ApiError('열린 프로젝트가 없습니다')
        self.proj.remove_observation(int(index))
        return self.api_state()

    # ── 관측 실행 ────────────────────────────────────────────

    def api_parse_coords(self, ra: str, dec: str) -> dict:
        try:
            r, d = parse_ra_deg(ra), parse_dec_deg(dec)
        except Exception as e:
            raise ApiError(f'좌표 형식 오류 — {e}')
        l, b = icrs_to_galactic(r, d)
        return dict(ra=r, dec=d, l=l, b=b)

    def api_run_observation(self, ra: str, dec: str, obs_time: str = '',
                            source: str = 'sim', file_path: str = '',
                            temp_method: Optional[str] = None,
                            seed: Optional[int] = None) -> dict:
        try:
            ra_deg, dec_deg = parse_ra_deg(ra), parse_dec_deg(dec)
        except Exception as e:
            raise ApiError(f'좌표 형식 오류 — {e}')
        obs_time = (obs_time or '').strip() or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        try:
            datetime.fromisoformat(obs_time.replace('Z', ''))
        except ValueError:
            raise ApiError('관측 시각 형식은 YYYY-MM-DDTHH:MM:SS (UTC) 입니다')

        wav = bin_ = None
        if source == 'file':
            if not file_path:
                raise ApiError('SDR 데이터 파일을 선택하세요')
            fp = Path(file_path)
            if not fp.is_file():
                raise ApiError(f'파일이 없습니다: {fp.name}')
            if fp.suffix.lower() == '.wav':
                wav = str(fp)
            else:
                bin_ = str(fp)
        cfg = self.cfg
        method = temp_method or cfg.temp_method
        t0 = time.perf_counter()

        def step(name):
            self._emit('progress', dict(step=name, t=time.perf_counter() - t0))

        result = process_observation(
            ra_deg=ra_deg, dec_deg=dec_deg, obs_time=obs_time,
            obs_lat=cfg.obs_lat, obs_lon=cfg.obs_lon, obs_height_m=cfg.obs_height_m,
            bin_filepath=bin_, wav_filepath=wav,
            center_freq_hz=cfg.center_freq_hz, sample_rate=cfg.sample_rate,
            nfft=cfg.nfft, T_sys=cfg.T_sys, G_sys=cfg.G_sys,
            temp_method=method, seed=seed, progress=step,
        )
        result['obs_time'] = obs_time
        result['source'] = 'file' if source == 'file' else 'sim'
        result['temp_method'] = method

        step('peaks')
        arm = analyze_observation(result)
        step('distance')
        peaks = []
        for p in arm.peaks:
            c = peak_candidates(p.l_deg, p.b_deg, p.v_lsr_kms)
            dist = velocity_to_distance(p.v_lsr_kms, p.l_deg, p.b_deg)
            peaks.append(dict(
                v=p.v_lsr_kms, T=p.T_b_peak, f_ghz=p.freq_hz / 1e9,
                d_near=p.d_near_kpc, d_far=p.d_far_kpc, R=dist['R_kpc'],
                ambiguous=c['ambiguous'], valid=c['valid'],
                cands=[dict(kind=q['kind'], d=q['d'], x=q['x'], y=q['y']) for q in c['cands']],
            ))
        gc = galactocentric_velocity(ra_deg, dec_deg, result['v_radial_kms'])

        saved = False
        if self.proj.is_open and result['success']:
            step('save')
            self.proj.add_observation(result, bin_filepath=file_path or '')
            last = self.proj.observations[-1]
            last['spiral_peaks'] = [
                {k: (float(v) if isinstance(v, (float, np.floating)) else
                     bool(v) if isinstance(v, (bool, np.bool_)) else v)
                 for k, v in p.__dict__.items()}
                for p in arm.peaks
            ]
            self.proj.save()
            saved = True

        # 스펙트럼 (주파수·속도축 공통)
        mask = result['freqs_corrected'] > 0
        f = result['freqs_corrected'][mask]
        power_db = 10 * np.log10(result['power'][mask] + 1e-30)
        tb = result['T_b_spectrum']
        v_axis = _C_KMS * (HI_FREQ_HZ - f) / HI_FREQ_HZ
        order = np.argsort(f)
        spectrum = dict(
            f_ghz=(f[order] / 1e9).round(9), v_kms=v_axis[order].round(4),
            power_db=power_db[order].round(4), tb=np.asarray(tb)[order].round(5),
        )
        summary = dict(
            ra=ra_deg, dec=dec_deg, l=result['l_deg'], b=result['b_deg'],
            obs_time=obs_time, source=result['source'], temp_method=method,
            file=Path(file_path).name if file_path else '',
            v_corr=result['v_radial_kms'], T=result['T_brightness'],
            T_peak=result['T_b_peak'], W=result['W_HI_K_kms'],
            success=bool(result['success']),
            v_tan=gc['v_tangent_kms'],
            d_near=gc['kinematic_distance_near_kpc'], d_far=gc['kinematic_distance_far_kpc'],
            in_inner=gc['in_inner_galaxy'],
            elapsed=time.perf_counter() - t0, saved=saved,
        )
        step('done')
        self._last = dict(summary=summary, spectrum=spectrum, peaks=peaks)
        return dict(self._last, project=self._project_dict())

    def api_last_result(self) -> Optional[dict]:
        return self._last

    # ── 하늘 지도 ────────────────────────────────────────────

    def _nside(self) -> int:
        return self.proj.nside if self.proj.is_open else self.cfg.nside

    def api_sky_geometry(self, nside: Optional[int] = None) -> dict:
        """HEALPix 픽셀 경계 (적도·은하 좌표). float32 base64 로 전송."""
        nside = int(nside or self._nside())
        if nside in self._geom_cache:
            return self._geom_cache[nside]
        step = 2 if nside >= 16 else 3 if nside >= 8 else 6 if nside >= 4 else 10
        hp = HEALPix(nside=nside, order='ring', frame='icrs')
        idx = np.arange(hp.npix)
        lon, lat = hp.boundaries_lonlat(idx, step)
        lon = lon.to_value(u.deg); lat = lat.to_value(u.deg)
        gal = SkyCoord(ra=lon.ravel() * u.deg, dec=lat.ravel() * u.deg, frame='icrs').galactic
        gl = gal.l.deg.reshape(lon.shape); gb = gal.b.deg.reshape(lat.shape)
        c_ra, c_dec = hp.healpix_to_lonlat(idx)
        cg = SkyCoord(ra=c_ra, dec=c_dec, frame='icrs').galactic
        out = dict(
            nside=nside, npix=int(hp.npix), nv=int(lon.shape[1]),
            eq=_f32_b64(np.stack([lon, lat], -1)),
            gal=_f32_b64(np.stack([gl, gb], -1)),
            centers_eq=_f32_b64(np.stack([c_ra.to_value(u.deg), c_dec.to_value(u.deg)], -1)),
            centers_gal=_f32_b64(np.stack([cg.l.deg, cg.b.deg], -1)),
            pix_deg=float(np.degrees(np.sqrt(4 * np.pi / hp.npix))),
        )
        self._geom_cache[nside] = out
        return out

    def api_sky(self) -> dict:
        nside = self._nside()
        npix = 12 * nside ** 2
        if self.proj.is_open and self.proj.sky_map is not None:
            vals, hits = self.proj.sky_map, self.proj.hit_map
        else:
            vals, hits = np.full(npix, np.nan), np.zeros(npix, int)
        observed = np.flatnonzero(hits > 0)
        return dict(nside=nside, npix=npix,
                    values=[float(vals[i]) for i in observed],
                    hits=[int(hits[i]) for i in observed],
                    pixels=observed.tolist(),
                    project=self.proj.is_open)

    def api_foreground(self) -> dict:
        from foreground_processing import get_foreground_map
        nside = self._nside()
        fg, method = get_foreground_map(nside)
        return dict(nside=nside, method=method, scale=self.cfg.fg_scale,
                    values=_f32_b64(np.nan_to_num(fg, nan=0.0)))

    # ── 은하 지도 / 나선팔 ───────────────────────────────────

    def _collect_peaks(self, include_obs: bool = True, include_synth: bool = True) -> list:
        peaks = []
        if include_obs and self.proj.is_open:
            for i, o in enumerate(self.proj.observations):
                for p in o.get('spiral_peaks', []):
                    if not all(k in p for k in ('l_deg', 'b_deg', 'v_lsr_kms')):
                        continue
                    peaks.append(dict(l_deg=p['l_deg'], b_deg=p['b_deg'],
                                      v_lsr_kms=p['v_lsr_kms'],
                                      T_b_peak=p.get('T_b_peak', np.nan),
                                      src='obs', obs=i))
        if include_synth:
            peaks.extend(dict(p, obs=-1) for p in self._synthetic)
        return peaks

    def api_spiral_infer(self, b_max_deg: float = 30.0, ambiguity: str = 'auto',
                         tol_lnr: float = 0.08, pitch_min: float = 5.0,
                         pitch_max: float = 25.0, min_points: int = 4,
                         use_obs: bool = True, use_synth: bool = True) -> dict:
        if ambiguity not in ('auto', 'near', 'far'):
            raise ApiError('ambiguity 는 auto / near / far 중 하나')
        peaks = self._collect_peaks(use_obs, use_synth)
        res = infer_spiral_arms(
            peaks, b_max_deg=float(b_max_deg), ambiguity=ambiguity,
            tol_lnr=float(tol_lnr), pitch_range=(float(pitch_min), float(pitch_max)),
            min_points_per_arm=int(min_points),
        )
        res['n_obs_peaks'] = sum(1 for p in peaks if p['src'] == 'obs')
        res['n_synth_peaks'] = sum(1 for p in peaks if p['src'] != 'obs')
        return res

    def api_spiral_model(self) -> dict:
        arms = [dict(name=k, xy=np.column_stack(v['xy']).round(4))
                for k, v in get_reference_spiral_arms().items()]
        sightlines = []
        if self.proj.is_open and self.proj.observations:
            seen = set()
            for i, o in enumerate(self.proj.observations):
                l, b = (o['l_deg'], o['b_deg']) if 'l_deg' in o else icrs_to_galactic(o['ra'], o['dec'])
                key = (round(l, 1), round(b, 1))
                if key in seen:
                    continue
                seen.add(key)
                sightlines.append(dict(l=l, b=b, obs=i, crossings=predict_sightline_crossings(l, b)))
        return dict(arms=arms, sightlines=sightlines, R0=R_SUN_KPC, V0=V_CIRC_KMS,
                    reference='Hou & Han (2014) 로그 나선 근사')

    def api_sightline(self, l: float, b: float = 0.0) -> dict:
        return dict(l=l, b=b, crossings=predict_sightline_crossings(float(l), float(b)))

    def api_synthetic_generate(self, n_dirs: int = 48, v_noise: float = 7.0,
                               seed: Optional[int] = None) -> dict:
        n_dirs = int(max(4, min(400, n_dirs)))
        self._synthetic = synthetic_arm_peaks(n_dirs=n_dirs, v_noise_kms=float(v_noise),
                                              seed=None if seed in (None, '') else int(seed))
        return dict(count=len(self._synthetic), n_dirs=n_dirs, v_noise=v_noise)

    def api_synthetic_clear(self) -> dict:
        self._synthetic = []
        return dict(count=0)

    # ── 내보내기 ─────────────────────────────────────────────

    def api_export_fits(self, path: str) -> dict:
        if not self.proj.is_open:
            raise ApiError('열린 프로젝트가 없습니다')
        out = self.proj.export_fits(path)
        return dict(path=str(out))

    def api_export_moc(self, path: str) -> dict:
        if not self.proj.is_open:
            raise ApiError('열린 프로젝트가 없습니다')
        from moc_manager import MocManager
        mm = MocManager(self.proj.nside)
        mm.add_from_project(self.proj.observations)
        try:
            out = mm.save(path)
        except RuntimeError as e:
            raise ApiError(str(e))
        return dict(path=str(out), coverage=mm.coverage_fraction())


if __name__ == '__main__':
    api = Api(emit=lambda n, p: print('  ·', n, p))
    print(json.dumps(api.dispatch('state')['data']['constants']))
    r = api.dispatch('run_observation', dict(ra='17h45m40s', dec='-29d00m28s', seed=1))
    print('run ok:', r['ok'], r.get('error'))
    if r['ok']:
        s = r['data']['summary']
        print(f"  l={s['l']:.1f} b={s['b']:.1f} T={s['T']:.2f}K peaks={len(r['data']['peaks'])}")
    g = api.dispatch('sky_geometry', dict(nside=2))
    print('geom ok:', g['ok'], g['data']['nv'] if g['ok'] else g)
    api.dispatch('synthetic_generate', dict(n_dirs=40, seed=3))
    inf = api.dispatch('spiral_infer')
    print('infer ok:', inf['ok'], inf['data']['n_arms'] if inf['ok'] else inf)
