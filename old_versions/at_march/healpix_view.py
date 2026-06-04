from astropy.coordinates import EarthLocation, AltAz, SkyCoord
from astropy.time import Time
import astropy.units as u
import json
import numpy as np
from scipy.optimize import curve_fit
from astropy_healpix import HEALPix
from astropy.coordinates import EarthLocation, AltAz, SkyCoord
from astropy.time import Time
import astropy.units as u

class StellarEngine:
    def __init__(self, config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.cfg = json.load(f)
        
        self.c = self.cfg['physics_params']['c_mps']
        self.freqs_obs = np.array(self.cfg['physics_params']['freq_ghz']) * 1e9 # GHz -> Hz
        self.nside = self.cfg['physics_params']['nside']
        
        # 3. HEALPix 및 관측지 설정
        self.hp = HEALPix(nside=self.nside, order='ring')
        self.location = EarthLocation(
            lat=self.cfg['observation_site']['latitude'] * u.deg,
            lon=self.cfg['observation_site']['longitude'] * u.deg,
            height=self.cfg['observation_site']['altitude_meters'] * u.m
        )

    def planck_law(self, nu, T):
        h, k = 6.626e-34, 1.38e-23
        exponent = (h * nu) / (k * T)
        exponent = np.clip(exponent, None, 700)
        return (2 * h * nu**3) / (self.c**2 * (np.exp(exponent) - 1))

    def relativistic_doppler(self, nu_obs, intensity_obs, v):
        """상대론적 도플러 보정"""
        beta = v / self.c
        gamma = 1 / np.sqrt(1 - beta**2)
        nu_rest = nu_obs * gamma * (1 + beta) # 멀어지는 경우 (+)
        intensity_rest = intensity_obs * (nu_rest / nu_obs)**3
        return nu_rest, intensity_rest

    def run_fitting(self, raw_data_map, velocity_map):
        """전체 HEALPix 픽셀에 대해 보정 및 피팅 수행"""
        npix = self.hp.npix
        temp_results = np.zeros(npix)
        
        print(f"총 {npix}개 픽셀 피팅 시작...")
        
        for i in range(npix):
            v = velocity_map[i]
            obs_i = raw_data_map[i] # 해당 픽셀의 주파수별 세기 리스트
            
            # 1. 보정 (상대론적)
            nu_corr, i_corr = self.relativistic_doppler(self.freqs_obs, obs_i, v)
            
            # 2. 피팅
            try:
                popt, _ = curve_fit(
                    self.planck_law, nu_corr, i_corr,
                    p0=[self.cfg['fitting_options']['initial_temp']],
                    bounds=(self.cfg['fitting_options']['min_temp'], 
                            self.cfg['fitting_options']['max_temp'])
                )
                temp_results[i] = popt[0]
            except:
                temp_results[i] = 0
                
        return temp_results

    def get_screen_coordinates(self):
        """현재 시간 기준 픽셀들의 화면 좌표(Az, Alt) 계산"""
        now = Time.now()
        frame = AltAz(obstime=now, location=self.location)
        
        pix_indices = np.arange(self.hp.npix)
        coords = self.hp.pixel_to_skycoord(pix_indices)
        altaz = coords.transform_to(frame)
        
        return altaz.az.deg, altaz.alt.deg

# --- 사용 예시 ---
if __name__ == "__main__":
    engine = StellarEngine('config.json')
    
    # 가상의 데이터 (현업에서는 실제 관측 데이터 JSON/FITS 로드)
    dummy_raw_data = np.random.random((engine.hp.npix, len(engine.freqs_obs))) * 1e-18
    dummy_velocity = np.random.normal(3000000, 100000, engine.hp.npix) # 3000km/s
    
    # 1. 피팅 수행
    final_temps = engine.run_fitting(dummy_raw_data, dummy_velocity)
    
    # 2. 화면 좌표 계산
    az, alt = engine.get_screen_coordinates()
    
    print(f"피팅 완료. 첫 번째 픽셀 온도: {final_temps[0]:.2f} K")
    print(f"화면 표시 준비 완료 (해상도 {engine.cfg['display_settings']['window_width']} 기준)")

def get_observer_frame(config):
    # 1. 관측자 위치 설정 (위도, 경도, 고도)
    site = config['observation_site']
    location = EarthLocation(
        lat=site['latitude'] * u.deg, 
        lon=site['longitude'] * u.deg, 
        height=site['altitude_meters'] * u.m
    )
    
    # 2. 현재 시뮬레이션 시간 설정 (시간대 반영 가능)
    # 실제로는 현재 시간 혹은 설정된 시간을 가져옴
    now = Time.now() 
    
    # 3. 관측자 기준 좌표계(AltAz: 고도/방위각) 프레임 생성
    frame = AltAz(obstime=now, location=location)
    return frame

import numpy as np
from astropy_healpix import HEALPix

def project_pixels_to_screen(config, temp_map):
    # 설정 로드
    nside = config['simulation_params']['nside']
    hp = HEALPix(nside=nside, order='ring')
    frame = get_observer_frame(config)
    
    # 1. 모든 HEALPix 픽셀의 중심 좌표(SkyCoord) 가져오기
    pix_indices = np.arange(hp.npix)
    coords = hp.pixel_to_skycoord(pix_indices) # 천구 좌표(RA, Dec)
    
    # 2. 관측자 기준 좌표(고도, 방위각)로 변환
    altaz_coords = coords.transform_to(frame)
    
    # 3. 화면 투영 (간단한 수평 투영 예시)
    # 지평선 위(Alt > 0)에 있는 별들만 선별
    visible_mask = altaz_coords.alt.deg > 0
    visible_az = altaz_coords.az.deg[visible_mask]
    visible_alt = altaz_coords.alt.deg[visible_mask]
    visible_temps = temp_map[visible_mask]
    
    # 4. 화면 해상도에 맞게 스케일링 (1920x1080)
    w = config['display_settings']['window_width']
    h = config['display_settings']['window_height']
    
    # 방위각(0~360) -> X(0~W), 고도(0~90) -> Y(H~0)
    screen_x = (visible_az / 360.0) * w
    screen_y = h - (visible_alt / 90.0) * h
    
    return screen_x, screen_y, visible_temps
