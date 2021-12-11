import datetime
import json
import operator
import os
import random
import sys

import PIL.Image
import numpy as np
from PIL import Image
# %pip install git+git://github.com/waspinator/pycococreator.git@0.2.0
from pycococreatortools import pycococreatortools

"""Overlay transparent foreground images onto background images.
"""

OBJ_PER_BG = 1  # how often a background image is "recycled" with a different object


def main(root_dir, output_format: str = "jpg"):
    # folder structure of the dataset
    background_folder = os.path.join(root_dir, "backgrounds")
    foreground_folder = os.path.join(root_dir, "renders")
    img_output_folder = os.path.join(root_dir, "image")
    json_folder = os.path.join(root_dir, "annotations")

    coco_output = {
        "info": {"description": None,
                 "url": "",
                 "version": 1.0,
                 "year": 2021,
                 "contributor": "Rene Erler, Philemon Schoepf, Lukas Walter",
                 "date_created": datetime.datetime.timestamp(datetime.datetime.now())
                 },
        "licenses": "",
        "categories": json.load(open(os.path.join(json_folder, "categories.json"))),
        "images": [],
        "annotations": []
    }

    backgrounds = [f for f in os.listdir(background_folder) if f.__contains__(".jpg")]
    foregrounds = [f for f in os.listdir(foreground_folder) if f.__contains__(".png")]
    for bg_id, bg in enumerate(backgrounds):
        with Image.open(os.path.join(background_folder, bg), mode="r") as bg_img:
            bg_img = bg_img.convert("RGBA")
            for fg_id, fg in enumerate(random.sample(foregrounds, OBJ_PER_BG)):
                with Image.open(os.path.join(foreground_folder, fg), mode="r") as fg_img:
                    fg_img = fg_img.convert("RGBA")

                    # TODO put pose in annotations
                    pose = json.load(open(os.path.join(json_folder, os.path.splitext(fg)[0] + ".json")))
                    position = (pose['position']['x'], pose['position']['y'], pose['position']['z'])
                    orientation = (pose['orientation']['w'], pose['orientation']['x'],
                                   pose['orientation']['y'], pose['orientation']['z'])

                    # running image id
                    img_id = bg_id * OBJ_PER_BG + fg_id

                    # pad the foreground image to same size as background
                    offset = random_offset(bg_img, fg_img)
                    padded_fg = pad(fg_img, offset, target_size=bg_img.size)

                    # blend images together and convert back to RGB
                    blend_img = Image.alpha_composite(bg_img, padded_fg).convert("RGB")

                    output_filename = os.path.splitext(bg)[0] + os.path.splitext(fg)[0] + "." + output_format
                    blend_img.save(os.path.join(img_output_folder, output_filename))

                    # create a binary (black/white) mask as sparse array
                    mask = padded_fg.copy().convert("L")
                    mask = np.asfortranarray(mask, bool)

                    # make an annotation string
                    category_info = {'id': pose["category"], 'is_crowd': False}
                    coco_output["images"].append(pycococreatortools.create_image_info(
                        image_id=img_id, file_name=output_filename, image_size=blend_img.size))
                    # TODO support multiple objects on one image
                    coco_output["annotations"].append(pycococreatortools.create_annotation_info(
                        img_id, img_id, category_info, mask))

    with open(os.path.join(json_folder, "3DprintingDataset.json"), 'w') as output_json_file:
        json.dump(coco_output, output_json_file)


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
    dataset_root = sys.argv[1]
    if not os.path.exists(dataset_root):
        os.makedirs(dataset_root)
    main(dataset_root)
    # stop = time.perf_counter()
    # print(f"Elapsed: {stop - start} seconds")
