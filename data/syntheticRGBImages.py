import operator
import random
import time

import PIL.Image
from PIL import Image
import os
import sys

"""Overlay transparent forground images onto background images.
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
                    # TODO implement random offsetting
                    # TODO implement auto-resizing (both imgs need same size before merging)
                    x_offset, y_offset = random_offset(bg_img, fg_img)
                    blend_img = Image.alpha_composite(bg_img, fg_img).convert("RGB")

                    output_filename = os.path.splitext(bg)[0] + os.path.splitext(fg)[0] + "." + output_format
                    blend_img.save(os.path.join(os.getcwd(), output_folder, output_filename))


def random_offset(bg_img: PIL.Image.Image, fg_img: PIL.Image.Image):
    max_offset = map(operator.sub, bg_img.size, fg_img.size)
    return tuple(map(lambda x: random.randint(0, x), max_offset))


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
