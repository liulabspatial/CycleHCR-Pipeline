import os, shutil, sys
import argparse
import numpy as np
import logging
from cellpose import core, utils, io, models, metrics, transforms, dynamics
from tqdm import trange
import fastremap
from cellpose.io import logger_setup
from cellpose.transforms import normalize99
from cellpose.io import imsave
import z5py
import tifffile
import torch
from pathlib import Path

def stitch3D(masks, stitch_threshold=0.25):
    """ new stitch3D function that won't slow down w/ large numbers of masks"""
    mmax = masks[0].max()
    empty = 0
    
    for i in trange(len(masks)-1):
        iunique, masks_unique = fastremap.unique(masks[i], return_inverse=True)
        iou = metrics._intersection_over_union(masks[i+1], masks_unique)[1:,1:]
        if not iou.size and empty == 0:
            masks[i+1] = masks[i+1]
            mmax = masks[i+1].max()
        elif not iou.size and not empty == 0:
            icount = masks[i+1].max()
            istitch = np.arange(mmax+1, mmax + icount+1, 1, int)
            mmax += icount
            istitch = np.append(np.array(0), istitch)
            masks[i+1] = istitch[masks[i+1]]
        else:
            iou[iou < stitch_threshold] = 0.0
            iou[iou < iou.max(axis=0)] = 0.0
            istitch = iunique[iou.argmax(axis=1) + 1]
            ino = np.nonzero(iou.max(axis=1)==0.0)[0]
            istitch[ino] = np.arange(mmax+1, mmax+len(ino)+1, 1, int)
            mmax += len(ino)
            istitch = np.append(np.array(0), istitch)
            masks[i+1] = istitch[masks[i+1]]
            empty = 1
    return masks

def main():
    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  cellpose.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input n5 dataset")
    parser.add_argument("-n", "--n5path", dest="n5path", type=str, default=None, help="input n5 dataset path (e.g. c0/s1)")
    parser.add_argument("-o", "--output", dest="output", type=str, default=None, help="output file path (.tif)")
    parser.add_argument("--model", dest="model", type=str, default=None, help="model file path")
    parser.add_argument("--model_xy", dest="model_xy", type=str, default=None, help="xy model file path")
    parser.add_argument("--model_yz", dest="model_yz", type=str, default=None, help="yz model file path")
    parser.add_argument("--min", dest="min", type=int, default=400, help="minimum size of segment")
    parser.add_argument("--diameter", dest="diameter", type=float, default=0., help="diameter of segment")
    parser.add_argument("--anisotropy", dest="anisotropy", type=float, default=None, help="Optional rescaling factor (e.g. set to 2.0 if Z is sampled half as dense as X or Y). Defaults to None.")
    parser.add_argument("--verbose", dest="verbose", default=False, action="store_true", help="enable verbose logging")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    input = args.input
    n5path = args.n5path
    output = args.output
    minsize = args.min
    diameter = args.diameter
    model_path = args.model
    model_xy_path = args.model_xy
    model_yz_path = args.model_yz
    anisotropy = args.anisotropy

    device = torch.device("cuda")

    # call logger_setup to have output of cellpose written
    logger_setup();

    print(input)
    print(n5path)
    img = None
    if Path(input).suffix.lower() in ['.tif', '.tiff']:
        img = tifffile.imread(input)
    else:
        n5input = z5py.File(input, use_zarr_format=False)
        n5_dataset = n5input[n5path]
        img = np.array(n5_dataset)

    print("dapi channel")
    print("\r shape: {0}".format(img.shape))
    print("\r dtype: {0}".format(img.dtype))
    print("\r min: {0}".format(img.min()))
    print("\r max: {0}".format(img.max()), "\n")

    img = normalize99(img)

    if model_path is not None:
        model = models.CellposeModel(gpu=True, pretrained_model=model_path)
        diameter = model.diam_labels if diameter==0 else diameter
        print("\r diameter: {0}".format(diameter))
        masks, flows, styles = model.eval(img, diameter=diameter, flow_threshold=0.0, do_3D=True, normalize=False, anisotropy=anisotropy)
        masks_pred0 = utils.fill_holes_and_remove_small_masks(masks.copy(), min_size=minsize)
    else:
        modelXY = models.CellposeModel(pretrained_model=model_xy_path, gpu=True)
        modelYZ = models.CellposeModel(pretrained_model=model_yz_path, gpu=True)
        diameterXY = modelXY.diam_labels
        diameterYZ = modelYZ.diam_labels

        # compute the flows
        nchan = 2

        shape = img.shape
        cellprob = np.zeros((3, *shape), "float32")
        dP = np.zeros((3, 2, *shape), "float32")

        pm = [(0,1,2), (1,0,2), (2,0,1)]
        ipm = [(0,1,2), (1,0,2), (1,2,0)]

        for p in range(0, 3):
            print(p)
            img0 = img.copy().transpose(pm[p])
            y = np.zeros((3, *img0.shape), "float32")
            for z in trange(img0.shape[0]):
                if p==0:
                    _, flows, _ = modelXY.eval(img0[z], batch_size=128, compute_masks=False, diameter=diameterXY, anisotropy=anisotropy)
                else:
                    _, flows, _ = modelYZ.eval(img0[z], batch_size=128, compute_masks=False, diameter=diameterYZ, anisotropy=anisotropy)
                y[:2, z] = flows[1].squeeze()
                y[-1, z] = flows[2].squeeze()
            dP[p, 0] = y[0].transpose(ipm[p])
            dP[p, 1] = y[1].transpose(ipm[p])
            cellprob[p] = y[-1].transpose(ipm[p])

        # average predictions from 3 views
        cellprob_all = cellprob.mean(axis=0)
        dP_all = np.stack((dP[1][0] + dP[2][0], dP[0][0] + dP[2][1], dP[0][1] + dP[1][1]), axis=0) # (dZ, dY, dX)

        # compute masks (most memory intensive)
        masks_pred, p = dynamics.compute_masks(dP_all, cellprob_all, do_3D=True, device=device)

        # remove cells below a certain size
        masks_pred0 = utils.fill_holes_and_remove_small_masks(masks_pred, min_size=minsize)

    io.imsave(output, masks_pred0)

if __name__ == '__main__':
    main()