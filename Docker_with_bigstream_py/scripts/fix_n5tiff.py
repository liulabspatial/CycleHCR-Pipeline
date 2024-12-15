import zarr
import numpy as np
import tifffile

import sys
import os

import argparse


def check_create_dir(PATH):
    if os.path.exists(PATH) == False:
        os.makedirs(PATH)
        print('directory created: ', PATH)
    else:
        print('directory already exists:', PATH)

# assumes length of (c1,c2), excludes (c10,c100)
def get_channels(N5path):
    S = os.listdir(N5path)
    channels = []
    for s in S:
        if len(s)==2 and s.startswith("c"):  # look for string that has length of 2 and starts with c
            channels.append(s)
    return channels

# extract batch and time point to generate outfile name prefix #
def get_batch_time(N5path):
    S = N5path.split('/')[-3:] # split by /
    for s in S:
        if (len(s) in [2,3,4]) and s.startswith("b") and any(char.isdigit() for char in s):  # look for string that has length of 2,3,4 and starts with b and contains a number
            B = s
        if (len(s) in [2,3,4]) and s.startswith("t") and any(char.isdigit() for char in s): # look for string that has length of 2,3,4 and starts with b and contains a number
            T = s
    return B,T

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

    fixBT = get_batch_time(args.fixdir)
    channels = get_channels(args.fixdir)

    channels_missing = []
    for c in channels:
        fix_prefix = 'fix_'+fixBT[0]+'_'+fixBT[1]+'_'+c+'_'+args.res
        fix_checkpoint_path = os.path.join(outdir_registered,fix_prefix+".checkpoint")
        if os.path.exists(fix_checkpoint_path):
            print("skipping resaving, tiff file already exists: ",fix_checkpoint_path)
        else:
            channels_missing.append(c)
    if not channels_missing:
        return
    else:
        fix_zarr = zarr.open(store=zarr.N5FSStore(args.fixdir),mode='r')
        for c in channels_missing:
            subpath = c+'/' + args.res
            fix = fix_zarr[subpath]
            fix_prefix = 'fix_'+fixBT[0]+'_'+fixBT[1]+'_'+c+'_'+args.res
            fix_tiff = os.path.join(outdir_registered,fix_prefix+'.tiff') # = outdir/registered/fix_prefix.tiff
            tifffile.imwrite(fix_tiff, fix, imagej=True, metadata={'axes':'ZYX'})
            fix_checkpoint_path = os.path.join(outdir_registered,fix_prefix+".checkpoint")
            print('resaving complete, creating checkpoint file: ', fix_checkpoint_path)
            with open(fix_checkpoint_path, 'w') as fp:
                pass

            
if __name__ == '__main__':
    main()
