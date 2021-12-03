import sys
import os
import random
import shutil


SAMPLESIZE = 1000


def main(root: str):
    imgs = [f for f in os.listdir(os.path.join(root, "image")) if f.__contains__(".png")]
    imgs.sort()
    depths = [f for f in os.listdir(os.path.join(root, "depth")) if f.__contains__(".png")]
    depths.sort()

    ds_imgs, ds_depths = downsample(imgs, depths, k=SAMPLESIZE)
    if not os.path.exists(os.path.join(root, "ds_image")):
        os.makedirs(os.path.join(root, "ds_image"))
    if not os.path.exists(os.path.join(root, "ds_depth")):
        os.makedirs(os.path.join(root, "ds_depth"))

    for img in ds_imgs:
        shutil.copy2(os.path.join(root, "image", img), os.path.join(root, "ds_image", img))
    for img in ds_depths:
        shutil.copy2(os.path.join(root, "depth", img), os.path.join(root, "ds_depth", img))


def downsample(imgs: list, depths: list, k: int):
    idx = random.sample(range(len(imgs)), k)
    ds_imgs = [imgs[i] for i in idx]
    ds_depths = [depths[i] for i in idx]
    return ds_imgs, ds_depths


if __name__ == "__main__":
    main(os.path.join(os.getcwd(), sys.argv[1]))
