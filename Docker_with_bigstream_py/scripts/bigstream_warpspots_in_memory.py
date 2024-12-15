import numpy as np
import zarr
import tifffile
import pandas as pd
from scipy.ndimage import zoom

import sys
import os
from collections import Counter

import argparse
import time

def check_create_dir(PATH):
    if os.path.exists(PATH) == False:
        os.makedirs(PATH)
        print('directory created: ', PATH)
    else:
        print('directory already exists:', PATH)

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
    usage_text = ("Usage:" + " .py -i mov_spots.csv -m mov.n5 -t transform.tiff")
    parser = argparse.ArgumentParser(description=usage_text,usage=argparse.SUPPRESS)
    parser.add_argument('-n','--n5dir',dest='n5dir',type=str,help='path to N5, whose spots have been called',required=True,metavar='')
    parser.add_argument('-td','--transformdir',dest='transformdir',type=str,help='path to transformdir',required=True,metavar='')
    parser.add_argument('-sd','--spotsdir',dest='spotsdir',type=str,help='path to spotsdir',required=True,metavar='')    
    parser.add_argument('-o','--outdir',dest='outdir',type=str,help='output directory',required=True,metavar='')

    # optional param, specify resolution if registration or spot calling was performed in more than one resolution #
#    parser.add_argument('--transform_res',dest='transform_res',type=str,help='image resolution at which registeration happened (e.g. s2)',required=False,metavar='',default=None)
#    parser.add_argument('--spots_res',dest='spots_res',type=str,help='image resolution at which rsFISH happened (e.g. s0)',required=False,metavar='',default=None)
#    parser.add_argument('--force',dest='force', default=False, action="store_true", help="overwrite existing registered spots file")


    # parameters for inverting transformation field (optional params) #
    # iteration default 10
    parser.add_argument('--downsample_field_xy',dest='downsample_field_xy', type=str,help='downsampling factor applied to transform field before inverting',required=False,metavar='',default='4')
    parser.add_argument('--iterations',dest='iterations',type=str,help='The number of stationary point iterations to find inverse. More iterations for higher precision',required=False,metavar='',default='10')
    parser.add_argument('--sqrt_order',dest='sqrt_order',type=str,help='The number of roots to take before stationary point iterations',required=False,metavar='',default='2')
    parser.add_argument('--sqrt_iterations',dest='sqrt_iterations',type=str,help='The number of iterations to find the field composition square root',required=False,metavar='',default='5')

    args=parser.parse_args()

    ### print some indication that this script is running ###
    print('-------------bigstream_warpspots_in_memory.py: start-------------')
    print('-------------N5 input: ',args.n5dir, '-------------')

    ### parameters format ###
    iterations = int(args.iterations)
    sqrt_order = int(args.sqrt_order)
    sqrt_iterations = int(args.sqrt_iterations)
    downsample_field_xy=int(args.downsample_field_xy)

    ### make output directory: no subdirectory ###
    check_create_dir(args.outdir)

    ### get batch time of the N5 used to call spots ###
    n5BT = get_batch_time(args.n5dir)

    ### save temporary text file to which python stuff will be output ###
    tmp_file = os.path.join(args.outdir,n5BT[0]+'_'+n5BT[1]+'.tmp')
    if os.path.exists(tmp_file):
        with open(tmp_file,'a') as file:
            file.write("\n\n")
            file.write("### start of bigstream_warpspots ###")
    else:
        with open(tmp_file,'w') as file:
            file.write("### start of bigstream_warpspots ###")

    ### save parameters ###
    with open(tmp_file,'a') as file:
        file.write("\nparameters used in the script:")
        file.write("\n\t--n5dir "+str(args.n5dir))
        file.write("\n\t--transformdir "+str(args.transformdir))
        file.write("\n\t--spotsdir "+str(args.spotsdir))
        file.write("\n\t--outdir "+str(args.outdir))
        file.write("\n\t--downsample_field_xy "+str(downsample_field_xy))
        file.write("\n\t--iterations "+str(iterations))
        file.write("\n\t--sqrt_order "+str(sqrt_order))
        file.write("\n\t--sqrt_iterations "+str(sqrt_iterations))

################################################# the beginning of block dedicated to getting correct transform file prefix and spacing #################################################
    # from n5BT, get transform checkpoint #
    # assume there is a singular transformation per N5
    F = os.listdir(args.transformdir)
    transform_cp = []
    for f in F:
        f_mov = f.split('-')[-1]
        if n5BT[0]+"_"+n5BT[1] in f_mov and '.checkpoint' in f_mov:
            transform_cp.append(f)
    if len(transform_cp) == 0:
        isfiximage=True
        transform_checkpoint="None"
    else:
        isfiximage=False
        transform_checkpoint=transform_cp[0]


    # from trasnform_cp -> get resolution
    if isfiximage==True:
        # for fix, grab the first transform field and use the 'fix' prefix
        transform_btcs = F[0].split('-')[0].split('_')
    else:
        # for mov, use transform_checkpoint
        transform_btcs = transform_checkpoint.split('-')[-1].replace(".checkpoint","").split('_')
    for s in transform_btcs: 
        if (len(s)==2) and s.startswith("s") and any(char.isdigit() for char in s):
            transform_res=s
    
    # from resolution -> get transform_spacing metadata
    n5_zarr = zarr.open(store=zarr.N5FSStore(args.n5dir),mode='r')
    subpath = 'c0/'+transform_res
    n5 = n5_zarr[subpath]
    transform_spacing = np.multiply(n5.attrs.asdict()['pixelResolution'],n5.attrs.asdict()['downsamplingFactors'])[::-1]

    with open(tmp_file,'a') as file:
        file.write("\n"+"transform_checkpoint="+transform_checkpoint)
        file.write("\n"+"transform_spacing="+str(transform_spacing))    
################################################# the end of block dedicated to getting correct transform file prefix and spacing #################################################

################################################# the beginning of block dedicated to getting correct spots file prefix and spacing ###############################################
    # from n5BT, get spots checkpoint #
    F = os.listdir(args.spotsdir)
    spots_cp = []
    for f in F:
        if n5BT[0]+"_"+n5BT[1] in f and '.checkpoint' in f:
            spots_cp.append(f)
    spots_btcs = spots_cp[0].replace(".checkpoint","").split('_')

    # from spots_cp -> get resolution
    for s in spots_btcs: 
        if (len(s)==2) and s.startswith("s") and any(char.isdigit() for char in s):
            spots_res=s
    subpath = 'c0/'+spots_res
    n5 = n5_zarr[subpath]
    spots_spacing = np.multiply(n5.attrs.asdict()['pixelResolution'],n5.attrs.asdict()['downsamplingFactors'])[::-1]
    
    with open(tmp_file,'a') as file:
        file.write("\n"+"spots_checkpoint="+str(spots_cp))
        file.write("\n"+"spots_spacing="+str(spots_spacing))

################################################# the end of block dedicated to getting correct spots file prefix and spacing #################################################

################################################# the beginning of block dedicated to inverting field ###############################################
    F = os.listdir(args.outdir)
    reg_spots_cp = []
    for f in F:
        if n5BT[0]+"_"+n5BT[1] in f and '.checkpoint' in f:
            reg_spots_cp.append(f)
    
    # check if number of spots = number of registered spots
    if len(spots_cp) != len(reg_spots_cp):
        ### fix image ###
        if isfiximage==True:
            with open(tmp_file,'a') as file:
                file.write("\n"+"only do spot rescaling")
            for c in spots_cp:
                if os.path.exists(os.path.join(args.spotsdir,c)):
                    spots_path = os.path.join(args.spotsdir,c.replace(".checkpoint",".csv"))
                    spots = pd.read_csv(spots_path)
                
                ### same block as mov image, fix_spots_zyx = spots_zyx ###
                spots_zyx = spots[['z','y','x']].to_numpy() * spots_spacing
                fix_spots_zyx = spots_zyx # no registration for fix image
                fix_spots_df = pd.DataFrame((fix_spots_zyx / transform_spacing)[:,::-1],columns=['x','y','z']) # zyx -> xyz when saving
                fix_spots = pd.concat([fix_spots_df,spots[['t','c','intensity']]],axis=1) # will bring back other columns of the spots data
                fix_spots_csv = "fix_"+c.replace(str(spots_res),str(transform_res)).replace(".checkpoint",".csv")
                fix_spots.to_csv(os.path.join(args.outdir,fix_spots_csv),index=None)
                fix_spots_checkpoint_path = os.path.join(args.outdir,fix_spots_csv.replace(".csv",".checkpoint"))
                with open(fix_spots_checkpoint_path, 'w') as fp:
                    pass
                if os.path.exists(fix_spots_checkpoint_path):
                    with open(tmp_file,'a') as file:
                        file.write("\n"+"fix_spots: "+fix_spots_checkpoint_path)

                
        ### mov image ###
        else:
            if os.path.exists(os.path.join(args.transformdir,transform_checkpoint)):
                transform_path = os.path.join(args.transformdir,transform_checkpoint.replace(".checkpoint",".tiff"))
                transform = np.moveaxis(tifffile.imread(transform_path),1,-1)
            from bigstream.transform import invert_displacement_vector_field
            start_time = time.time()
            
            zoom_down = np.array([1,1/downsample_field_xy,1/downsample_field_xy,1])
            transform_down = zoom(input=transform,zoom=zoom_down,order=0)
            with open(tmp_file,'a') as file:
                file.write("\n"+"begin field inversion:")
                file.write("\n\t"+"transform_field:"+str(transform.shape))
                file.write("\n\t"+"transform_field_downsampled:"+str(transform_down.shape))
            transform = None # clear memory
            transform_invert = invert_displacement_vector_field(
                    field=transform_down,
                    spacing=transform_spacing,
                    iterations=iterations,
                    sqrt_order=sqrt_order,
                    sqrt_iterations=sqrt_iterations
                    )
            transform_down = None # clear memory
            zoom_up=1/zoom_down
            transform_invert_up = zoom(input=transform_invert,zoom=zoom_up,order=0)
            transform_invert = None # clear memory
            end_time = time.time()
            total_elapsed_time = end_time - start_time
            with open(tmp_file,'a') as file:
                file.write("\n"+"completed transform field inversion and re-upsampling:"+str(transform_invert_up.shape))
                file.write("\n\t"+"inversion time (min):"+str(total_elapsed_time//60))

            ### read the spots csv: this has 6 channels: x,y,z,t,c,intensity ###
            ## loop through the spots ##
            for c in spots_cp:
                if os.path.exists(os.path.join(args.spotsdir,c)):
                    spots_path = os.path.join(args.spotsdir,c.replace(".checkpoint",".csv"))
                    spots = pd.read_csv(spots_path)
                spots_zyx = spots[['z','y','x']].to_numpy() * spots_spacing    # only need z,y,x; convert to physical units

                ### transform spots, output is in physical spacing ###
                from bigstream.transform import apply_transform_to_coordinates
                start_time = time.time()
                reg_spots_zyx = apply_transform_to_coordinates(
                        coordinates=spots_zyx,
                        transform_list=[transform_invert_up],
                        transform_spacing=transform_spacing
                        )
                end_time = time.time()
                total_elapsed_time = end_time - start_time
                ## spots_zyx_reg is in physical spacing, convert back to voxel units of the transform field ##
                ## This should allow registered image and the registered spots to be correctly superimposed ##
                # spots_zyx_reg (um) / spacing_transform (um / voxel-s2) = spots_zyx_reg (voxel-s2 units) 
                reg_spots_df = pd.DataFrame((reg_spots_zyx / transform_spacing)[:,::-1],columns=['x','y','z']) # zyx -> xyz when saving
                reg_spots = pd.concat([reg_spots_df,spots[['t','c','intensity']]],axis=1) # will bring back other columns of the spots data
                reg_spots_csv = "reg_"+c.replace(str(spots_res),str(transform_res)).replace(".checkpoint",".csv")
                reg_spots.to_csv(os.path.join(args.outdir,reg_spots_csv),index=None)
                reg_spots_checkpoint_path = os.path.join(args.outdir,reg_spots_csv.replace(".csv",".checkpoint"))
                with open(reg_spots_checkpoint_path, 'w') as fp:
                    pass
                if os.path.exists(reg_spots_checkpoint_path):
                    with open(tmp_file,'a') as file:
                        file.write("\n"+"reg_spots: "+reg_spots_checkpoint_path)
                        file.write("\n\t"+"registration time (min):"+str(total_elapsed_time//60))
    else:
        print("no registration performed, checkpoint file already exists")
        with open(tmp_file,'a') as file:
            file.write("\n"+"registered_spots already exists, no warping performed:")
            file.write("\n"+str(reg_spots_cp))
        
    with open(tmp_file,'a') as file:
        file.write("\n"+"### end of bigstream_warpspots ###")



if __name__ == '__main__':
    main()
