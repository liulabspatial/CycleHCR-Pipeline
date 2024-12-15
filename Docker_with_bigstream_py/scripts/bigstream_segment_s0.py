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
    


## assumes segmentation was done in same resolution as transformation matrix
def get_warped_crop_coordinates(seg,idx_lst,spacing_seg,transform_lst,spacing_target):
    from bigstream.transform import apply_transform_to_coordinates

    ### start/stop of crop coordinates ###
    zyxi_seg,zyxf_seg = get_crop_coordinates(seg,idx_lst)

    ### obtain start/stop coordinates in mov data, better to be 'inclusive', not necessarily have to be in same shape as fix crop ###
    zyxi_warp = apply_transform_to_coordinates(
        zyxi_seg * spacing_seg ,
        transform_list=transform_lst,
        transform_spacing=spacing_seg,
        )
    zyxf_warp = apply_transform_to_coordinates(
        zyxf_seg * spacing_seg ,
        transform_list=transform_lst,
        transform_spacing=spacing_seg,
        )
    
    ### add padding +/-10 voxels ###
    zyxi_warp_padded_target = np.round(zyxi_warp / spacing_target).astype(int)
    zyxi_warp_padded_target -= 10
    zyxf_warp_padded_target = np.round(zyxf_warp / spacing_target).astype(int)
    zyxf_warp_padded_target += 10

    print(zyxi_warp_padded_target,zyxf_warp_padded_target)
    start = np.array(zyxi_warp_padded_target).copy()
    start[start<0] = 0
    end = np.array(zyxf_warp_padded_target).copy()
    end[end<0] = 0

    return start, end


# 0. get spacing s0, and spacing at which transform was performed
# 1. get coordinates to be cropped
# 2. crop fix s0 (reference to which mov_crop will be mapped to)
# 3. crop mov s0 (not registered) from warped coordinates
# 4. transform crop mov_s0
# 5. do another round of registration ??

def main():
    ### arguments and help messages ###
    usage_text = ("Usage:" + " .py -n ../b0/t1 -td ../step2/transform/ -seg ../step4/Mask_b0_t0_c3_s2.tiff, -idx 1000 -o ../step?/")
    parser = argparse.ArgumentParser(description=usage_text,usage=argparse.SUPPRESS)
    parser.add_argument('-f','--fixdir',dest='fixdir',type=str,help='path to fix N5',required=True,metavar='')
    parser.add_argument('-m','--movdir',dest='movdir',type=str,help='path to mov N5, for which the transform matrix exists',required=True,metavar='')
    parser.add_argument('-td','--transformdir',dest='transformdir',type=str,help='path to transformdir',required=True,metavar='')
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

    # warp crop coordinates #
    # read transform file #
    fixBT = get_batch_time(args.fixdir)
    movBT = get_batch_time(args.movdir)
    dapi = str(seg_btcs[2])
    transform_prefix = fixBT[0]+'_'+fixBT[1]+'_'+dapi+'_'+str(seg_btcs[3])+'-'+movBT[0]+'_'+movBT[1]+'_'+dapi+'_'+str(seg_btcs[3])
    print(transform_prefix)

    transform_checkpoint = os.path.join(args.transformdir,transform_prefix+'.checkpoint')
    transform_tiff = os.path.join(args.transformdir,transform_prefix+'.tiff')

    if os.path.exists(transform_checkpoint):
        affine_deform = np.moveaxis(tifffile.imread(transform_tiff),1,-1)
    else:
        print('transform matrix does not exist: ', transform_checkpoint)
        return
    
    ## get warped crop coordinates of interest ###
    zyxi_warp_padded_s0, zyxf_warp_padded_s0 = get_warped_crop_coordinates(seg=seg, idx_lst=seg_idx_lst, spacing_seg=spacing_seg, transform_lst=[affine_deform], spacing_target=spacing_s0)
    
    print('raw N5 start: ',zyxi_warp_padded_s0)
    print('raw N5 end: ',zyxf_warp_padded_s0)

    ############### loop through each crop index #####################
    # affine #
    affine_kwargs = {
        'alignment_spacing':1.0, # subsampling factor 
        'shrink_factors':(1,), # proper downsampling factor, can be done in sequential multi resolution
        'smooth_sigmas':(0.25,), # gaussian smoothing each level
        'optimizer_args':{
            'learningRate':0.25,
            'minStep':0.,
            'numberOfIterations':20,
        },
    }

    # deform #
    deform_kwargs = {
        'alignment_spacing':1.0,
        'shrink_factors':(1,),
        'smooth_sigmas':(0.25,),
        'control_point_spacing':1,
        'control_point_levels':(1,),
        'optimizer_args':{
            'learningRate':0.25,
            'minStep':0.,
            'numberOfIterations':20,
        },
    }


    for i in range(len(seg_idx_lst)):
        #### we will first work with dapi to get transform matrix for crop-registration ####
        subpath = dapi+'/s0'
        fix = fix_zarr[subpath]
        fix_crop_s0_i = make_crop(fix,zyxi_s0[i],zyxf_s0[i])
        print('fix s0 shape: ', fix_crop_s0_i.shape)

        mov_zarr = zarr.open(store=zarr.N5FSStore(args.movdir),mode='r')
        mov = mov_zarr[subpath]
        mov_crop_s0_i = make_crop(mov,zyxi_warp_padded_s0[i],zyxf_warp_padded_s0[i])

        # make binary mask 0,1 where 1 is the index, used to mask out other cells in the cropped region #
        seg_crop_sSeg_i = make_crop(seg,zyxi_sSeg[i],zyxf_sSeg[i])
        seg_bin = seg_crop_sSeg_i==seg_idx_lst[i]
        seg_crop_sSeg_i[seg_bin] = 1
        seg_crop_sSeg_i[np.invert(seg_bin)] = 0
#        print('segment crop shape: ',seg_crop_sSeg_i.shape)

        import scipy.ndimage
        seg_crop_s0_i = scipy.ndimage.zoom(input=seg_crop_sSeg_i, zoom=np.divide(spacing_seg,spacing_s0), order=0, mode='constant',)
#        print('segment s0 shape: ', seg_crop_s0_i.shape)

        from bigstream.transform import apply_transform
        mov_crop_s0_i_transform = apply_transform(
            fix=fix_crop_s0_i, mov=mov_crop_s0_i,
            fix_spacing=spacing_s0, mov_spacing=spacing_s0,
            transform_list=[affine_deform],
            transform_spacing=spacing_seg,
            fix_origin=zyxi_s0[i]*spacing_s0,
            mov_origin=zyxi_warp_padded_s0[i]*spacing_s0,
            interpolator='1'
        )
        
        #### perform registration in subset ####

        from bigstream.align import alignment_pipeline
        crop_affine_deform_i = alignment_pipeline(
            fix=fix_crop_s0_i, mov=mov_crop_s0_i_transform,
            fix_spacing=spacing_s0,mov_spacing=spacing_s0,
            steps=[('affine',affine_kwargs),('deform',deform_kwargs)]
        )
        
    
        #### loop through channels ####
        mov_channels = get_channels(args.movdir)
        for c in mov_channels:
            print(str(c))
            subpath = str(c)+'/s0'
            mov = mov_zarr[subpath]
            mov_crop_s0_i = make_crop(mov,zyxi_warp_padded_s0[i],zyxf_warp_padded_s0[i])
            mov_crop_s0_i_transform = apply_transform(
                fix=fix_crop_s0_i, mov=mov_crop_s0_i,
                fix_spacing=spacing_s0, mov_spacing=spacing_s0,
                transform_list=[affine_deform],
                transform_spacing=spacing_seg,
                fix_origin=zyxi_s0[i]*spacing_s0,
                mov_origin=zyxi_warp_padded_s0[i]*spacing_s0,
                interpolator='1',
                )          
            mov_crop_s0_i_transform2 = apply_transform(
                fix=fix_crop_s0_i,mov=mov_crop_s0_i_transform,
                fix_spacing=spacing_s0,mov_spacing=spacing_s0,
                transform_list=[crop_affine_deform_i],
                interpolator='1'
                )
            outfile_prefix = 'reg_'+movBT[0]+'_'+movBT[1]+'_'+str(c)+'_s0_'+str(seg_idx_lst[i])
            outfile_tiff = os.path.join(args.outdir,outfile_prefix+'.tiff')
            
            
            
            tifffile.imwrite(outfile_tiff,np.multiply(mov_crop_s0_i_transform2,seg_crop_s0_i),imagej=True, metadata={'axes': 'ZYX'})





if __name__ == '__main__':
    main()


