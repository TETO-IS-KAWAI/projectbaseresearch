import pyqtgraph as pg
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

class SkyAppWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sky Data Explorer")
        self.resize(1000, 600)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setAspectLocked(True)
        self.plot_widget.setBackground('k')
        self.layout.addWidget(self.plot_widget)
