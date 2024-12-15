import os

import os
import sys
import re
import argparse

import nd2

import dask
import dask.array as da
import dask.bag as db
import dask.dataframe as dd
import zarr
import numpy as np

from dask.distributed import LocalCluster, Client

from dask.diagnostics import ProgressBar, Profiler, ResourceProfiler, CacheProfiler, visualize

from pathlib import Path

import tifffile

def get_key_index(dictionary, key):
    for i, k in enumerate(dictionary.keys()):
        if k == key:
            return i
    return -1

def nd2tiff():

    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  nd2n5.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input files")
    parser.add_argument("-o", "--output", dest="output", type=str, default=None, help="output file path (.xml)")
    parser.add_argument("-b", "--bg", dest="bg", type=str, default=None, help="background file path (.xml)")
    parser.add_argument("--verbose", dest="verbose", default=False, action="store_true", help="enable verbose logging")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    input = args.input
    outpath = args.output
    outdir = os.path.dirname(outpath)
    bg = args.bg

    numbers = re.findall(r'\d+', outpath)
    time_id = int(numbers[len(numbers)-1])
    ch_id = int(numbers[len(numbers)-2])
    tile_id = int(numbers[len(numbers)-3])
    print(time_id)
    print(ch_id)
    print(tile_id)

    Path(outdir).mkdir(parents=True, exist_ok=True)

    darray = nd2.imread(input, dask=True)

    print(darray.shape)

    timepoints = 1
    tiles = 1
    channels = 1
    timepoints_idx = -1
    tiles_idx = -1
    channels_idx = -1
    z_idx = 0
    y_idx = 1
    x_idx = 2
    with nd2.ND2File(input) as nd2file:
        print(nd2file.sizes)
        if 'T' in nd2file.sizes:
            timepoints = nd2file.sizes['T']
            timepoints_idx = get_key_index(nd2file.sizes, 'T')
        if 'P' in nd2file.sizes:
            tiles = nd2file.sizes['P']
            tiles_idx = get_key_index(nd2file.sizes, 'P')
        if 'C' in nd2file.sizes:
            channels = nd2file.sizes['C']
            channels_idx = get_key_index(nd2file.sizes, 'C')
        if 'X' in nd2file.sizes:
            w = nd2file.sizes['X']
            x_idx = get_key_index(nd2file.sizes, 'X')
        if 'Y' in nd2file.sizes:
            h = nd2file.sizes['Y']
            y_idx = get_key_index(nd2file.sizes, 'Y')
        if 'Z' in nd2file.sizes:
            d = nd2file.sizes['Z']
            z_idx = get_key_index(nd2file.sizes, 'Z')

    d = darray.shape[z_idx]
    h = darray.shape[y_idx]
    w = darray.shape[x_idx]

    output = np.zeros((d, h, w), dtype=darray.dtype)
    if timepoints_idx >= 0:
        if tiles_idx >= 0:
            if channels_idx >= 0:
                output[:d, :h, :w] = darray[time_id, tile_id, :d, ch_id, :h, :w]
            else:
                output[:d, :h, :w] = darray[time_id, tile_id, :d, :h, :w]
        else:
            if channels_idx >= 0:
                output[:d, :h, :w] = darray[time_id, :d, ch_id, :h, :w]
            else:
                output[:d, :h, :w] = darray[time_id, :d, :h, :w]
    else:
        if tiles_idx >= 0:
            if channels_idx >= 0:
                output[:d, :h, :w] = darray[tile_id, :d, ch_id, :h, :w]
            else:
                output[:d, :h, :w] = darray[tile_id, :d, :h, :w]
        else:
            if channels_idx >= 0:
                output[:d, :h, :w] = darray[:d, ch_id, :h, :w]
            else:
                output[:d, :h, :w] = darray[:d, :h, :w]

    tifffile.imsave(outpath, output, compression=("ZLIB", 6))

def main():
    nd2tiff()

if __name__ == '__main__':
    main()
