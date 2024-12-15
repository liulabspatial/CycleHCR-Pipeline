import os

import os
import sys
import re
import argparse

import nd2
import zarr
import numpy as np

from pathlib import Path

def nd2tiffcsv():

    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  nd2tiffcsv.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input files")
    parser.add_argument("-o", "--output", dest="output", type=str, default=None, help="output file path (.xml)")
    parser.add_argument("--verbose", dest="verbose", default=False, action="store_true", help="enable verbose logging")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    input = args.input
    output = args.output

    darray = nd2.imread(input, dask=True)

    print(darray.shape)

    timepoints = 1
    tiles = 1
    channels = 1
    timepoints_idx = -1
    tiles_idx = -1
    channels_idx = -1
    with nd2.ND2File(input) as nd2file:
        print(nd2file.sizes)
        if 'T' in nd2file.sizes:
            timepoints = nd2file.sizes['T']
        if 'P' in nd2file.sizes:
            tiles = nd2file.sizes['P']
        if 'C' in nd2file.sizes:
            channels = nd2file.sizes['C']

    if tiles <= 1:
        print("single tile")
        testfile_path = os.path.join(os.path.dirname(output), "SingleTile")
        with open(testfile_path, 'w') as testfile:
            testfile.write("single tile data");

    outdir = os.path.dirname(output)
    Path(outdir).mkdir(parents=True, exist_ok=True)

    with open(output, 'w') as csvfile:
        for tile_id in range(tiles):
            for time_id in range(timepoints):
                for ch_id in range(channels):
                    csvfile.write(os.path.join(outdir, "tiff_" + str(tile_id) + "_" + str(ch_id) + "_" + str(time_id) + ".tif") + "\n")


def main():
    nd2tiffcsv()

if __name__ == '__main__':
    main()
