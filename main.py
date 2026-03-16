# import sys
# import numpy as np
# from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
# import pyqtgraph.opengl as gl

# class MainWindow(QMainWindow):
#     def __init__(self):
#         super().__init__()
#         self.setWindowTitle("PySide6 + PyQtGraph 3D Sky")
#         self.resize(800, 600)

#         # 1. 메인 레이아웃 설정
#         central_widget = QWidget()
#         self.setCentralWidget(central_widget)
#         layout = QVBoxLayout(central_widget)

#         # 2. PyQtGraph 3D 위젯 생성
#         self.view = gl.GLViewWidget()
#         layout.addWidget(self.view)

#         # 3. 그리드 추가 (바닥면 대신 천구 느낌을 위해)
#         # gz = gl.GLGridItem()
#         # self.view.addItem(gz)

#         # 4. HEALPix를 흉내낸 3D 구체 (ScatterPlot으로 별자리처럼 표현)
#         self.create_sky()

#     def create_sky(self):
#         # 가상의 픽셀 데이터 (1000개의 별)
#         n = 1000
#         pos = np.random.normal(size=(n, 3))
#         # 반지름이 10인 구 표면에 배치
#         pos /= (pos**2).sum(axis=1)[:, np.newaxis]**0.5
#         pos *= 10 
        
#         # 색상 설정 (RGBA)
#         color = np.ones((n, 4))
        
#         # 3. 3D 점(Scatter) 그리기
#         sp = gl.GLScatterPlotItem(pos=pos, color=color, size=2, pxMode=True)
#         self.view.addItem(sp)

# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     window = MainWindow()
#     window.show()
#     sys.exit(app.exec())

import sys
import numpy as np
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
import pyqtgraph.opengl as gl

# 1. 내부 시점에 최적화된 커스텀 뷰 위젯
class SkyViewWidget(gl.GLViewWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.opts['fov'] = 60  # 기본 시야각 (도 단위)
        self.min_fov = 10      # 최대 확대 (좁은 시야)
        self.max_fov = 120     # 최대 축소 (넓은 시야)

    def wheelEvent(self, ev):
        # 휠 방향에 따라 시야각(FOV) 증감
        delta = ev.angleDelta().y()
        if delta > 0:
            new_fov = self.opts['fov'] - 5  # 줌 인
        else:
            new_fov = self.opts['fov'] + 5  # 줌 아웃

        # 시야각 범위 제한 (너무 과하게 확대/축소되지 않도록)
        self.opts['fov'] = np.clip(new_fov, self.min_fov, self.max_fov)
        
        # 화면 갱신
        self.update()

class CelestialViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stellarium-style Inside View")
        self.resize(1000, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 커스텀 뷰 위젯 사용
        self.view = SkyViewWidget()
        self.view.setBackgroundColor('k')
        layout.addWidget(self.view)

        self.radius = 50 # 천구 반지름

        self.add_horizon()
        self.add_celestial_grid()
        
        # [핵심] 카메라를 구의 정중앙(0,0,0)에 배치
        # distance가 0에 가까울수록 내부 시점이 됩니다.
        self.view.setCameraPosition(distance=40, elevation=0, azimuth=0)
        
        # FOV(시야각)를 넓히면 내부에서 더 넓은 밤하늘이 보입니다.
        self.view.opts['fov'] = 70 

    def add_horizon(self):
        # 지평선 (반투명 원판)
        mesh_data = gl.MeshData.cylinder(rows=1, cols=60, radius=[self.radius, self.radius], length=0.1)
        horizon = gl.GLMeshItem(
            meshdata=mesh_data,
            smooth=True,
            color=(0.1, 0.4, 0.1, 0.2), # 더 투명하게
            shader='shaded',
            glOptions='translucent'
        )
        horizon.rotate(90, 1, 0, 0)
        self.view.addItem(horizon)

    def add_celestial_grid(self):
        line_color = (1, 1, 1, 0.3) # 내부에서 잘 보이도록 밝기 업
        
        # 위선/경선 그리기 로직 (동일)
        for lat in range(-90, 91, 15):
            phi = np.radians(lat)
            theta = np.linspace(0, 2 * np.pi, 100)
            x = self.radius * np.cos(phi) * np.cos(theta)
            y = self.radius * np.cos(phi) * np.sin(theta)
            z = np.full_like(x, self.radius * np.sin(phi))
            pts = np.column_stack([x, y, z])
            line = gl.GLLinePlotItem(pos=pts, color=line_color, width=1, antialias=True)
            self.view.addItem(line)

        for lon in range(0, 360, 30):
            theta = np.radians(lon)
            phi = np.linspace(-np.pi/2, np.pi/2, 100)
            x = self.radius * np.cos(phi) * np.cos(theta)
            y = self.radius * np.cos(phi) * np.sin(theta)
            z = self.radius * np.sin(phi)
            pts = np.column_stack([x, y, z])
            line = gl.GLLinePlotItem(pos=pts, color=line_color, width=1, antialias=True)
            self.view.addItem(line)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CelestialViewer()
    window.show()
    sys.exit(app.exec())