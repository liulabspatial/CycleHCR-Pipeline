import os, shutil, sys
import argparse
import numpy as np
import logging
from cellpose import core, utils, io, models, metrics, transforms
from tqdm import trange
import fastremap
from cellpose.io import logger_setup
from cellpose.transforms import normalize99
from cellpose.io import imsave
import zarr

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
    parser.add_argument("--min", dest="min", type=int, default=400, help="minimum size of segment")
    parser.add_argument("--diameter", dest="diameter", type=float, default=10., help="diameter of segment")
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

    use_GPU = core.use_gpu()
    yn = ['NO', 'YES']
    print(f'>>> GPU activated? {yn[use_GPU]}')

    # call logger_setup to have output of cellpose written
    logger_setup();

    print(input)
    n5_dataset = zarr.open(input, mode='r')[n5path]
    dapi = np.array(n5_dataset)

    print("dapi channel")
    print("\r shape: {0}".format(dapi.shape))
    print("\r dtype: {0}".format(dapi.dtype))
    print("\r min: {0}".format(dapi.min()))
    print("\r max: {0}".format(dapi.max()), "\n")

    dapi_norm = normalize99(dapi)

    model = models.CellposeModel(gpu=True, model_type="nuclei")
    masks_sp = np.zeros(dapi_norm.shape, dtype="uint32")
    for i in trange(len(dapi_norm)):
        # run with normalization off
        masks0 = model.eval(dapi_norm[i], diameter=diameter, flow_threshold=0.0, normalize=False)[0]
        masks_sp[i] = masks0
    
    masks_stitch = stitch3D(masks_sp, stitch_threshold=0.5)
    print(f"{masks_stitch.max()} masks after stitching")

    masks_final = utils.fill_holes_and_remove_small_masks(masks_stitch.copy(), min_size=minsize)
    print(f"removed {masks_stitch.max() - masks_final.max()} masks smaller than {0} pixels", minsize)

    io.imsave(output, masks_final)

if __name__ == '__main__':
    main()