import operator
import random
import time

import PIL.Image
from PIL import Image
import os
import sys

"""Overlay transparent foreground images onto background images.
"""


def main(background_folder: str, foreground_folder: str, output_folder: str, output_format: str = "jpg"):
    backgrounds = [f for f in os.listdir(background_folder) if f.__contains__(".jpg")]
    foregrounds = [f for f in os.listdir(foreground_folder) if f.__contains__(".png")]
    for bg in backgrounds:
        with Image.open(os.path.join(os.getcwd(), background_folder, bg), mode="r") as bg_img:
            bg_img = bg_img.convert("RGBA")
            for fg in random.sample(foregrounds, 1):
                with Image.open(os.path.join(os.getcwd(), foreground_folder, fg), mode="r") as fg_img:
                    fg_img = fg_img.convert("RGBA")

                    # pad the foreground image to same size as background
                    offset = random_offset(bg_img, fg_img)
                    padded_fg = pad(fg_img, offset, target_size=bg_img.size)

                    # blend images together and convert back to RGB
                    blend_img = Image.alpha_composite(bg_img, padded_fg).convert("RGB")

                    output_filename = os.path.splitext(bg)[0] + os.path.splitext(fg)[0] + "." + output_format
                    blend_img.save(os.path.join(os.getcwd(), output_folder, output_filename))


def random_offset(bg_img: PIL.Image.Image, fg_img: PIL.Image.Image):
    """
    Calculate a random offset within the possible limits of 2 images
    Parameters:
        bg_img: background image
        fg_img: foreground image, must be smaller than background
    Returns:
        2-tuple of x- and y- offset of the left upper corner of the foreground image
    """
    max_offset = map(operator.sub, bg_img.size, fg_img.size)
    return tuple(map(lambda x: random.randint(0, x), max_offset))


def pad(img: PIL.Image.Image, position: tuple, target_size=(640, 480)):
    """
    Draw a blank image and paste a foreground at a given position.
    Parameters:
        img: image to pad
        position: 2-tuple where the upper left corner will be in the padded image
        target_size: 2-tuple, size of the result image
    Returns:
        padded image
    """
    result = Image.new("RGBA", target_size)
    result.paste(img, position)
    return result


if __name__ == "__main__":
    # start = time.perf_counter()
    if not os.path.exists(sys.argv[3]):
        os.makedirs(sys.argv[3])
    main(
        os.path.join(os.getcwd(), sys.argv[1]),
        os.path.join(os.getcwd(), sys.argv[2]),
        os.path.join(os.getcwd(), sys.argv[3]))
    # stop = time.perf_counter()
    # print(f"Elapsed: {stop - start} seconds")
