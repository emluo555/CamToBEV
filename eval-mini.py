import argparse
import os
import random
# os.environ['CUDA_VISIBLE_DEVICES'] = '0'
# print("FIXED CUDA DEVICE: " + os.environ['CUDA_VISIBLE_DEVICES'])
import time
import warnings

import numpy as np
import torch
import torch.nn.functional as F
import yaml
from fire import Fire
from shapely.errors import ShapelyDeprecationWarning
from tabulate import tabulate
from tensorboardX import SummaryWriter

import nuscenes_data
import saverloader
import utils.basic
import utils.geom
import utils.improc
import utils.misc
import utils.vox
from nets.segnet_simple_bev_with_map import SegnetWithMap
from nets.segnet_simple_lift_fuse_ablation_new_decoders import (
    SegnetSimpleLiftFuse,
)
from nets.segnet_transformer_lift_fuse_new_decoders import (
    SegnetTransformerLiftFuse,
)

# Suppress deprecation warnings from shapely regarding the nuscenes map api
warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning, module="nuscenes.map_expansion.map_api")

torch.multiprocessing.set_sharing_strategy('file_system')

random.seed(125)
np.random.seed(125)
torch.manual_seed(125)
torch.cuda.manual_seed_all(125)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

scene_centroid_x = 0.0
scene_centroid_y = 1.0
scene_centroid_z = 0.0

scene_centroid_py = np.array([scene_centroid_x,
                              scene_centroid_y,
                              scene_centroid_z]).reshape([1, 3])
scene_centroid = torch.from_numpy(scene_centroid_py).float()

XMIN, XMAX = -50, 50
ZMIN, ZMAX = -50, 50
YMIN, YMAX = -5, 5
bounds = (XMIN, XMAX, YMIN, YMAX, ZMIN, ZMAX)

Z, Y, X = 200, 8, 200

val_day_len = 4449
val_rain_len = 968
val_night_len = 602


def update_metrics(metric_prefix: str, condition_metrics_dict: dict,  metrics_model: dict) -> None:
    intersections_key = f'{metric_prefix}_intersections'
    unions_key = f'{metric_prefix}_unions'
    iou_key = f'{metric_prefix}_iou'
    condition_metrics_dict[intersections_key] += metrics_model[intersections_key]
    condition_metrics_dict[unions_key] += metrics_model[unions_key]
    condition_metrics_dict[iou_key] = 100 * condition_metrics_dict[intersections_key] / \
        (condition_metrics_dict[unions_key] + 1e-4)


def update_range_metrics(metric_prefix: str, range_metric_dict: dict, metrics_model: dict) -> None:
    for range_suffix in ['0_20', '20_35', '35_50']:
        update_metrics(f'{metric_prefix}_{range_suffix}', range_metric_dict, metrics_model)


def update_and_calculate_map_metrics(eval_status: str, metrics: dict, map_metrics: dict, iou_labels: list[str]) \
        -> tuple[dict, float]:
    for key in map_metrics.keys():
        if key == 'map_seg_thresholds':
            map_metrics[key] = metrics[key]
        else:
            map_metrics[key] += metrics[key]
    # map_ious = {f'{eval_status.lower()}_{label}': 100 * map_metrics['map_masks_intersections'][i] /
    #             map_metrics['map_masks_unions'][i] for i, label in enumerate(iou_labels)}
    map_ious = {f'{label}': 100 * map_metrics['map_masks_intersections'][i] /
                map_metrics['map_masks_unions'][i] for i, label in enumerate(iou_labels)}
    mean_map_iou = 100 * (map_metrics['map_masks_intersections'] / map_metrics['map_masks_unions'])
    mean_map_iou = mean_map_iou.sum() / torch.count_nonzero(mean_map_iou)
    return map_ious, mean_map_iou


def calculate_best_map_ious_and_thresholds(intersections: torch.Tensor, unions: torch.Tensor, thresholds: torch.Tensor):
    multi_map_ious = intersections / unions
    best_map_ious, best_threshold_index = torch.max(multi_map_ious, dim=1)
    best_thresholds = thresholds[best_threshold_index]
    best_map_mean_iou = best_map_ious.sum(dim=0) / torch.count_nonzero(best_map_ious, dim=0)
    return best_map_ious, best_thresholds, best_map_mean_iou


def format_value(value):
    if isinstance(value, torch.Tensor):
        return f"{value.item():.3f}"
    return f"{float(value):.3f}"


def display_final_results(train_task, dset, obj_metrics, day_metrics, rain_metrics, night_metrics,
                          map_metrics, day_map_metrics, rain_map_metrics, night_map_metrics,
                          mean_map_iou, map_ious, day_mean_map_iou, day_map_ious,
                          rain_mean_map_iou, rain_map_ious, night_mean_map_iou, night_map_ious, do_drn_val_split):
    print("day stuff ", day_metrics, day_map_metrics, day_mean_map_iou, day_map_ious)
    print("rain stuff? ", rain_metrics, rain_map_metrics,rain_mean_map_iou,rain_map_ious)
    print("night stuff? ", night_metrics, night_map_metrics,night_mean_map_iou,night_map_ious)
    print("do_drn_val_split ", do_drn_val_split)

    print("##################   FINAL RESULTS   ###################")
    print("##################   OBJ IOUs  ###################")
    if train_task == 'both' or train_task == 'object':
        obj_data = [
            ["ALL", format_value(obj_metrics['obj_iou']), format_value(obj_metrics['obj_0_20_iou']),
             format_value(obj_metrics['obj_20_35_iou']), format_value(obj_metrics['obj_35_50_iou'])],

            ["DAY", format_value(day_metrics['obj_iou']), format_value(day_metrics['obj_0_20_iou']),
             format_value(day_metrics['obj_20_35_iou']),
             format_value(day_metrics['obj_35_50_iou'])] if do_drn_val_split else ["DAY", "-", "-", "-", "-"],
             # no rain
             ["NIGHT", format_value(night_metrics['obj_iou']), format_value(night_metrics['obj_0_20_iou']),
             format_value(night_metrics['obj_20_35_iou']),
             format_value(night_metrics['obj_35_50_iou'])] if do_drn_val_split else ["NIGHT", "-", "-", "-", "-"]

        ]

        headers = ["", "mean obj_IoU", "0-20m obj_IoU", "20-35m obj_IoU", "35-50m obj_IoU"]
        print(tabulate(obj_data, headers=headers, tablefmt="pretty"))
        print('##############################################################')

    if train_task == 'both' or train_task == 'map':
        print("##################   MAP IOUs (UNIFORM THRESHOLD = 40%) ###################")
        map_data = [
            ["ALL", format_value(mean_map_iou), format_value(map_ious['drivable_iou'].item()),
             format_value(map_ious['carpark_iou'].item()), format_value(map_ious['ped_cross_iou'].item()),
             format_value(map_ious['walkway_iou'].item()), format_value(map_ious['stop_line_iou'].item()),
             format_value(map_ious['road_divider_iou'].item()), format_value(map_ious['lane_divider_iou'].item())],

            ["DAY", format_value(day_mean_map_iou), format_value(day_map_ious['drivable_iou'].item()),
             format_value(day_map_ious['carpark_iou'].item()), format_value(day_map_ious['ped_cross_iou'].item()),
             format_value(day_map_ious['walkway_iou'].item()), format_value(day_map_ious['stop_line_iou'].item()),
             format_value(day_map_ious['road_divider_iou'].item()),
             format_value(day_map_ious['lane_divider_iou'].item())] if do_drn_val_split
            else ["DAY", "-", "-", "-", "-", "-", "-", "-", "-"],

            # ["RAIN", format_value(rain_mean_map_iou), format_value(rain_map_ious['drivable_iou'].item()),
            #  format_value(rain_map_ious['carpark_iou'].item()), format_value(rain_map_ious['ped_cross_iou'].item()),
            #  format_value(rain_map_ious['walkway_iou'].item()), format_value(rain_map_ious['stop_line_iou'].item()),
            #  format_value(rain_map_ious['road_divider_iou'].item()),
            #  format_value(rain_map_ious['lane_divider_iou'].item())] if do_drn_val_split
            # else ["RAIN", "-", "-", "-", "-", "-", "-", "-", "-"],

            ["NIGHT", format_value(night_mean_map_iou), format_value(night_map_ious['drivable_iou'].item()),
             format_value(night_map_ious['carpark_iou'].item()), format_value(night_map_ious['ped_cross_iou'].item()),
             format_value(night_map_ious['walkway_iou'].item()), format_value(night_map_ious['stop_line_iou'].item()),
             format_value(night_map_ious['road_divider_iou'].item()),
             format_value(night_map_ious['lane_divider_iou'].item())] if do_drn_val_split
            else ["NIGHT", "-", "-", "-", "-", "-", "-", "-", "-"]
        ]

        headers = ["", "mean map_IoU", "drivable_IoU", "carpark_IoU", "ped_cross_IoU", "walkway_IoU", "stop_line_IoU",
                   "road_divider_IoU", "lane_divider_IoU"]
        print(tabulate(map_data, headers=headers, tablefmt="pretty"))

        print("##################   BEST MAP IOUs (CLASS-SPECIFIC THRESHOLD)  ###################")
        best_map_ious, best_thresholds, best_map_mean_iou = calculate_best_map_ious_and_thresholds(
            intersections=map_metrics['map_masks_multi_ious_intersections'],
            unions=map_metrics['map_masks_multi_ious_unions'],
            thresholds=map_metrics['map_seg_thresholds'])

        day_best_map_ious, day_best_thresholds, day_best_map_mean_iou = calculate_best_map_ious_and_thresholds(
            intersections=day_map_metrics['map_masks_multi_ious_intersections'],
            unions=day_map_metrics['map_masks_multi_ious_unions'],
            thresholds=day_map_metrics['map_seg_thresholds'])

        # rain_best_map_ious, rain_best_thresholds, rain_best_map_mean_iou = calculate_best_map_ious_and_thresholds(
        #     intersections=rain_map_metrics['map_masks_multi_ious_intersections'],
        #     unions=rain_map_metrics['map_masks_multi_ious_unions'],
        #     thresholds=rain_map_metrics['map_seg_thresholds'])

        night_best_map_ious, night_best_thresholds, night_best_map_mean_iou = calculate_best_map_ious_and_thresholds(
            intersections=night_map_metrics['map_masks_multi_ious_intersections'],
            unions=night_map_metrics['map_masks_multi_ious_unions'],
            thresholds=night_map_metrics['map_seg_thresholds'])

        best_data = [
            ["ALL", format_value(best_map_mean_iou*100), *[f"{x * 100:.3f}" for x in best_map_ious]],
            ["DAY", format_value(day_best_map_mean_iou*100), *[f"{x * 100:.3f}" for x in day_best_map_ious]]
            if do_drn_val_split else ["DAY", "-", "-", "-", "-", "-", "-", "-"],
            # ["RAIN", format_value(rain_best_map_mean_iou*100), *[f"{x * 100:.3f}" for x in rain_best_map_ious]]
            # if do_drn_val_split else ["RAIN", "-", "-", "-", "-", "-", "-", "-"],
            ["NIGHT", format_value(night_best_map_mean_iou*100), *[f"{x * 100:.3f}" for x in night_best_map_ious]]
            if do_drn_val_split else ["NIGHT", "-", "-", "-", "-", "-", "-", "-"]
        ]
        # [f"{x * 100:.3f}" for x in best_map_ious]  (torch.round(best_map_ious*100000)/1000)
        headers = ["", "best map_IoU", "drivable_IoU", "carpark_IoU", "ped_cross_IoU", "walkway_IoU", "stop_line_IoU",
                   "road_divider_IoU", "lane_divider_IoU"]

        print(tabulate(best_data, headers=headers, tablefmt="pretty"))

        print("##################   BEST CLASS-SPECIFIC THRESHOLD ###################")
        thresholds_data = [
            ["ALL", *(torch.round(best_thresholds*100))],
            ["DAY", *(torch.round(day_best_thresholds*100))] if do_drn_val_split
            else ["DAY", "-", "-", "-", "-", "-", "-", "-"],
            # ["RAIN", *(torch.round(rain_best_thresholds*100))] if do_drn_val_split
            # else ["RAIN", "-", "-", "-", "-", "-", "-", "-"],
            ["NIGHT", *(torch.round(night_best_thresholds*100))] if do_drn_val_split
            else ["NIGHT", "-", "-", "-", "-", "-", "-", "-"]
        ]

        headers = ["", "drivable_th", "carpark_th", "ped_cross_th", "walkway_th", "stop_line_th", "road_divider_th",
                   "lane_divider_th"]

        print(tabulate(thresholds_data, headers=headers, tablefmt="pretty"))


def requires_grad(parameters: iter, flag: bool = True) -> None:
    """
        Sets the `requires_grad` attribute of the given parameters.
        Args:
            parameters (iterable): An iterable of parameter tensors whose `requires_grad` attribute will be set.
            flag (bool, optional): If True, sets `requires_grad` to True. If False, sets it to False.
                Default is True.

        Returns:
            None
        """
    for p in parameters:
        p.requires_grad = flag


class SimpleLoss(torch.nn.Module):
    """
    SimpleLoss module that computes the binary cross-entropy loss.

    Args:
        pos_weight (float): Positive class weight for the binary cross-entropy loss.

    Methods:
        forward(ypred: torch.Tensor, ytgt: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
            Forward pass that computes the binary cross-entropy loss.
    """
    def __init__(self, pos_weight: float):
        """Initializes the SimpleLoss module with the specified positive class weight."""
        super(SimpleLoss, self).__init__()
        self.loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.Tensor([pos_weight]), reduction='none')

    def forward(self, ypred: torch.Tensor, ytgt: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
        """
        Forward pass that computes the binary cross-entropy loss.

        Args:
            ypred (torch.Tensor): Predicted logits.
            ytgt (torch.Tensor): Target tensor.
            valid (torch.Tensor): Mask indicating valid elements.

        Returns:
            torch.Tensor: The computed loss.
        """
        loss = self.loss_fn(ypred, ytgt)
        loss = utils.basic.reduce_masked_mean(loss, valid)
        return loss


class SigmoidFocalLoss(torch.nn.Module):
    """
        Computes the sigmoid of the model output to get values between 0 and 1, then applies the Focal Loss.
    """
    def __init__(self, alpha: float = -1.0, gamma: int = 2, reduction: str = "mean"):
        """
        Args:
            alpha (float, optional): Balances the importance of positive/negative examples. Default is -1.0.
            gamma (int, optional): If >= 0, reduces the loss contribution from easy examples
            and extends the range in which an example receives low loss. Default is 2.
            reduction (str, optional): Specifies the reduction to apply to the output. Options are 'mean', 'sum',
            and 'sum_of_class_means'. Default is 'mean'.
        """
        super(SigmoidFocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.reduction = reduction

    def forward(self, map_seg_e: torch.Tensor, map_seg_gt: torch.Tensor):
        """
        Forward pass that computes the sigmoid focal loss.

        Args:
            map_seg_e (torch.Tensor): Predicted logits.
            map_seg_gt (torch.Tensor): Target tensor.

        Returns:
                torch.Tensor: The computed loss.
        """
        # get predictions between 0 and 1
        p = torch.sigmoid(map_seg_e)
        # BCE with logits
        ce_loss = F.binary_cross_entropy_with_logits(input=map_seg_e, target=map_seg_gt, reduction="none")
        p_t = p * map_seg_gt + (1 - p) * (1 - map_seg_gt)
        f_loss = ce_loss * ((1 - p_t) ** self.gamma)

        if self.alpha >= 0:
            alpha_t = self.alpha * map_seg_gt + (1 - self.alpha) * (1 - map_seg_gt)
            f_loss = alpha_t * f_loss
        else:
            f_loss = f_loss

        if self.reduction == "mean":  # get mean over all classes
            f_loss = f_loss.mean()
        elif self.reduction == "sum":
            f_loss = f_loss.sum()
        elif self.reduction == "sum_of_class_means":
            '''
            f_loss = f_loss.mean(dim=[2,3])  # mean over bev map space
            f_loss = f_loss.mean(dim=0)  # mean over batch dim -> results in sum over class errors
            f_loss = f_loss.sum()
            '''
            # mean over B and bev grid -> then sum avg class error
            f_loss = f_loss.mean(dim=[0, 2, 3]).sum()
        return f_loss


def run_model(model, loss_fn, map_seg_loss_fn, d, device='cuda:0', sw=None, use_radar_encoder=None,
              radar_encoder_type=None, train_task='both', use_shallow_metadata=True,
              use_obj_layer_only_on_map=True):
    metrics = {}
    total_loss = torch.tensor(0.0, requires_grad=False).to(device)

    voxel_input_feature_buffer = None
    voxel_coordinate_buffer = None
    number_of_occupied_voxels = None
    in_occ_mem0 = None

    if radar_encoder_type == "voxel_net":
        # voxelnet
        imgs, rots, trans, intrins, seg_bev_g, \
            valid_bev_g, radar_data, bev_map_mask_g, bev_map_g, egocar_bev, \
            voxel_input_feature_buffer, voxel_coordinate_buffer, number_of_occupied_voxels = d

        # VoxelNet preprocessing
        voxel_input_feature_buffer = voxel_input_feature_buffer[:, 0]
        voxel_coordinate_buffer = voxel_coordinate_buffer[:, 0]
        number_of_occupied_voxels = number_of_occupied_voxels[:, 0]
        voxel_input_feature_buffer = voxel_input_feature_buffer.to(device)
        voxel_coordinate_buffer = voxel_coordinate_buffer.to(device)
        number_of_occupied_voxels = number_of_occupied_voxels.to(device)
    else:
        imgs, rots, trans, intrins, seg_bev_g, \
            valid_bev_g, radar_data, bev_map_mask_g, bev_map_g, egocar_bev = d

    B0, T, S, C, H, W = imgs.shape
    assert (T == 1)

    # eliminate the time dimension
    imgs = imgs[:, 0]
    rots = rots[:, 0]
    trans = trans[:, 0]
    intrins = intrins[:, 0]
    seg_bev_g = seg_bev_g[:, 0]
    valid_bev_g = valid_bev_g[:, 0]
    radar_data = radar_data[:, 0]
    # added bev_map_gt
    bev_map_mask_g = bev_map_mask_g[:, 0]
    if use_obj_layer_only_on_map:
        bev_map_mask_g = bev_map_mask_g[:, :-1]  # remove attached object class
    bev_map_g = bev_map_g[:, 0]
    # added egocar in bev plane
    egocar_bev = egocar_bev[:, 0]

    rgb_camXs = imgs.float().to(device)
    rgb_camXs = rgb_camXs - 0.5  # go to -0.5, 0.5

    seg_bev_g = seg_bev_g.to(device)
    obj_seg_bev_e = torch.zeros_like(seg_bev_g)
    valid_bev_g = valid_bev_g.to(device)

    # added bev_map_gt
    bev_map_mask_g = bev_map_mask_g.to(device)
    bev_map_mask_e = torch.zeros_like(bev_map_mask_g)
    bev_map_g = bev_map_g.to(device)
    bev_map_e = torch.zeros_like(bev_map_g)
    # added egocar in bev plane
    egocar_bev = egocar_bev.to(device)

    # create ego car color plane
    ego_plane = torch.zeros_like(bev_map_g).to(device)
    ego_plane[:, [0, 2]] = 0.0
    ego_plane[:, 1] = 1.0
    # combine ego car and map
    ego_car_on_map_g = bev_map_g * (1 - egocar_bev) + ego_plane * egocar_bev

    # create other cars plane
    other_cars_plane = torch.zeros_like(bev_map_g).to(device)
    other_cars_plane[:, [0, 1]] = 0.0
    other_cars_plane[:, 2] = 1.0
    # combine ego car other cars and map
    ego_other_cars_on_map_g = ego_car_on_map_g * (1 - seg_bev_g) + other_cars_plane * seg_bev_g

    rad_data = radar_data.to(device).permute(0, 2, 1)  # B, R, 19
    xyz_rad = rad_data[:, :, :3]
    meta_rad = rad_data[:, :, 3:]
    shallow_meta_rad = rad_data[:, :, 5:8]

    B, S, C, H, W = rgb_camXs.shape

    def __p(x):
        # Wrapper function: e.g. unites B,S dim to B*S
        return utils.basic.pack_seqdim(x, B)

    def __u(x):
        # Wrapper function: e.g. splits B*S dim into B,S
        return utils.basic.unpack_seqdim(x, B)

    intrins_ = __p(intrins)
    pix_T_cams_ = utils.geom.merge_intrinsics(*utils.geom.split_intrinsics(intrins_)).to(device)
    pix_T_cams = __u(pix_T_cams_)

    velo_T_cams = utils.geom.merge_rtlist(rots, trans).to(device)
    cams_T_velo = __u(utils.geom.safe_inverse(__p(velo_T_cams)))

    cam0_T_camXs = utils.geom.get_camM_T_camXs(velo_T_cams, ind=0)
    rad_xyz_cam0 = utils.geom.apply_4x4(cams_T_velo[:, 0], xyz_rad)

    vox_util = utils.vox.Vox_util(
        Z, Y, X,
        scene_centroid=scene_centroid.to(device),
        bounds=bounds,
        assert_cube=False)

    if not model.module.use_radar:
        in_occ_mem0 = None
    elif model.module.use_radar and (model.module.use_metaradar or use_shallow_metadata):
        if use_radar_encoder and radar_encoder_type == 'voxel_net':
            voxelnet_feats_mem0 = voxel_input_feature_buffer, voxel_coordinate_buffer, number_of_occupied_voxels
            in_occ_mem0 = voxelnet_feats_mem0
        elif use_shallow_metadata:
            shallow_metarad_occ_mem0 = vox_util.voxelize_xyz_and_feats(rad_xyz_cam0, shallow_meta_rad, Z, Y, X,
                                                                       assert_cube=False)
            in_occ_mem0 = shallow_metarad_occ_mem0
        else:  # use_metaradar
            metarad_occ_mem0 = vox_util.voxelize_xyz_and_feats(rad_xyz_cam0, meta_rad, Z, Y, X, assert_cube=False)
            in_occ_mem0 = metarad_occ_mem0
    elif model.module.use_radar:
        rad_occ_mem0 = vox_util.voxelize_xyz(rad_xyz_cam0, Z, Y, X, assert_cube=False)
        in_occ_mem0 = rad_occ_mem0
    elif model.module.use_metaradar or use_shallow_metadata:
        assert False  # cannot use_metaradar without use_radar

    start_inference_t = time.time()  # optional: pure inference timing
    seg_e = model(
        rgb_camXs=rgb_camXs,
        pix_T_cams=pix_T_cams,
        cam0_T_camXs=cam0_T_camXs,
        vox_util=vox_util,
        rad_occ_mem0=in_occ_mem0)
    inference_t = time.time() - start_inference_t  # optional: pure inference timing
    # print("Inference time: ", inference_t)  # optional: pure inference timing

    # get bev map from masks
    if train_task == 'both' or train_task == 'map':

        if train_task == 'both':
            bev_map_mask_e = seg_e[:, :-1]
            obj_seg_bev_e = seg_e[:, -1].unsqueeze(dim=1)
            obj_seg_bev = torch.sigmoid(obj_seg_bev_e)

            bev_map_only_mask_g = bev_map_mask_g
        else:
            bev_map_mask_e = seg_e
            obj_seg_bev = seg_bev_g  # add gt vehicles on map (optional)
            bev_map_only_mask_g = bev_map_mask_g

        map_seg_threshold = 0.4
        bev_map_e = nuscenes_data.get_rgba_map_from_mask2_on_batch(
            torch.sigmoid(bev_map_mask_e).detach().cpu().numpy(),
            threshold=map_seg_threshold, a=0.4).to(device)

        # combine ego car and bev_map_e
        ego_car_on_map_e = bev_map_e * (1 - egocar_bev) + ego_plane * egocar_bev  # check dims

        # create other cars estimate plane
        other_cars_plane_e = torch.zeros_like(bev_map_e).to(device)
        other_cars_plane_e[:, [0, 1]] = 0.0
        other_cars_plane_e[:, 2] = 1.0

        # combine ego car other cars and map  # not used here  -->  checkout vis_eval_nuscenes for combined results
        # ego_other_cars_on_map_e = ego_car_on_map_e * (1 - obj_seg_bev) + other_cars_plane_e * obj_seg_bev

        # loss calculation
        map_seg_fc_loss = map_seg_loss_fn(bev_map_mask_e, bev_map_only_mask_g)
        #   map
        fc_map_factor = 1 / torch.exp(model.module.fc_map_weight)
        map_seg_fc_loss = 20.0 * map_seg_fc_loss * fc_map_factor  # 20.0
        # add to total loss
        total_loss += map_seg_fc_loss

        # MAP IoU calculation

        # ious for map segmentation:
        tp = ((torch.sigmoid(bev_map_mask_e) >= map_seg_threshold).bool() & bev_map_mask_g.bool()).sum(dim=[2, 3])
        fp = ((torch.sigmoid(bev_map_mask_e) >= map_seg_threshold).bool() & ~bev_map_mask_g.bool()).sum(dim=[2, 3])
        fn = (~(torch.sigmoid(bev_map_mask_e) >= map_seg_threshold).bool() & bev_map_mask_g.bool()).sum(dim=[2, 3])

        map_intersections_per_class = tp.sum(dim=0)  # sum over batch --> 7 intersection values
        map_unions_per_class = (
                tp.sum(dim=0) + fp.sum(dim=0) + fn.sum(dim=0) + 1e-4)  # sum over batch --> 7 union values

        # ################# MULTI-IOU CALCULATION #####################

        # ######
        map_seg_thresholds = torch.Tensor([0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]).to(device)
        sig_map_bev_e = torch.sigmoid(bev_map_mask_e)[:, :, :, :, None] >= map_seg_thresholds
        bev_map_mask_g = bev_map_only_mask_g[:, :, :, :, None]

        tps = (sig_map_bev_e.bool() & bev_map_mask_g.bool()).sum(dim=[2, 3])  # (B,7,12)
        fps = (sig_map_bev_e.bool() & ~bev_map_mask_g.bool()).sum(dim=[2, 3])
        fns = (~sig_map_bev_e.bool() & bev_map_mask_g.bool()).sum(dim=[2, 3])

        # best i's and u's
        map_masks_multi_ious_intersections = tps.sum(0)
        map_masks_multi_ious_unions = (tps.sum(0) + fps.sum(0) + fns.sum(0) + 1e-4)

        # metrics
        metrics['focal_loss_map'] = map_seg_fc_loss  # .item()
        metrics['fc_map_weight'] = model.module.fc_map_weight.item()
        # single threshold IoUs (t=0.4)
        metrics['map_masks_intersections'] = map_intersections_per_class
        metrics['map_masks_unions'] = map_unions_per_class
        # multi threshold IoUs
        metrics['map_masks_multi_ious_intersections'] = map_masks_multi_ious_intersections
        metrics['map_masks_multi_ious_unions'] = map_masks_multi_ious_unions
        metrics['map_seg_thresholds'] = map_seg_thresholds

    # object seg task
    if train_task == 'both' or train_task == 'object':
        if train_task == 'both':
            obj_seg_bev_e = seg_e[:, -1].unsqueeze(dim=1)
        else:  # 'object'
            obj_seg_bev_e = seg_e
            obj_seg_bev_e_sigmoid = torch.sigmoid(obj_seg_bev_e)
            ego_other_cars_on_map_e = ego_car_on_map_g * (1 - obj_seg_bev_e_sigmoid) + \
                other_cars_plane * obj_seg_bev_e_sigmoid
        # clc loss
        ce_loss = loss_fn(obj_seg_bev_e, seg_bev_g, valid_bev_g)
        # obj
        ce_factor = 1 / torch.exp(model.module.ce_weight)
        ce_loss = 10.0 * ce_loss * ce_factor  # 10.0
        total_loss += ce_loss

        # object IoUs
        obj_seg_bev_e_round = torch.sigmoid(obj_seg_bev_e).round()  # --> thresh = 0.5
        # overall intersection and unions
        obj_intersection = (obj_seg_bev_e_round * seg_bev_g * valid_bev_g).sum(dim=[1, 2, 3])
        obj_union = ((obj_seg_bev_e_round + seg_bev_g) * valid_bev_g).clamp(0, 1).sum(dim=[1, 2, 3])
        obj_intersections = obj_intersection.sum()
        obj_unions = obj_union.sum()

        # distance based IoU calc
        # 0 - 20 m
        bev_0_20_mask = torch.zeros_like(obj_seg_bev_e_round)  # init with zeros
        _, _, mask_h, mask_w = bev_0_20_mask.shape
        start_20 = (mask_h // 2) - 40
        end_20 = (mask_h // 2) + 40
        bev_0_20_mask[:, :, start_20:end_20, start_20:end_20] = 1.0
        # bev_0_20_mask_np = bev_0_20_mask.detach().cpu().numpy()  # debug only -> better visualization of the masks

        obj_0_20_intersection = (obj_seg_bev_e_round * seg_bev_g * valid_bev_g * bev_0_20_mask).sum(dim=[1, 2, 3])
        obj_0_20_union = ((obj_seg_bev_e_round + seg_bev_g) * valid_bev_g * bev_0_20_mask).clamp(0, 1).sum(
            dim=[1, 2, 3])
        obj_0_20_intersections = obj_0_20_intersection.sum()
        obj_0_20_unions = obj_0_20_union.sum()

        # 20 - 35 m
        bev_20_35_mask = torch.zeros_like(obj_seg_bev_e_round)  # init with zeros
        start_0_35 = (mask_h // 2) - 70
        end_0_35 = (mask_h // 2) + 70
        bev_20_35_mask[:, :, start_0_35:end_0_35, start_0_35:end_0_35] = 1.0
        # set the inner (0-20) mask to zero
        bev_20_35_mask[:, :, start_20:end_20, start_20:end_20] = 0.0

        obj_20_35_intersection = (obj_seg_bev_e_round * seg_bev_g * valid_bev_g * bev_20_35_mask).sum(dim=[1, 2, 3])
        obj_20_35_union = ((obj_seg_bev_e_round + seg_bev_g) * valid_bev_g * bev_20_35_mask).clamp(0, 1).sum(
            dim=[1, 2, 3])
        obj_20_35_intersections = obj_20_35_intersection.sum()
        obj_20_35_unions = obj_20_35_union.sum()

        # 35 - 50 m
        bev_35_50_mask = torch.ones_like(obj_seg_bev_e_round)  # init with ones
        # set the inner (0-35) mask to zero
        bev_35_50_mask[:, :, start_0_35:end_0_35, start_0_35:end_0_35] = 0.0

        obj_35_50_intersection = (obj_seg_bev_e_round * seg_bev_g * valid_bev_g * bev_35_50_mask).sum(dim=[1, 2, 3])
        obj_35_50_union = ((obj_seg_bev_e_round + seg_bev_g) * valid_bev_g * bev_35_50_mask).clamp(0, 1).sum(
            dim=[1, 2, 3])
        obj_35_50_intersections = obj_35_50_intersection.sum()
        obj_35_50_unions = obj_35_50_union.sum()

        metrics['ce_loss'] = ce_loss
        metrics['ce_weight'] = model.module.ce_weight.item()
        metrics['obj_intersections'] = obj_intersections
        metrics['obj_unions'] = obj_unions

        # 0 - 20 m
        metrics['obj_0_20_intersections'] = obj_0_20_intersections
        metrics['obj_0_20_unions'] = obj_0_20_unions
        # 20 - 35 m
        metrics['obj_20_35_intersections'] = obj_20_35_intersections
        metrics['obj_20_35_unions'] = obj_20_35_unions
        # 35 - 50 m
        metrics['obj_35_50_intersections'] = obj_35_50_intersections
        metrics['obj_35_50_unions'] = obj_35_50_unions

    return total_loss, metrics, inference_t


def main(
        exp_name='eval',
        # val
        log_freq=100,
        shuffle=False,
        dset='mini',  # we will just use val -- start with mini??
        batch_size=8,
        nworkers=12,
        # data/log/load directories
        data_dir='./datasets/nuscenes/',
        custom_dataroot='./datasets/nuscenes/scaled_images',
        log_dir='logs_eval_nuscenes_bevcar',
        init_dir='checkpoints/bev_car',
        ignore_load=None,
        # data
        final_dim=[448, 896],  # to match //8, //14, //16 and //32 in Vit
        ncams=6,
        nsweeps=5,
        # model
        encoder_type='dino_v2',
        radar_encoder_type='voxel_net',
        use_rpn_radar=False,
        train_task='both',
        use_radar=False,
        use_radar_encoder=False,
        use_radar_filters=False,
        use_metaradar=False,
        use_shallow_metadata=False,
        use_pre_scaled_imgs=True,
        use_obj_layer_only_on_map=False,
        init_query_with_image_feats=False,
        do_rgbcompress=True,
        use_multi_scale_img_feats=False,
        num_layers=6,
        # cuda
        device_ids=[0],
        freeze_dino=True,
        do_feat_enc_dec=True,
        combine_feat_init_w_learned_q=False,
        load_step=None,
        model_type='transformer',
        use_radar_occupancy_map=False,  # occupancy_radar_rpn
        do_drn_val_split=True,  # True
        learnable_fuse_query=True,
):
    assert (model_type in ['transformer', 'simple_lift_fuse', 'SimpleBEV_map'])
    B = batch_size
    assert (B % len(device_ids) == 0)  # batch size must be divisible by number of gpus

    device = 'cuda:%d' % device_ids[0]
    print(device)

    model_name = str(load_step) + '_' + exp_name
    print('model_name', model_name)

    # set up logging
    writer_ev = SummaryWriter(os.path.join(log_dir, model_name + '/ev'), max_queue=10, flush_secs=60)

    print('resolution:', final_dim)

    data_aug_conf = {
        'final_dim': final_dim,
        'cams': ['CAM_FRONT_LEFT', 'CAM_FRONT', 'CAM_FRONT_RIGHT',
                 'CAM_BACK_LEFT', 'CAM_BACK', 'CAM_BACK_RIGHT'],
        'ncams': ncams,
    }
    _, val_dataloader = nuscenes_data.compile_data(
        dset,
        data_dir,
        data_aug_conf=data_aug_conf,
        centroid=scene_centroid_py,
        bounds=bounds,
        res_3d=(Z, Y, X),
        bsz=B,
        nworkers=1,
        nworkers_val=nworkers,
        shuffle=shuffle,
        use_radar_filters=use_radar_filters,
        seqlen=1,
        nsweeps=nsweeps,
        do_shuffle_cams=False,
        get_tids=True,
        radar_encoder_type=radar_encoder_type,
        use_shallow_metadata=use_shallow_metadata,
        use_pre_scaled_imgs=use_pre_scaled_imgs,
        custom_dataroot=custom_dataroot,
        use_obj_layer_only_on_map=use_obj_layer_only_on_map,
        use_radar_occupancy_map=use_radar_occupancy_map,
        do_drn_val_split=do_drn_val_split,
        get_val_day=False,  # set 'True' for debug only
        get_val_rain=False,  # set 'True' for debug only
        get_val_night=False  # set 'True' for debug only
    )
    val_iterloader = iter(val_dataloader)

    vox_util = utils.vox.Vox_util(
        Z, Y, X,
        scene_centroid=scene_centroid.to(device),
        bounds=bounds,
        assert_cube=False)

    max_iters = len(val_dataloader)  # determine iters by length of dataset

    # set up model & seg loss
    seg_loss_fn = SimpleLoss(2.13).to(device)
    map_seg_loss_fn = SigmoidFocalLoss(alpha=0.25, gamma=3, reduction="sum_of_class_means").to(
        device)

    # Transformer based lifting and fusion
    if model_type == 'transformer':
        model = SegnetTransformerLiftFuse(Z_cam=200, Y_cam=8, X_cam=200, Z_rad=Z, Y_rad=Y, X_rad=X, vox_util=None,
                                          use_radar=use_radar, use_metaradar=use_metaradar,
                                          use_shallow_metadata=use_shallow_metadata,
                                          use_radar_encoder=use_radar_encoder,
                                          do_rgbcompress=do_rgbcompress, encoder_type=encoder_type,
                                          radar_encoder_type=radar_encoder_type, rand_flip=False, train_task=train_task,
                                          init_query_with_image_feats=init_query_with_image_feats,
                                          use_obj_layer_only_on_map=use_obj_layer_only_on_map, do_feat_enc_dec=True,
                                          use_multi_scale_img_feats=use_multi_scale_img_feats, num_layers=num_layers,
                                          combine_feat_init_w_learned_q=combine_feat_init_w_learned_q,
                                          use_rpn_radar=use_rpn_radar, use_radar_occupancy_map=use_radar_occupancy_map,
                                          freeze_dino=freeze_dino, learnable_fuse_query=learnable_fuse_query)

    elif model_type == 'simple_lift_fuse':
        # our net with replaced lifting and fusion from SimpleBEV
        model = SegnetSimpleLiftFuse(Z_cam=200, Y_cam=8, X_cam=200, Z_rad=Z, Y_rad=Y, X_rad=X, vox_util=None,
                                     use_radar=use_radar, use_metaradar=use_metaradar,
                                     use_shallow_metadata=use_shallow_metadata, use_radar_encoder=use_radar_encoder,
                                     do_rgbcompress=do_rgbcompress, encoder_type=encoder_type,
                                     radar_encoder_type=radar_encoder_type, rand_flip=False, train_task=train_task,
                                     use_obj_layer_only_on_map=use_obj_layer_only_on_map,
                                     do_feat_enc_dec=do_feat_enc_dec,
                                     use_multi_scale_img_feats=use_multi_scale_img_feats, num_layers=num_layers,
                                     latent_dim=128, use_rpn_radar=use_rpn_radar,
                                     use_radar_occupancy_map=use_radar_occupancy_map,
                                     freeze_dino=freeze_dino)

    else:  # model_type == 'SimpleBEV_map'
        model = SegnetWithMap(Z, Y, X, vox_util=vox_util, use_radar=use_radar,
                              use_metaradar=use_metaradar, use_shallow_metadata=use_shallow_metadata,
                              do_rgbcompress=do_rgbcompress, encoder_type=encoder_type, rand_flip=False,
                              train_task=train_task, freeze_dino=freeze_dino)

    model = model.to(device)
    model = torch.nn.DataParallel(model, device_ids=device_ids)
    parameters = list(model.parameters())

    # Counting trainable parameters
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f'Trainable parameters: {trainable_params}')
    # Counting non-trainable parameters
    non_trainable_params = sum(p.numel() for p in model.parameters() if not p.requires_grad)
    print(f'Non-trainable parameters: {non_trainable_params}')
    # Overall parameters
    total_params = trainable_params + non_trainable_params
    print('Total parameters (trainable + fixed)', total_params)

    # load checkpoint
    _ = saverloader.load(init_dir, model.module, ignore_load=ignore_load, is_DP=True, step=load_step)
    global_step = 0
    requires_grad(parameters, False)
    model.eval()

    # logging pools. pool size should be larger than max_iters
    n_pool = 10000
    loss_pool_ev = utils.misc.SimplePool(n_pool, version='np')
    time_pool_ev = utils.misc.SimplePool(n_pool, version='np')
    assert (n_pool > max_iters)

    eval_status = 'unsorted'

    # Initialize metric dictionaries
    # object dicts
    obj_metrics = {
        'obj_intersections': 0, 'obj_unions': 0, 'obj_0_20_intersections': 0, 'obj_0_20_unions': 0,
        'obj_20_35_intersections': 0, 'obj_20_35_unions': 0, 'obj_35_50_intersections': 0, 'obj_35_50_unions': 0
    }
    day_metrics = obj_metrics.copy()
    rain_metrics = obj_metrics.copy()
    night_metrics = obj_metrics.copy()

    # map dicts
    iou_labels = ['drivable_iou', 'carpark_iou', 'ped_cross_iou', 'walkway_iou', 'stop_line_iou',
                  'road_divider_iou', 'lane_divider_iou']
    map_metrics = {
        'map_masks_intersections': torch.zeros(7, device=device),
        'map_masks_unions': torch.zeros(7, device=device),
        'map_masks_multi_ious_intersections': torch.zeros((7, 12), device=device),
        'map_masks_multi_ious_unions': torch.zeros((7, 12), device=device),
        'map_seg_thresholds': torch.zeros(12, device=device)
    }

    day_map_metrics = {k: v.clone() for k, v in map_metrics.items()}
    rain_map_metrics = {k: v.clone() for k, v in map_metrics.items()}
    night_map_metrics = {k: v.clone() for k, v in map_metrics.items()}

    map_ious = {}
    day_map_ious = {}
    rain_map_ious = {}
    night_map_ious = {}
    mean_map_iou = 0.0
    day_mean_map_iou = 0.0
    rain_mean_map_iou = 0.0
    night_mean_map_iou = 0.0

    inference_time = 0.0

    while global_step < max_iters:
        global_step += 1

        if do_drn_val_split:
            if global_step <= val_day_len:
                eval_status = "DAY"
            if val_day_len < global_step <= (val_day_len + val_rain_len):
                eval_status = "RAIN"
            if global_step > val_day_len + val_rain_len:
                eval_status = "NIGHT"

        iter_start_time = time.time()
        read_start_time = time.time()

        sw_ev = utils.improc.Summ_writer(
            writer=writer_ev,
            global_step=global_step,
            log_freq=log_freq,
            fps=2,
            scalar_freq=int(log_freq / 2),
            just_gif=True)
        sw_ev.save_this = False

        try:
            sample = next(val_iterloader)
        except StopIteration:
            break

        read_time = time.time() - read_start_time

        with torch.no_grad():
            total_loss, metrics, inference_t = run_model(model, seg_loss_fn, map_seg_loss_fn, sample, device, sw_ev,
                                                         use_radar_encoder, radar_encoder_type, train_task,
                                                         use_shallow_metadata=use_shallow_metadata,
                                                         use_obj_layer_only_on_map=use_obj_layer_only_on_map)
            inference_time += inference_t

        # range based iou clac
        # obj
        if train_task in ['both', 'object']:
            # Update overall metrics
            update_metrics(metric_prefix='obj', condition_metrics_dict=obj_metrics, metrics_model=metrics)
            update_range_metrics(metric_prefix='obj', range_metric_dict=obj_metrics, metrics_model=metrics)

            # Update day, rain, and night metrics
            if eval_status == "DAY":
                update_metrics('obj', day_metrics, metrics)
                update_range_metrics('obj', day_metrics, metrics)
            elif eval_status == "RAIN":
                update_metrics('obj', rain_metrics, metrics)
                update_range_metrics('obj', rain_metrics, metrics)
            elif eval_status == "NIGHT":
                update_metrics('obj', night_metrics, metrics)
                update_range_metrics('obj', night_metrics, metrics)

        # map
        if train_task in ['both', 'map']:
            # Calculate IOUs
            map_ious, mean_map_iou = update_and_calculate_map_metrics(eval_status='ALL', metrics=metrics,
                                                                      map_metrics=map_metrics,
                                                                      iou_labels=iou_labels)

            # Update day, rain, and night map metrics
            # short version
            if eval_status == "DAY":
                day_map_ious, day_mean_map_iou = update_and_calculate_map_metrics(eval_status='DAY',
                                                                                  metrics=metrics,
                                                                                  map_metrics=day_map_metrics,
                                                                                  iou_labels=iou_labels)
            elif eval_status == "RAIN":
                rain_map_ious, rain_mean_map_iou = update_and_calculate_map_metrics(eval_status='RAIN',
                                                                                    metrics=metrics,
                                                                                    map_metrics=rain_map_metrics,
                                                                                    iou_labels=iou_labels)
            elif eval_status == "NIGHT":
                night_map_ious, night_mean_map_iou = update_and_calculate_map_metrics(eval_status='NIGHT',
                                                                                      metrics=metrics,
                                                                                      map_metrics=night_map_metrics,
                                                                                      iou_labels=iou_labels)

        loss_pool_ev.update([total_loss.item()])
        sw_ev.summ_scalar('pooled/total_loss', loss_pool_ev.mean())
        sw_ev.summ_scalar('stats/total_loss', total_loss.item())

        iter_time = time.time() - iter_start_time

        time_pool_ev.update([iter_time])
        sw_ev.summ_scalar('pooled/time_per_batch', time_pool_ev.mean())
        sw_ev.summ_scalar('pooled/time_per_el', time_pool_ev.mean() / float(B))

        if train_task == 'object':
            print('%s; step %06d/%d; rtime %.2f; itime %.2f (%.2f ms); loss %.5f; iou_ev %.1f' % (
                model_name, global_step, max_iters, read_time, iter_time, 1000 * time_pool_ev.mean(),
                total_loss.item(), obj_metrics['obj_iou']))

        if train_task == 'map':
            print('%s; step %06d/%d; rtime %.2f; itime %.2f (%.2f ms); loss %.5f; m_map_iou %.1f; driv %.1f; '
                  'carp %.1f; ped_cr %.1f; walkw %.1f; stop %.1f; road %.1f; lane %.1f' % (
                      model_name, global_step, max_iters, read_time, iter_time, 1000 * time_pool_ev.mean(),
                      total_loss.item(), mean_map_iou, map_ious['drivable_iou'].item(),
                      map_ious['carpark_iou'].item(), map_ious['ped_cross_iou'].item(), map_ious['walkway_iou'].item(),
                      map_ious['stop_line_iou'].item(), map_ious['road_divider_iou'].item(),
                      map_ious['lane_divider_iou'].item()))

        if train_task == 'both':
            print('%s; step %06d/%d; eval_status: %s; rtime %.2f; itime %.2f (%.2f ms); loss %.5f; iou_ev %.1f; '
                  'm_map_iou %.1f; driv %.1f; carp %.1f; ped_cr %.1f; walkw %.1f; stop %.1f; road %.1f; lane %.1f' % (
                    model_name, global_step, max_iters, eval_status, read_time, iter_time, 1000 * time_pool_ev.mean(),
                    total_loss.item(), obj_metrics['obj_iou'], mean_map_iou, map_ious['drivable_iou'].item(),
                    map_ious['carpark_iou'].item(), map_ious['ped_cross_iou'].item(), map_ious['walkway_iou'].item(),
                    map_ious['stop_line_iou'].item(), map_ious['road_divider_iou'].item(),
                    map_ious['lane_divider_iou'].item()))

    # print final metrics in terminal
    display_final_results(train_task=train_task, dset=dset, obj_metrics=obj_metrics, day_metrics=day_metrics,
                          rain_metrics=rain_metrics, night_metrics=night_metrics, map_metrics=map_metrics,
                          day_map_metrics=day_map_metrics, rain_map_metrics=rain_map_metrics,
                          night_map_metrics=night_map_metrics, mean_map_iou=mean_map_iou, map_ious=map_ious,
                          day_mean_map_iou=day_mean_map_iou, day_map_ious=day_map_ious,
                          rain_mean_map_iou=rain_mean_map_iou, rain_map_ious=rain_map_ious,
                          night_mean_map_iou=night_mean_map_iou, night_map_ious=night_map_ious,
                          do_drn_val_split=do_drn_val_split)

    mean_inference_time = inference_time / max_iters
    print("Mean inference time across val split: ", mean_inference_time)
    writer_ev.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run evaluation with model-specific config.')
    parser.add_argument('--config', type=str, required=True, help='Path to the config file')

    args = parser.parse_args()

    # Load the config file
    with open(args.config, 'r') as file:
        config = yaml.safe_load(file)

    main(**config)
