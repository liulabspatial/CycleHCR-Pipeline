import zarr
import numpy as np
import tifffile

import sys
import os
import re

import argparse


def check_create_dir(path):
    os.makedirs(path, exist_ok=True)
    print(f"Directory ready: {path}")

def get_channels(ZARRpath):
    z = zarr.open(store=ZARRpath,mode='r')
    z_metadata = z['c0'].attrs
    channels = z_metadata['multiscales'][0]['paths']
    return channels

# extract point and time to generate outfile name prefix #
def get_point_time(ZARRpath):
    S = ZARRpath.split('/')[-3:] # split by /
    for s in S:
        if (len(s) in [2,3]) and s.startswith("p") and any(char.isdigit() for char in s):  # look for string that has length of 2,3,4 and starts with b and contains a number
            P = s
        elif (len(s) in [2,3]) and s.startswith("t") and any(char.isdigit() for char in s): # look for string that has length of 2,3,4 and starts with t and contains a number
            T = s
    return P,T

def main():
    ### arguments and help messages ###
    usage_text = ("Usage:" + " .py -f fix.n5")
    parser = argparse.ArgumentParser(description=usage_text,usage=argparse.SUPPRESS)
    parser.add_argument('-f','--fixdir',dest='fixdir',type=str,help='path to fix N5',required=True,metavar='')
    parser.add_argument('-s','--res',dest='res',type=str,help='image resolution to register (e.g. s2)',required=True,metavar='')
    parser.add_argument('-o','--outdir',dest='outdir',type=str,help='output directory',required=True,metavar='')

    args=parser.parse_args()

    outdir_registered = os.path.join(args.outdir,'registered') # subdirectory 'registered'
    check_create_dir(outdir_registered)

    fixPT = get_point_time(args.fixdir)
    channels = get_channels(args.fixdir)
    res = str(int(re.search(r'\d+', str(args.res)).group()))

    channels_missing = []
    for c in channels:
        fix_prefix = f"fix_{fixPT[0]}_{fixPT[1]}_c{c}_s{res}"
        fix_checkpoint_path = os.path.join(outdir_registered,fix_prefix+".checkpoint")
        if os.path.exists(fix_checkpoint_path):
            print("skipping resaving, tiff file already exists: ",fix_checkpoint_path)
        else:
            channels_missing.append(c)
    if not channels_missing:
        return
    else:
        fix_zarr = zarr.open(store=args.fixdir, mode='r')
        for c in channels_missing:
            fix = fix_zarr['c'+c][res][0,0,:,:,:].astype(np.uint16)
            fix_prefix = f"fix_{fixPT[0]}_{fixPT[1]}_c{c}_s{res}"
            fix_tiff = os.path.join(outdir_registered,fix_prefix+'.tiff') # = outdir/registered/fix_prefix.tiff
            tifffile.imwrite(fix_tiff, fix, imagej=True, metadata={'axes':'ZYX'})
            fix_checkpoint_path = os.path.join(outdir_registered,fix_prefix+".checkpoint")
            print('resaving complete, creating checkpoint file: ', fix_checkpoint_path)
            with open(fix_checkpoint_path, 'w') as fp:
                pass


            
if __name__ == '__main__':
    main()
