import numpy as np
import zarr
import tifffile
import pandas as pd

import sys
import os
from collections import Counter

import argparse

# check create directory #
def check_create_dir(PATH):
    if os.path.exists(PATH) == False:
        os.makedirs(PATH)
        print('directory created: ', PATH)
    else:
        print('directory already exists:', PATH)

# extract batch and time point to generate outfile name prefix #
def get_batch_time(N5path):
    S = N5path.split('/')[-3:] # split by /, grab last three (batch time)
    for s in S:
        if (len(s) in [2,3,4]) and s.startswith("b") and any(char.isdigit() for char in s):  # look for string that has length of 2,3,4 and starts with b and contains a number
            B = s
        if (len(s) in [2,3,4]) and s.startswith("t") and any(char.isdigit() for char in s): # look for string that has length of 2,3,4 and starts with b and contains a number
            T = s
    return B,T

# assumes length of (c1,c2), excludes (c10,c100)
def get_channels(N5path):
    S = os.listdir(N5path)
    channels = []
    for s in S:
        if len(s)==2 and s.startswith("c"):  # look for string that has length of 2 and starts with c
            channels.append(s)
    return channels

# returns list of start coordinates and list of stop coordinates
def get_crop_coordinates(seg,idx_lst):
    zyxi_lst = []
    zyxf_lst = []
    for i in range(len(idx_lst)):
        p = np.where(seg==idx_lst[i])
        zyxi_lst.append([np.min(dim) for dim in p])
        zyxf_lst.append([np.max(dim) for dim in p])    
    return np.stack(zyxi_lst,axis=0),np.stack(zyxf_lst,axis=0)


##### generate crop from start/stop coordinates #######
def make_crop(img,zyxi,zyxf):
    region = tuple(slice(a, b) for a, b in zip(zyxi,zyxf))
    crop = img[region]
    return crop

def main():
    ### arguments and help messages ###
    usage_text = ("Usage:" + " .py -f ../b0/t0, -seg ../step4/Mask_b0_t0_c3_s2.tiff, -idx 1000 -o ../step?/")
    parser = argparse.ArgumentParser(description=usage_text,usage=argparse.SUPPRESS)
    parser.add_argument('-f','--fixdir',dest='fixdir',type=str,help='path to fix N5',required=True,metavar='')
    parser.add_argument('-seg','--segmentation',dest='seg',type=str,help='path to segmentation mask',required=True,metavar='')
    parser.add_argument('-idx','--index',dest='idx_lst',type=str,help='comma separated list of indices of segments',required=True,metavar='')
    parser.add_argument('-o','--outdir',dest='outdir',type=str,help='output directory',required=True,metavar='')
    args=parser.parse_args()

    # format index list #
    seg_idx_lst = [int(i) for i in args.idx_lst.split(',')]
    print(seg_idx_lst)

    # check create output directory #
    check_create_dir(args.outdir)

    # get the s0_spacing #
    subpath = 'c0/s0'
    fix_zarr = zarr.open(store=zarr.N5FSStore(args.fixdir),mode='r')
    fix = fix_zarr[subpath]
    spacing_s0 = np.multiply(fix.attrs.asdict()['pixelResolution'],fix.attrs.asdict()['downsamplingFactors'])[::-1]
    print("spacing_s0: ", spacing_s0)

    # get the spacing of mask #
    seg_path = args.seg
    seg_btcs = seg_path.split('/')[-1].split('.')[0].split('_')[1:]
    print('segmentation: ',seg_btcs)
    subpath = 'c0/'+str(seg_btcs[3])
    fix = fix_zarr[subpath]
    spacing_seg = np.multiply(fix.attrs.asdict()['pixelResolution'],fix.attrs.asdict()['downsamplingFactors'])[::-1]
    print("spacing_seg: ", spacing_seg)


    # get coordinates to be cropped #
    seg = tifffile.imread(args.seg)
    
    zyxi_sSeg,zyxf_sSeg = get_crop_coordinates(seg=seg,idx_lst=seg_idx_lst)
    print('segmentation start: ',zyxf_sSeg)
    print('segmentation end: ',zyxf_sSeg)
    zyxi_s0 = np.round(zyxi_sSeg * spacing_seg / spacing_s0).astype(int)
    zyxf_s0 = np.round(zyxf_sSeg * spacing_seg / spacing_s0).astype(int)

    #########################################################################################################################################################

    fixBT = get_batch_time(args.fixdir)
    dapi = str(seg_btcs[2])

    ############### loop through each crop index #####################

    for i in range(len(seg_idx_lst)):
        # make binary mask 0,1 where 1 is the index, used to mask out other cells in the cropped region #
        seg_crop_sSeg_i = make_crop(seg,zyxi_sSeg[i],zyxf_sSeg[i])
        seg_bin = seg_crop_sSeg_i==seg_idx_lst[i]
        seg_crop_sSeg_i[seg_bin] = 1
        seg_crop_sSeg_i[np.invert(seg_bin)] = 0

        import scipy.ndimage
        seg_crop_s0_i = scipy.ndimage.zoom(input=seg_crop_sSeg_i, zoom=np.divide(spacing_seg,spacing_s0), order=0, mode='constant',)

        #### loop through channels ####
        fix_channels = get_channels(args.fixdir)

        for c in fix_channels:
            print(str(c))
            subpath = str(c)+'/s0'
            fix = fix_zarr[subpath]
            fix_crop_s0_i = make_crop(fix,zyxi_s0[i],zyxf_s0[i])
            fixfile_prefix = 'fix_'+fixBT[0]+'_'+fixBT[1]+'_'+str(c)+'_s0_'+str(seg_idx_lst[i])
            fix_tiff = os.path.join(args.outdir,fixfile_prefix+'.tiff')
            tifffile.imwrite(fix_tiff,np.multiply(fix_crop_s0_i,seg_crop_s0_i),imagej=True, metadata={'axes': 'ZYX'})



            
if __name__ == '__main__':
    main()       
        

            

