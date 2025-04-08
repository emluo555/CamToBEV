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

def init_model():
    parameters = {
        'inp_channels':3,
        'out_channels':3,
        'n_feat':80,
        'chan_factor':1.5,
        'n_RRG':4,
        'n_MRB':2,
        'height':3,
        'width':2,
        'bias':False,
        'scale':1,
        'task': 'lowlight_enhancement'
    }
    weights = os.path.join('MIRNet', 'pretrained_models', 'enhancement_lol.pth')
    load_arch = run_path(os.path.join('MIRNet','mirnet_v2_arch.py'))
    model = load_arch['MIRNet_v2'](**parameters)
    model.cuda()

    checkpoint = torch.load(weights)
    model.load_state_dict(checkpoint['params'])
    return model

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
    
    model = init_model()

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

            img = Image.open(imgname) 
            img_scaled=img
            #img_scaled = img.resize(size=final_dim, resample=Image.NEAREST)

            rgb_img =  img_scaled.convert("RGB")
            img_np = np.array(rgb_img)  # Convert to NumPy array
            mean_intensity = np.mean(img_np)

            # Skip processing if the image is not dark
            if mean_intensity >= 50:
                # print('light , ' , new_imgname)
                img_scaled.save(new_imgname)
            else: 
                print('dark , ' , new_imgname)
                restored_img = lowlight_enhancement(img_np, model)
                restored_img.save(new_imgname)
            
        sample_num += 1
    return

# NIGHT IMAGE STUFF 
def lowlight_enhancement(img_np, model):
    img_multiple_of = 4

    with torch.no_grad():
        input_ = torch.from_numpy(img_np).float().div(255.).permute(2, 0, 1).unsqueeze(0).cuda()

        # Pad the input if not a multiple of 4
        h, w = input_.shape[2], input_.shape[3]
        H, W = ((h + img_multiple_of) // img_multiple_of) * img_multiple_of, \
            ((w + img_multiple_of) // img_multiple_of) * img_multiple_of
        padh = H - h if h % img_multiple_of != 0 else 0
        padw = W - w if w % img_multiple_of != 0 else 0
        input_ = F.pad(input_, (0, padw, 0, padh), 'reflect')

        restored = model(input_)
        restored = torch.clamp(restored, 0, 1)

        # Unpad the output
        restored = restored[:, :, :h, :w]
        restored = restored.permute(0, 2, 3, 1).cpu().detach().numpy()
        restored = img_as_ubyte(restored[0])

        # Convert NumPy array back to PIL image
        restored_img = Image.fromarray(restored)
        return restored_img


if __name__ == '__main__':
    version = "trainval"  # specifies the split that is loaded - mini for now
    print("Version for conversion: '%s' " % version)
    dataroot = "./datasets/nuscenes-trainval/"  # path to NuScenes directory
    print("Data is taken from '%s'" % dataroot)
    target_dir = "./datasets/nuscenes-trainval/cleaned_images"   # custom data path
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
                            new_w=448, new_h=896)  # change desired image resolution
