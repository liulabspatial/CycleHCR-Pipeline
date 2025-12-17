import numpy as np
import zarr
import tifffile
import pandas as pd
from scipy.ndimage import zoom

import sys
import os
import re
from collections import Counter

import argparse
import time

def check_create_dir(path):
    os.makedirs(path, exist_ok=True)
    print(f"Directory ready: {path}")

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
    usage_text = ("Usage:" + " .py -z zarrdir")
    parser = argparse.ArgumentParser(description=usage_text,usage=argparse.SUPPRESS)
    parser.add_argument('-z','--zarrdir',dest='zarrdir',type=str,help='path to zarr, whose spots have been called',required=True,metavar='')
    parser.add_argument('-td','--transformdir',dest='transformdir',type=str,help='path to transformdir',required=True,metavar='')
    parser.add_argument('-sd','--spotsdir',dest='spotsdir',type=str,help='path to spotsdir',required=True,metavar='')    
    parser.add_argument('-o','--outdir',dest='outdir',type=str,help='output directory',required=True,metavar='')

    # parameters for inverting transformation field (optional params) #
    # ignored if the transform matrix is 4x4 affine matrix #
    # iteration default 10
    parser.add_argument('--downsample_field_xy',dest='downsample_field_xy', type=str,help='downsampling factor applied to transform field before inverting',required=False,metavar='',default='4')
    parser.add_argument('--iterations',dest='iterations',type=str,help='The number of stationary point iterations to find inverse. More iterations for higher precision',required=False,metavar='',default='10')

    args=parser.parse_args()
    print(args)
    ### parameters format ###
    downsample_field_xy=int(args.downsample_field_xy)
    iterations = int(args.iterations)

    ### make output directory: no subdirectory ###
    check_create_dir(args.outdir)

    ### get batch time of the N5 used to call spots ###
    zarrPT = get_point_time(args.zarrdir)


################################################# the beginning of block dedicated to getting correct transform file prefix and spacing #################################################
    # zarrPT -> get transform checkpoint #
    transform_cp = []
    first_valid_file = None  # Store this for fixed image resolution
    with os.scandir(args.transformdir) as entries:
        for entry in entries:
            if entry.is_file():
                f = entry.name
                # Save the first file name (for fixed image case)
                if first_valid_file is None:
                    first_valid_file = f
                f_mov = f.split('-')[-1]
                if f"{zarrPT[0]}_{zarrPT[1]}" in f_mov and '.checkpoint' in f_mov:
                    transform_cp.append(f)
    
    # from trasnform_cp -> p,t,c,s
    if not transform_cp:
        # no checkpoint file, assume fix
        if not first_valid_file:
            raise ValueError("No files found to extract fixed image metadata.")
        transform_checkpoint = None
        transform_ptcs = first_valid_file.split('-')[0].split('_')
        isfiximage=True
    else:
        # Use moving image (checkpoint) metadata
        transform_checkpoint = transform_cp[0]
        transform_ptcs = transform_checkpoint.removesuffix('.checkpoint').split('-')[-1].split('_')

        last_part = transform_checkpoint.split('-')[-1]
        stripped = last_part.replace(".checkpoint", "")
        transform_ptcs = stripped.split('_')
        isfiximage=False

    # from p,t,c,s -> get spacing
    # Step 1: Identify transform resolution like "s0", "s1", etc.
    transform_res = None
    for s in transform_ptcs:
        if len(s) == 2 and s.startswith("s") and s[1].isdigit():
            transform_res = s
            break  # exit once found
    transform_res = str(int(re.search(r'\d+', str(transform_res)).group()))

    # Step 2: Read spacing metadata from zarr
    Zarr = zarr.open(store=args.zarrdir, mode='r')
    metadata = Zarr['c0'].attrs
    transform_spacing = np.multiply(metadata['Bigstitcher-Spark']['Spacings'][::-1], metadata['multiscales'][0]['datasets'][int(transform_res)]['coordinateTransformations'][0]['scale'][2:5])
    print('transform_spacing',transform_spacing)
    
################################################# the end of block dedicated to getting correct transform file prefix and spacing #################################################

################################################# the beginning of block dedicated to getting correct spots file prefix and spacing ###############################################
    spots_cp = []
    with os.scandir(args.spotsdir) as entries:
        for entry in entries:
            if entry.is_file():
                if f"{zarrPT[0]}_{zarrPT[1]}" in entry.name and '.checkpoint' in entry.name:
                    spots_cp.append(entry.name)
    spots_ptcs = spots_cp[0].replace(".checkpoint","").split('_')
    
    # from n5BT, get spots checkpoint #
    # Step 1: Identify transform resolution like "s0", "s1", etc.
    spots_res = None
    for s in spots_ptcs:
        if len(s) == 2 and s.startswith("s") and s[1].isdigit():
            spots_res = s
            break  # exit once found
    spots_res = str(int(re.search(r'\d+', str(spots_res)).group()))

    # Step 2: Read spacing metadata from N5/Zarr structure
    Zarr = zarr.open(store=args.zarrdir, mode='r')
    metadata = Zarr['c0'].attrs
    spots_spacing = np.multiply(metadata['Bigstitcher-Spark']['Spacings'][::-1], metadata['multiscales'][0]['datasets'][int(spots_res)]['coordinateTransformations'][0]['scale'][2:5])
    print('spots_spacing',spots_spacing)

################################################# the end of block dedicated to getting correct spots file prefix and spacing #################################################
    reg_spots_cp = []
    with os.scandir(args.outdir) as entries:
        for entry in entries:
            if entry.is_file():
                if f"{zarrPT[0]}_{zarrPT[1]}" in entry.name and '.checkpoint' in entry.name:
                    reg_spots_cp.append(entry.name)
                    
################ check spots for all channels are registered, ie check called spots = registered spots #################
    if len(spots_cp) != len(reg_spots_cp):
        if isfiximage==True:
            for c in spots_cp:
                if os.path.exists(os.path.join(args.spotsdir,c)):
                    spots_path = os.path.join(args.spotsdir,c.replace(".checkpoint",".csv"))
                    if not os.path.exists(spots_path):
                        print(f"CSV file not found, skipping: {spots_path}")
                        continue
                    spots = pd.read_csv(spots_path)
                else:
                    continue
                ### same block as mov image, fix_spots_zyx = spots_zyx ###
                spots_zyx = spots[['z','y','x']].to_numpy() * spots_spacing
                fix_spots_zyx = spots_zyx # no registration for fix image
                fix_spots_df = pd.DataFrame((fix_spots_zyx / transform_spacing)[:,::-1],columns=['x','y','z']) # zyx -> xyz when saving
                fix_spots = pd.concat([fix_spots_df,spots[['t','c','intensity']]],axis=1) # will bring back other columns of the spots data
                fix_spots_csv = "fix_"+c.replace("s"+str(spots_res),"s"+str(transform_res)).replace(".checkpoint",".csv")
                fix_spots.to_csv(os.path.join(args.outdir,fix_spots_csv),index=None)
                fix_spots_checkpoint_path = os.path.join(args.outdir,fix_spots_csv.replace(".csv",".checkpoint"))
                with open(fix_spots_checkpoint_path, 'w') as fp:
                    pass

        ### mov image ###
        else:
            print(args.transformdir)
            print(transform_checkpoint)
            if os.path.exists(os.path.join(args.transformdir,transform_checkpoint)):
                transform_path = os.path.join(args.transformdir,transform_checkpoint.replace(".checkpoint",".npy"))
                transform = np.load(transform_path)
            # check if this is affine #
            if transform.shape == (4,4):
                transform_invert = np.linalg.inv(transform)
            else:
                if downsample_field_xy!=1:
                    zoom_down = np.array([1,1/downsample_field_xy,1/downsample_field_xy,1])
                    transform = zoom(input=transform,zoom=zoom_down,order=0)
                    
                from bigstream.transform import invert_displacement_vector_field
                transform_spacing_down = np.multiply(transform_spacing, np.array([1,downsample_field_xy, downsample_field_xy]))

                transform_invert = invert_displacement_vector_field(
                        field=transform,
                        spacing=transform_spacing_down,
                        iterations=(iterations,),
                        )
                if downsample_field_xy!=1:
                    zoom_up=1/zoom_down
                    transform_invert = zoom(input=transform_invert,zoom=zoom_up,order=0)                    
            print('inversion complete', transform_invert.shape)
                    ### read the spots csv: this has 6 channels: x,y,z,t,c,intensity ###
            ## loop through the spots ##
            print(spots_cp)
            for c in spots_cp:
                if os.path.exists(os.path.join(args.spotsdir,c)):
                    spots_path = os.path.join(args.spotsdir,c.replace(".checkpoint",".csv"))
                    if not os.path.exists(spots_path):
                        print(f"CSV file not found, skipping: {spots_path}")
                        continue
                    spots = pd.read_csv(spots_path)
                else:
                    continue
                spots_zyx = spots[['z','y','x']].to_numpy() * spots_spacing    # only need z,y,x; convert to physical units

                ### transform spots, output is in physical spacing ###
                from bigstream.transform import apply_transform_to_coordinates
                reg_spots_zyx = apply_transform_to_coordinates(
                        coordinates=spots_zyx,
                        transform_list=[transform_invert],
                        transform_spacing=transform_spacing
                        )
                ## spots_zyx_reg is in physical spacing, convert back to voxel units of the transform field ##
                ## This should allow registered image and the registered spots to be correctly superimposed ##
                # spots_zyx_reg (um) / spacing_transform (um / voxel-s2) = spots_zyx_reg (voxel-s2 units) 
                reg_spots_df = pd.DataFrame((reg_spots_zyx / transform_spacing)[:,::-1],columns=['x','y','z']) # zyx -> xyz when saving
                reg_spots = pd.concat([reg_spots_df,spots[['t','c','intensity']]],axis=1) # will bring back other columns of the spots data
                reg_spots_csv = "reg_"+c.replace("s"+str(spots_res),"s"+str(transform_res)).replace(".checkpoint",".csv")
                reg_spots.to_csv(os.path.join(args.outdir,reg_spots_csv),index=None)
                reg_spots_checkpoint_path = os.path.join(args.outdir,reg_spots_csv.replace(".csv",".checkpoint"))
                with open(reg_spots_checkpoint_path, 'w') as fp:
                    pass

    else:
        print("no registration performed, checkpoint file already exists")



if __name__ == '__main__':
    main()
