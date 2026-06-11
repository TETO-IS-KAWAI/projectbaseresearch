#new main(also temporary)
#library import
import sys
import os
import numpy

import astropy
import astropy_healpix
from astropy_healpix import HEALPix
from astropy.coordinates import SkyCoord
import astropy.units as astunits

import matplotlib
import matplotlib.pyplot as pyplot
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import PySide6
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

import pyqtgraph
import pyqtgraph.opengl as pygl

import tkinter

#HealPix viewer widget
class HealPixViewWidget(pygl.GLViewWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.opts['fov']=60
        self.min_fov=10
        self.max_fov=110

    def wheelEvent(self, ev):
        delta=ev.angleDelta().y()
        if delta>0:
            new_fov=self.opts['fov']+2
        else:
            new_fov=self.opts['fov']-2

        self.opts['fov']=numpy.clip(new_fov, self.min_fov, self.max_fov)
        self.update()

#processing data for HealPix
class HealPixDataProcessor(QThread):
    data_ready=Signal(numpy.ndarray)

    def run(self):
        nside=16
        hp=HEALPix(nside=nside, order='ring', frame='icrs')
        npix=hp.npix
        
        #pseudo data
        temperatures=numpy.random.normal(loc=2.7, scale=0.1, size=npix)
        self.data_ready.emit(temperatures)

#map data to HealPix and main HealPix viewer
class CelestialViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data Mapped to HealPix")
        self.resize(1500, 1000)
        #initial size

        #open widget
        central_widget=QWidget()
        self.setCentralWidget(central_widget)
        layout=QVBoxLayout(central_widget)

        #open viewer
        self.view=HealPixViewWidget()
        self.view.setBackgroundColor('white')
        layout.addWidget(self.view)

        #parameter
        self.radius=50 
        self.nside=16
        self.hp=HEALPix(nside=self.nside, order='ring', frame='icrs')

        self.addHorizon()
        self.addCelestialGrid()
        
        self.view.setCameraPosition(distance=40, elevation=0, azimuth=0)
        self.view.opts['fov']=70 

        #construct mesh bone
        self.meshInitializeHealPix()

        self.processor=HealPixDataProcessor()
        self.processor.data_ready.connect(self.updateSky) 
        self.processor.start()

    def meshInitializeHealPix(self):
        npix=self.hp.npix
        lon, lat=self.hp.boundaries_lonlat(numpy.arange(npix), step=1)

        #with rad
        lon_rad=lon.to_value('rad')
        lat_rad=lat.to_value('rad')
        
        #with cartesian
        x=self.radius*numpy.cos(lat_rad)*numpy.cos(lon_rad)
        y=self.radius*numpy.cos(lat_rad)*numpy.sin(lon_rad)
        z=self.radius*numpy.sin(lat_rad)
        
        #vertex matrix pixel
        self.vertices=numpy.column_stack([x.flatten(), y.flatten(), z.flatten()])
        
        #divide square into triangle
        self.faces=numpy.zeros((npix*2, 3), dtype=int)
        for i in range(npix):
            v0=i*4
            self.faces[i*2]=[v0, v0+1, v0+2]
            self.faces[i*2+1]=[v0, v0+2, v0+3]

        dummy_colors=numpy.ones((npix*2, 4))
        
        #make mesh data iterator and add to viewer
        self.mesh_data=pygl.MeshData(vertexes=self.vertices, faces=self.faces, faceColors=dummy_colors)
        
        #smooth — false for interface design usability
        self.sky_mesh=pygl.GLMeshItem(meshdata=self.mesh_data, smooth=False, shader='shaded', glOptions='translucent')
        self.view.addItem(self.sky_mesh)

    #horizon
    def addHorizon(self):
        mesh_data=pygl.MeshData.cylinder(rows=1, cols=60, radius=[self.radius, self.radius], length=0.1)
        horizon=pygl.GLMeshItem(meshdata=mesh_data, smooth=True, color=(0.1, 0.4, 0.1, 0.2), shader='shaded', glOptions='translucent')
        horizon.rotate(90, 1, 0, 0)
        self.view.addItem(horizon)

    def addCelestialGrid(self):
        line_color=(1, 1, 1, 0.3) 
        for lat in range(-90, 91, 15):
            phi=numpy.radians(lat)
            theta=numpy.linspace(0, 2*numpy.pi, 100)
            x=self.radius*numpy.cos(phi)*numpy.cos(theta)
            y=self.radius*numpy.cos(phi)*numpy.sin(theta)
            z=numpy.full_like(x, self.radius*numpy.sin(phi))
            pts=numpy.column_stack([x, y, z])
            line=pygl.GLLinePlotItem(pos=pts, color=line_color, width=1, antialias=True)
            self.view.addItem(line)

        for lon in range(0, 360, 30):
            theta=numpy.radians(lon)
            phi=numpy.linspace(-numpy.pi/2, numpy.pi/2, 100)
            x=self.radius*numpy.cos(phi)*numpy.cos(theta)
            y=self.radius*numpy.cos(phi)*numpy.sin(theta)
            z=self.radius*numpy.sin(phi)
            pts=numpy.column_stack([x, y, z])
            line=pygl.GLLinePlotItem(pos=pts, color=line_color, width=1, antialias=True)
            self.view.addItem(line)

    def updateSky(self, temperatures):
        #determine color by temperature
        norm=numpy.clip((temperatures - 2.5) / (3.0 - 2.5), 0, 1)
        pixel_colors=numpy.zeros((len(temperatures), 4))
        #red
        pixel_colors[:, 0]=norm
        #blue
        pixel_colors[:, 2]=1.0 - norm
        #alpha
        pixel_colors[:, 3]=1

        #multiple mesh triangle
        face_colors=numpy.repeat(pixel_colors, 2, axis=0)

        #update mesh color
        self.mesh_data.setFaceColors(face_colors)
        self.sky_mesh.setMeshData(meshdata=self.mesh_data)
