import cv2, imagehash
from PIL import Image
import numpy as np
from . import utils

class _pHash(metaclass=utils.Singleton):
    @staticmethod
    def img_to_phash(img:np.ndarray, input_colorspace='BGR', hash_size=32, highfreq_factor=4, crop_scale=1) -> np.ndarray:
        '''
        Calculate the pHash for `img`, grayscaled.
        Image will be resized internally, new image size is calculated as `hash_size * highfreq_factor`

        :param img: image in ndarray format
        :param input_colorspace: img colorspace
        :param hash_size: passed to `imagehash.phash()`
        :param highfreq_factor: passed to `imagehash.phash()`
        :returns: phash value as a flatten binary np.ndarray
        '''
        if img is None:
            return {'hash': np.array(None)}

        if crop_scale < 1:
            img = utils.crop_scale_img(img, scale=crop_scale)

        # convert to grayscale
        if input_colorspace.upper() == 'BGR':
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        elif input_colorspace.upper() == 'RGB':
            img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # convert to PIL image
        # there is no need to explicitly resize the image since the pHash library does so automatically.
        img = Image.fromarray(img)
        res = imagehash.phash(img, hash_size, highfreq_factor)
        return res.hash.flatten()

pHash = _pHash()
