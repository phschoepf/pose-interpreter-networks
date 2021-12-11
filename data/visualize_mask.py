from pycocotools.coco import COCO
from PIL import Image

def main(annfile):
    coco = COCO(annfile)
    anns = coco.loadAnns(coco.getAnnIds(coco.getImgIds()))
    for id, ann in enumerate(anns):
        mask = coco.annToMask(ann)
        im = Image.fromarray(mask, mode="L")
        im.save(f"{id}_mask.png")

if __name__ == "__main__":
    main("3DprintingDataset.json")