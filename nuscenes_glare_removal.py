"""
code for image precomputation -> scales the full res images down to the specified scaling factor
"""

import os

from nuscenes.nuscenes import NuScenes
from nuscenes.utils.splits import create_splits_scenes
from PIL import Image
from runpy import run_path
from skimage import img_as_ubyte
import torch
import torch.nn.functional as F
import numpy as np
import cv2

# glare removal
def patch_based_inpainting(image, mask, patch_size=5):
    # Convert the mask to grayscale
    mask_binary = mask

    # Find contours in the binary mask
    contours, _ = cv2.findContours(mask_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Iterate through each contour (assumes there is only one contour in this case)
    for contour in contours:
        # Create a mask for the current contour
        contour_mask = np.zeros_like(mask_binary)
        cv2.drawContours(contour_mask, [contour], 0, 255, thickness=cv2.FILLED)

        # Create an inpainting mask by dilating the contour mask
        inpaint_mask = cv2.dilate(contour_mask, np.ones((patch_size, patch_size), np.uint8))

        # Inpaint the image using the inpainting mask
        image = cv2.inpaint(image, inpaint_mask, inpaintRadius=patch_size, flags=cv2.INPAINT_TELEA)

    return image

def grab_convert_store_imgs(version, dataroot, is_train, target_dir, new_w, new_h):
    # load nuscenes
    nusc = NuScenes(version='v1.0-{}'.format(version), dataroot=dataroot, verbose=True)
    print("... data loaded! \n")

    # filter by scene split
    split = {
        'v1.0-trainval': {True: 'train', False: 'val'},
        'v1.0-mini': {True: 'mini_train', False: 'mini_val'},
    }[nusc.version][is_train]
    # get list of scene strings for specified split 
    scenes = create_splits_scenes()[split]

    # get indices for relevant samples -> based on chosen split
    samples = [samp for samp in nusc.sample]
    # remove samples that aren't in this split
    samples = [samp for samp in samples if nusc.get('scene', samp['scene_token'])['name'] in scenes]
    # sort by scene, timestamp (only to make chronological viz easier)
    samples.sort(key=lambda x: (x['scene_token'], x['timestamp']))

    cams = ['CAM_FRONT_LEFT', 'CAM_FRONT', 'CAM_FRONT_RIGHT', 'CAM_BACK_LEFT', 'CAM_BACK', 'CAM_BACK_RIGHT']
    # w = 1600
    # h = 900

    final_dim = (new_w, new_h)

    res_str = str(final_dim[0]) + "_" + str(final_dim[1])
    new_target_dir = os.path.join(target_dir, res_str)
    if not os.path.exists(new_target_dir):
        os.mkdir(new_target_dir)

    samples_dir = os.path.join(new_target_dir, "samples")
    if not os.path.exists(samples_dir):
        os.mkdir(samples_dir)
    
    sample_num = 0
    for sample in samples:
        print("Sample: %d" % sample_num)

        for cam in cams:
            samp = nusc.get('sample_data', sample['data'][cam])
            cam_name = cam
            cam_dir = os.path.join(samples_dir, cam_name)
            if not os.path.exists(cam_dir):
                os.mkdir(cam_dir)
            imgname = os.path.join(dataroot, samp['filename'])
            new_imgname = os.path.join(new_target_dir, samp['filename'])

            img = cv2.imread(imgname) 
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            mean_intensity = np.mean(gray)

            # Skip processing if the image is not dark
            if mean_intensity > 60:
                cv2.imwrite(new_imgname, img)
            else: 
                # Apply threshold on grayscale image to extract glare
                mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)[1]  

                restored_img = patch_based_inpainting(img, mask, patch_size = 2 )
                cv2.imwrite(new_imgname, restored_img)
            
        sample_num += 1
    return


if __name__ == '__main__':
    version = "trainval"  # specifies the split that is loaded - mini for now
    print("Version for conversion: '%s' " % version)
    dataroot = "./datasets/nuscenes-trainval/"  # path to NuScenes directory
    print("Data is taken from '%s'" % dataroot)
    target_dir = "./datasets/nuscenes-trainval/glare_220_5"   # custom data path
    if not os.path.exists(target_dir):
        os.mkdir(target_dir)
        print("Directory '%s' created" % target_dir)
    else:
        print("Directory '%s' already exists!" % target_dir)

    # get the image -> convert to the desired resolution -> store data at desired path
    grab_convert_store_imgs(version=version,
                            dataroot=dataroot,
                            is_train=False,  # True -> Trainset ; False -> Valset
                            target_dir=target_dir,
                            new_w=900, new_h=1600)  # keep res
