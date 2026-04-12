from astropy.io import fits

def read_fits_data(filepath):
    with fits.open(filepath) as hdul:
        data = hdul[1].data
        header = hdul[1].header
        return data.field(0), header['NSIDE'], header.get('ORDERING', 'RING')
