import astropy.io
import astropy.io.fits as fits
import sys
import io
import os
import json

class save_proto:
    def __init__(self, config_path):
        with open(config_path, 'w', encoding='utf-8') as f:
            self.cfg=json.load(f)

