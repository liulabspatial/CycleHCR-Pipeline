import numpy as np
import zarr
import tifffile
from scipy.ndimage import zoom

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
    usage_text = ("Usage:" + " .py -f fix_zarr -m mov_zarr ...")
    parser = argparse.ArgumentParser(description=usage_text,usage=argparse.SUPPRESS)
    parser.add_argument('-f','--fixdir',dest='fixdir',type=str,help='path to fix zarr',required=True,metavar='')
    parser.add_argument('-m','--movdir',dest='movdir',type=str,help='path to mov zarr',required=True,metavar='')
    parser.add_argument('-s','--res',dest='res',type=str,help='image resolution to register (e.g. 2)',required=True,metavar='')
    parser.add_argument('-d','--dapi',dest='dapi',type=str,help='dapi channel (e.g. 3)',required=True,metavar='')
    parser.add_argument('-o','--outdir',dest='outdir',type=str,help='output directory',required=True,metavar='')

    # optional parameters #
    parser.add_argument('--fix_mask',dest='fix_mask',type=str,help='path to fix mask tif',required=False,metavar='')
    parser.add_argument('--mov_mask',dest='mov_mask',type=str,help='path to mov mask tif',required=False,metavar='')
    parser.add_argument('--force',dest='force', default=False, action="store_true", help="overwrite existing results")

    # affine registration (optional params) #
    parser.add_argument('--aff_as',dest='aff_as',type=str,help='affine_alignment_spacing: subsampling factor to be applied to the image that has been projected onto physical space',required=False,metavar='',default='2')
    parser.add_argument('--aff_sf',dest='aff_sf',type=str,help='affine_shrink_factors: downsampling factor to apply after alignment_spacing, multiple values can be provided for sequential alignments',required=False,metavar='',default='2,1')
    parser.add_argument('--aff_ss',dest='aff_ss',type=str,help='affine_smooth_sigmas: gaussian smoothing to apply to each downsampled image, must be the same length as the aff_shrink_factors',required=False,metavar='',default='2,0')
    parser.add_argument('--aff_n',dest='aff_n',type=str,help='affine_iterN: number of iterations ',required=False,metavar='',default=1000)

    # deform registration (optional params) #
    parser.add_argument('--deform',dest='deform',type=str,help='whether or not to perform deform',required=False,metavar='',default='0')
    parser.add_argument('--def_as',dest='def_as',type=str,help='deform_alignment_spacing: subsampling factor to be applied to the image that has been projected onto physical space',required=False,metavar='',default='2')
    parser.add_argument('--def_sf',dest='def_sf',type=str,help='deform_shrink_factors: downsampling factor to apply after alignment_spacing, multiple values can be provided for sequential alignments',required=False,metavar='',default='2')
    parser.add_argument('--def_ss',dest='def_ss',type=str,help='deform_smooth_sigmas: gaussian smoothing to apply to each downsampled image, must be the same length as the def_shrink_factors',required=False,metavar='',default='0.25')
    parser.add_argument('--def_n',dest='def_n',type=str,help='deform_iterN: number of iterations',required=False,metavar='',default=200)
    parser.add_argument('--def_cps',dest='def_cps',type=str,help='deform_control_point_spacing: physical spacing between control points for deformation optimization',required=False,metavar='',default='128')


    args=parser.parse_args()
    print(args)
    ## resolution format ##
    res = str(int(re.search(r'\d+', str(args.res)).group()))
    dapi = str(int(re.search(r'\d+', str(args.dapi)).group()))

    ### parameters format for affine registration ###
    aff_as = float(args.aff_as) # alignemnt_spacing is float
    aff_sf = args.aff_sf.split("," ) 
    aff_sf = tuple([int(i) for i in aff_sf]) # shrink_factor is a tuple of integers
    aff_ss = args.aff_ss.split("," ) 
    aff_ss = tuple([float(i) for i in aff_ss]) # smooth_sigma is a tuple of floats
    aff_n = int(args.aff_n) # number of iteration is int

    ### parameters format for deform registration ###
    deform = int(args.deform)
    def_as = float(args.def_as) # alignemnt_spacing is float
    def_sf = args.def_sf.split("," ) 
    def_sf = tuple([int(i) for i in def_sf]) # shrink_factor is a tuple of integers
    def_ss = args.def_ss.split("," ) 
    def_ss = tuple([float(i) for i in def_ss]) # smooth_sigma is a tuple of floats
    def_n = int(args.def_n) # number of iteration is int
    def_cps = float(args.def_cps)

    ### parameter setting for bigstream ###
    # affine #
    affine_kwargs = {
        'alignment_spacing':aff_as, # subsampling factor 
        'shrink_factors':aff_sf, # proper downsampling factor, can be done in sequential multi resolution
        'smooth_sigmas':aff_ss, # gaussian smoothing each level
        'optimizer_args':{
            'learningRate':0.25,
            'minStep':0.,
            'numberOfIterations':aff_n, # this is the maximum iterations. The function will end before if the alignment is easy and converges quick,
        },
    }

    # deform #
    deform_kwargs = {
        'alignment_spacing':def_as,
        'shrink_factors':def_sf,
        'smooth_sigmas':def_ss,
        'control_point_spacing':def_cps,
        'control_point_levels':(1,),
        'optimizer_args':{
            'learningRate':0.25,
            'minStep':0.,
            'numberOfIterations':def_n,
        },
    }

    ### make output directories: transform and registered ###
    outdir_transform = os.path.join(args.outdir,'transform')  # subdirectory 'transform'
    outdir_registered = os.path.join(args.outdir,'registered') # subdirectory 'registered'
    check_create_dir(outdir_transform)
    check_create_dir(outdir_registered)

    ### name of the transform matrix file to be saved as ###
    fixPT = get_point_time(args.fixdir)
    movPT = get_point_time(args.movdir)
    transform_prefix = f"{fixPT[0]}_{fixPT[1]}_c{dapi}_s{res}-{movPT[0]}_{movPT[1]}_c{dapi}_s{res}"

    ### list of channels present in mov data ###
    channels = get_channels(args.movdir) # get other channels of mov directory

    ### checkpoint test for alignment: does transformation matrix exist? ###
    transform_checkpoint_path = os.path.join(outdir_transform,transform_prefix+".checkpoint")
    if os.path.exists(transform_checkpoint_path) and not args.force:
        print("skipping alignmentment, transform file already exists: ", transform_checkpoint_path)
        ### if the transform exists, then do checkpoint test for transformation: does registered data exist? ###
        # save missing channels, ones that do not have checkpoint file #
        channels_missing=[]
        for c in channels:
            reg_prefix = f"reg_{movPT[0]}_{movPT[1]}_c{c}_s{res}"
            reg_checkpoint_path = os.path.join(outdir_registered,reg_prefix+".checkpoint") # = outdir/registered/reg_prefix.checkpoint
            if os.path.exists(reg_checkpoint_path):
                print("skipping transformation, registered file already exists: ",reg_checkpoint_path)
            else:
                channels_missing.append(c)
        ### if there is no missing channel, then end of function ###
        if not channels_missing:
            return
        
        ### if there are missing channels, perform registration using the existing transform data ###
        else:
            from bigstream.transform import apply_transform

            ### read fix data ###
            try:
                fix_zarr = zarr.open(store=args.fixdir, mode='r')
                fix = fix_zarr['c'+dapi][res][0,0,:,:,:].astype(np.uint16)
                metadata = fix_zarr['c'+dapi].attrs
                fix_spacing = np.multiply(metadata['Bigstitcher-Spark']['Spacings'][::-1], metadata['multiscales'][0]['datasets'][int(res)]['coordinateTransformations'][0]['scale'][2:5])

            except Exception as e:
                print(f"error reading omezarr")

            ### read transform matrix ###
            transform_npy = os.path.join(outdir_transform,transform_prefix+".npy")
            transform = np.load(transform_npy)

            ### transform in a loop over channels_missing ###
            for c in channels_missing:
                try:
                    mov_zarr = zarr.open(store=args.movdir, mode='r')
                    mov = mov_zarr['c'+c][res][0,0,:,:,:].astype(np.uint16)
                    print(mov.shape)
                    metadata = mov_zarr['c'+c].attrs
                    mov_spacing = np.multiply(metadata['Bigstitcher-Spark']['Spacings'][::-1], metadata['multiscales'][0]['datasets'][int(res)]['coordinateTransformations'][0]['scale'][2:5])
                except Exception as e:
                    print(f"error reading zarr data")  

                reg = apply_transform(
                    fix=fix,  # fix does not need to change, can stay as dapi
                    mov=mov, 
                    fix_spacing=fix_spacing,
                    mov_spacing=mov_spacing,
                    transform_list=[transform,], # together
                )
                # naming prefix for saving registered image
                reg_prefix = f"reg_{movPT[0]}_{movPT[1]}_c{c}_s{res}"
                reg_tiff = os.path.join(outdir_registered,reg_prefix+'.tiff') # = outdir/registered/reg_prefix.tiff
                tifffile.imwrite(reg_tiff, reg , imagej=True, metadata={'axes':'ZYX'})
                reg_checkpoint_path = os.path.join(outdir_registered,reg_prefix+".checkpoint") # =outdir/registered/reg_prefix.checkpoint
                print('registration complete, creating checkpoint file: ', reg_checkpoint_path)
                with open(reg_checkpoint_path, 'w') as fp:
                    pass        

    ### if transformation matrix does not exist, then perform transform followed by registration ###
    else:
        ### read zarr dapi data ###
        try:
            fix_zarr = zarr.open(store=args.fixdir, mode='r')
            fix = fix_zarr['c'+dapi][res][0,0,:,:,:].astype(np.uint16)

            mov_zarr = zarr.open(store=args.movdir, mode='r')
            mov = mov_zarr['c'+dapi][res][0,0,:,:,:].astype(np.uint16)

        except Exception as e:
            print(f"error reading zarr")

        ### read metadata from N5 ###
        # spacing = pixel res of full s0 multiply by downsampling factor
        metadata = fix_zarr['c'+dapi].attrs
        fix_spacing = np.multiply(metadata['Bigstitcher-Spark']['Spacings'][::-1], metadata['multiscales'][0]['datasets'][int(res)]['coordinateTransformations'][0]['scale'][2:5])
        metadata = mov_zarr['c'+dapi].attrs
        mov_spacing = np.multiply(metadata['Bigstitcher-Spark']['Spacings'][::-1], metadata['multiscales'][0]['datasets'][int(res)]['coordinateTransformations'][0]['scale'][2:5])        

        ### parameters format for masks ###
        ## infer relative spacing for mask, and match the shape to the N5 ##
        if args.fix_mask == None:
            fix_mask=(0,)
            print("no fix mask, applying mask > 0")
        else:
            fix_mask0 = tifffile.imread(args.fix_mask)
            fix_mask_relative_spacing = (np.array(fix.shape) / np.array(fix_mask0.shape))
            fix_mask = zoom(fix_mask0,zoom=fix_mask_relative_spacing,order=0,mode='constant')
            print('fix_shape', fix.shape)
            print('fix_spacing', fix_spacing)
            print('fix_mask_shape: ',fix_mask0.shape)
            print('fix_mask_relative_spacing: ',fix_mask_relative_spacing)
            print('fix_mask_shape(zoomed): ',fix_mask.shape)

        if args.mov_mask == None:
            mov_mask=(0,)
            print("no mov mask, applying mask > 0")
        else:
            mov_mask0 = tifffile.imread(args.mov_mask)
            mov_mask_relative_spacing = (np.array(mov.shape) / np.array(mov_mask0.shape))
            mov_mask= zoom(mov_mask0,zoom=mov_mask_relative_spacing,order=0,mode='constant')
            print('mov_shape', mov.shape)
            print('mov_spacing', mov_spacing)
            print('mov_mask_shape: ',mov_mask0.shape)
            print('mov_mask_relative_spacing: ',mov_mask_relative_spacing)
            print('mov_mask_shape(zoomed): ',mov_mask.shape)

        ## specify steps: affine or affine+deform ##
        if deform == 0:
            print('only affine')
            steps = [('affine',affine_kwargs)]
        elif deform == 1:
            print('do affine and deform')
            steps = [('affine',affine_kwargs),('deform',deform_kwargs)]
        else:
            print('deform parameter must be 0 or 1')
            return

        ### calculate the transformation matrix ###

        from bigstream.align import alignment_pipeline
        transform = alignment_pipeline(
            fix=fix, 
            mov=mov,
            fix_spacing=fix_spacing,
            mov_spacing=mov_spacing,
            fix_mask=fix_mask,
            mov_mask=mov_mask,
            steps=steps, # perform together, affine and then deform in steps
        )
        # save transform, we need to use for warping spots #
        transform_npy = os.path.join(outdir_transform,transform_prefix+".npy")
        np.save(transform_npy, transform)

        print('alignment complete, creating checkpoint file: ', transform_checkpoint_path)
        with open(transform_checkpoint_path, 'w') as fp:
            pass


        ### transform in a loop over channels ###
        from bigstream.transform import apply_transform
        # fix doesn't change, mov loop through channels

        for c in channels:            
            try:
                mov_zarr = zarr.open(store=args.movdir, mode='r')
                mov = mov_zarr['c'+c][res][0,0,:,:,:].astype(np.uint16)
            except Exception as e:
                print(f"error reading zarr data")                

            reg = apply_transform(
                fix=fix,  # fix does not need to change, can stay as dapi
                mov=mov, 
                fix_spacing=fix_spacing,
                mov_spacing=mov_spacing,
                transform_list=[transform,], # together
            )
            # naming prefix for saving registered image
            reg_prefix = f"reg_{movPT[0]}_{movPT[1]}_c{c}_s{res}"
            reg_tiff = os.path.join(outdir_registered,reg_prefix+'.tiff') # = outdir/registered/reg_prefix.tiff
            tifffile.imwrite(reg_tiff, reg , imagej=True, metadata={'axes':'ZYX'})
            
            reg_checkpoint_path = os.path.join(outdir_registered,reg_prefix+".checkpoint") # =outdir/registered/reg_prefix.checkpoint
            print('registration complete, creating checkpoint file: ', reg_checkpoint_path)
            with open(reg_checkpoint_path, 'w') as fp:
                pass


if __name__ == '__main__':
    main()
