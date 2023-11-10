import sys

sys.path.append('..')

import cv2
import math
import torch
import lpips
import argparse
import numpy as np
import os.path as osp
from model.pytorch_msssim import ssim_matlab
from model.RIFE_sdi import Model
from utils import Logger
from basicsr.metrics.niqe import calculate_niqe

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

if __name__ == '__main__':
    """
    cmd:
    CUDA_VISIBLE_DEVICES=4 python Vimeo90K_sdi.py --model_dir ../experiments/rife_sdi_m_noavg_blur_triplet/train_sdi_log --testset_path /mnt/disks/ssd0/dataset/vimeo_triplet/ --blur --clip
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--model_dir', type=str, default='train_sdi_log')
    parser.add_argument('--testset_path', type=str, default='../dataset/vimeo_triplet/')
    parser.add_argument('--blur', action='store_true', help='use blurred sdi map')
    parser.add_argument('--clip', action='store_true', help='use clipped sdi map')
    parser.add_argument('--sdi_name', type=str, default='dis_index_0_1_2.npy')

    args = parser.parse_args()

    model = Model()
    model.load_model(args.model_dir)
    model.eval()
    model.device()

    logger = Logger(osp.join(args.model_dir, 'test_log.txt'))

    path = args.testset_path
    f = open(path + 'tri_testlist.txt', 'r')
    psnr_list = []
    ssim_list = []
    lpips_list = []
    niqe_list = []
    loss_fn_alex = lpips.LPIPS(net='alex').to(device)
    for i in f:
        name = str(i).strip()
        if (len(name) <= 1):
            continue
        print(path + 'sequences/' + name + '/im1.png')
        I0 = cv2.imread(path + 'sequences/' + name + '/im1.png')
        I1 = cv2.imread(path + 'sequences/' + name + '/im2.png')
        I2 = cv2.imread(path + 'sequences/' + name + '/im3.png')
        sdi_map = np.load(path + 'sequences/' + name + '/{}'.format(args.sdi_name)).astype(np.float32)

        if args.clip:
            sdi_map = np.clip(sdi_map, 0, 1)
        if args.blur:
            sdi_map = cv2.GaussianBlur(sdi_map, (5, 5), 0)

        I0 = (torch.tensor(I0.transpose(2, 0, 1)).to(device) / 255.)[None]
        I2 = (torch.tensor(I2.transpose(2, 0, 1)).to(device) / 255.)[None]
        h, w, _ = I1.shape
        sdi_map = cv2.resize(sdi_map, dsize=(w, h), interpolation=cv2.INTER_AREA)[..., np.newaxis]
        sdi_map = np.ascontiguousarray(sdi_map)
        sdi_map = torch.from_numpy(sdi_map).permute(2, 0, 1).to(device)[None]
        mid = model.inference(I0, I2, sdi_map=sdi_map)[0]
        ssim = ssim_matlab(torch.tensor(I1.transpose(2, 0, 1)).to(device).unsqueeze(0) / 255.,
                           torch.round(mid * 255).unsqueeze(0) / 255.).detach().cpu().numpy()
        mid = np.round((mid * 255).detach().cpu().numpy()).astype('uint8').transpose(1, 2, 0) / 255.
        I1 = I1 / 255.
        psnr = -10 * math.log10(((I1 - mid) * (I1 - mid)).mean())
        psnr_list.append(psnr)
        ssim_list.append(ssim)

        # calculate niqe score
        niqe = calculate_niqe(mid * 255., crop_border=0)
        niqe_list.append(niqe)

        # calculate lpips score
        mid = mid[:, :, ::-1]  # rgb image
        mid = torch.from_numpy(2 * mid - 1.).permute(2, 0, 1)[None].float().to(
            device
        )  # (1, 3, h, w) value range from [-1, 1]
        I1 = I1[:, :, ::-1]  # rgb image
        I1 = torch.from_numpy(2 * I1 - 1.).permute(2, 0, 1)[None].float().to(
            device
        )  # (1, 3, h, w) value range from [-1, 1]
        lpips_value = loss_fn_alex.forward(mid, I1).detach().cpu().numpy()
        lpips_list.append(lpips_value)
        logger("Avg PSNR: {:.4f} SSIM: {:.4f} LPIPS: {:.4f} NIQE: {:.4f}".format(
            np.mean(psnr), np.mean(ssim), np.mean(lpips_value), np.mean(niqe)
        ))

    logger("Total Avg PSNR: {:.4f} SSIM: {:.4f} LPIPS: {:.4f} NIQE: {:.4f}".format(
        np.mean(psnr_list), np.mean(ssim_list), np.mean(lpips_list), np.mean(niqe_list)
    ))
