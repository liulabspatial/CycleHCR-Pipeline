import numpy as np
import zarr
import tifffile
from scipy.ndimage import zoom

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
    usage_text = ("Usage:" + " .py -f fix.n5 -m mov.n5 ...")
    parser = argparse.ArgumentParser(description=usage_text,usage=argparse.SUPPRESS)
    parser.add_argument('-f','--fixdir',dest='fixdir',type=str,help='path to fix N5',required=True,metavar='')
    parser.add_argument('-m','--movdir',dest='movdir',type=str,help='path to mov N5',required=True,metavar='')
    parser.add_argument('-s','--res',dest='res',type=str,help='image resolution to register (e.g. s2)',required=True,metavar='')
    parser.add_argument('-d','--dapi',dest='dapi',type=str,help='dapi channel (e.g. c3)',required=True,metavar='')
    parser.add_argument('-o','--outdir',dest='outdir',type=str,help='output directory',required=True,metavar='')


    # optional parameters #
    parser.add_argument('--fix_mask',dest='fix_mask',type=str,help='path to fix mask tiff',required=False,metavar='')
    parser.add_argument('--mov_mask',dest='mov_mask',type=str,help='path to mov mask tiff',required=False,metavar='')
    parser.add_argument('--force',dest='force', default=False, action="store_true", help="overwrite existing results")

    # affine registration (optional params) #
    parser.add_argument('--aff_as',dest='aff_as',type=str,help='affine_alignment_spacing: subsampling factor to be applied to the image that has been projected onto physical space',required=False,metavar='',default='2')
    parser.add_argument('--aff_sf',dest='aff_sf',type=str,help='affine_shrink_factors: downsampling factor to apply after alignment_spacing, multiple values can be provided for sequential alignments',required=False,metavar='',default='2,1')
    parser.add_argument('--aff_ss',dest='aff_ss',type=str,help='affine_smooth_sigmas: gaussian smoothing to apply to each downsampled image, must be the same length as the aff_shrink_factors',required=False,metavar='',default='2,0')
    parser.add_argument('--aff_n',dest='aff_n',type=str,help='affine_iterN: number of iterations ',required=False,metavar='',default=1000)

    # deform registration (optional params) #
    parser.add_argument('--def_as',dest='def_as',type=str,help='deform_alignment_spacing: subsampling factor to be applied to the image that has been projected onto physical space',required=False,metavar='',default='2')
    parser.add_argument('--def_sf',dest='def_sf',type=str,help='deform_shrink_factors: downsampling factor to apply after alignment_spacing, multiple values can be provided for sequential alignments',required=False,metavar='',default='2')
    parser.add_argument('--def_ss',dest='def_ss',type=str,help='deform_smooth_sigmas: gaussian smoothing to apply to each downsampled image, must be the same length as the def_shrink_factors',required=False,metavar='',default='0.25')
    parser.add_argument('--def_n',dest='def_n',type=str,help='deform_iterN: number of iterations',required=False,metavar='',default=200)
    parser.add_argument('--def_cps',dest='def_cps',type=str,help='deform_control_point_spacing: physical spacing between control points for deformation optimization',required=False,metavar='',default='128')


    args=parser.parse_args()

    ### parameters format for affine registration ###
    aff_as = float(args.aff_as) # alignemnt_spacing is float
    aff_sf = args.aff_sf.split("," ) 
    aff_sf = tuple([int(i) for i in aff_sf]) # shrink_factor is a tuple of integers
    aff_ss = args.aff_ss.split("," ) 
    aff_ss = tuple([float(i) for i in aff_ss]) # smooth_sigma is a tuple of floats
    aff_n = int(args.aff_n) # number of iteration is int

    ### parameters format for deform registration ###
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
    fixBT = get_batch_time(args.fixdir)
    movBT = get_batch_time(args.movdir)
    transform_prefix = fixBT[0]+'_'+fixBT[1]+'_'+args.dapi+'_'+args.res+'-'+movBT[0]+'_'+movBT[1]+'_'+args.dapi+'_'+args.res  
    affine_deform_tiff = os.path.join(outdir_transform,transform_prefix+".tiff")

    ### list of channels present in mov data ###
    channels = get_channels(args.movdir) # get other channels of mov directory


    ### checkpoint test for alignment: does transformation matrix exist? ###
    transform_checkpoint_path = os.path.join(outdir_transform,transform_prefix+".checkpoint");
    if os.path.exists(transform_checkpoint_path) and not args.force:
        print("skipping alignmentment, transform file already exists: ", transform_checkpoint_path)
        ### if the matrix exists, then do checkpoint test for transformation: does registered data exist? ###
        # save missing channels, ones that do not have checkpoint file #
        channels_missing=[]
        for c in channels:
            reg_prefix = 'reg_'+movBT[0]+'_'+movBT[1]+'_'+c+'_'+args.res
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
            subpath = args.dapi+'/' + args.res
            fix_zarr = zarr.open(store=zarr.N5FSStore(args.fixdir),mode='r')
            fix = fix_zarr[subpath]
            fix_spacing = np.multiply(fix.attrs.asdict()['pixelResolution'],fix.attrs.asdict()['downsamplingFactors'])[::-1] # flip order, spacing needs to be in zyx

            ### read transform matrix ###
            affine_deform = np.moveaxis(tifffile.imread(affine_deform_tiff),1,-1) # move vector axis (from C axis - 1), to the last axis, because tiff format

            ### transform in a loop over channels_missing ###
            for c in channels_missing:
                subpath = c+'/' + args.res # get the channel
                mov_zarr = zarr.open(store=zarr.N5FSStore(args.movdir),mode='r')
                mov = mov_zarr[subpath]
                mov_spacing = np.multiply(mov.attrs.asdict()['pixelResolution'],mov.attrs.asdict()['downsamplingFactors'])[::-1] # flip order, spacing needs to be in zyx
                reg = apply_transform(
                    fix=fix,  # fix does not need to change, can stay as dapi
                    mov=mov, 
                    fix_spacing=fix_spacing,
                    mov_spacing=mov_spacing,
                    transform_list=[affine_deform,], # together
                )
                # naming prefix for saving registered image
                reg_prefix = 'reg_'+movBT[0]+'_'+movBT[1]+'_'+c+'_'+args.res
                reg_tiff = os.path.join(outdir_registered,reg_prefix+'.tiff') # = outdir/registered/reg_prefix.tiff
                tifffile.imwrite(reg_tiff, reg , imagej=True, metadata={'axes':'ZYX'})
                reg_checkpoint_path = os.path.join(outdir_registered,reg_prefix+".checkpoint") # =outdir/registered/reg_prefix.checkpoint
                print('registration complete, creating checkpoint file: ', reg_checkpoint_path)
                with open(reg_checkpoint_path, 'w') as fp:
                    pass
    ### if transformation matrix does not exist, then perform transform followed by registration ###
    else:
        ### read N5 dapi data ###
        subpath = args.dapi+'/' + args.res
        fix_zarr = zarr.open(store=zarr.N5FSStore(args.fixdir),mode='r')
        fix = fix_zarr[subpath]

        mov_zarr = zarr.open(store=zarr.N5FSStore(args.movdir),mode='r')
        mov = mov_zarr[subpath]

        ### read metadata from N5 ###
        # spacing = pixel res of full s0 multiply by downsampling factor
        fix_spacing = np.multiply(fix.attrs.asdict()['pixelResolution'],fix.attrs.asdict()['downsamplingFactors'])[::-1] # flip order, spacing needs to be in zyx
        mov_spacing = np.multiply(mov.attrs.asdict()['pixelResolution'],mov.attrs.asdict()['downsamplingFactors'])[::-1] # flip order, spacing needs to be in zyx
        print('fix_shape: ',fix.shape,' ; fix_spacing: ',fix_spacing)
        print('mov_shape: ',mov.shape,' ; mov_spacing: ',mov_spacing)

        ### parameters format for masks ###
        ## infer relative spacing for mask, and match the shape to the N5 ##
        if args.fix_mask == None:
            fix_mask=(0,)
            print("no fix mask, applying mask > 0")
        else:
            fix_mask0 = tifffile.imread(args.fix_mask)
            fix_mask_relative_spacing = (np.array(fix.shape) / np.array(fix_mask0.shape))
            fix_mask = zoom(fix_mask0,zoom=fix_mask_relative_spacing,order=0,mode='constant')
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
            print('mov_mask_shape: ',mov_mask0.shape)
            print('mov_mask_relative_spacing: ',mov_mask_relative_spacing)
            print('mov_mask_shape(zoomed): ',mov_mask.shape)

        ### calculate the transformation matrix ###
        from bigstream.align import alignment_pipeline
        affine_deform = alignment_pipeline(
            fix=fix, 
            mov=mov,
            fix_spacing=fix_spacing,
            mov_spacing=mov_spacing,
            fix_mask=fix_mask,
            mov_mask=mov_mask,
            steps=[('affine',affine_kwargs),('deform',deform_kwargs)], # perform together, affine and then deform in steps
        )
        # save as tiff, we need to use for warping spots #
        affine_deform_tiff = os.path.join(outdir_transform,transform_prefix+".tiff")
        tifffile.imwrite(affine_deform_tiff, np.moveaxis(affine_deform,-1,1) , imagej=True, metadata={'axes':'ZCYX'})  # move last vector axis into C axis, because tiff format
        print('alignment complete, creating checkpoint file: ', transform_checkpoint_path)
        with open(transform_checkpoint_path, 'w') as fp:
            pass

        ### transform in a loop over channels ###
        from bigstream.transform import apply_transform
        # fix doesn't change, mov loop through channels
        for c in channels:
            subpath = c+'/' + args.res # get the channel
            mov_zarr = zarr.open(store=zarr.N5FSStore(args.movdir),mode='r')
            mov = mov_zarr[subpath]
            reg = apply_transform(
                fix=fix,  # fix does not need to change, can stay as dapi
                mov=mov, 
                fix_spacing=fix_spacing,
                mov_spacing=mov_spacing,
                transform_list=[affine_deform,], # together
            )
            # naming prefix for saving registered image
            reg_prefix = 'reg_'+movBT[0]+'_'+movBT[1]+'_'+c+'_'+args.res
            reg_tiff = os.path.join(outdir_registered,reg_prefix+'.tiff') # = outdir/registered/reg_prefix.tiff
            tifffile.imwrite(reg_tiff, reg , imagej=True, metadata={'axes':'ZYX'})
            reg_checkpoint_path = os.path.join(outdir_registered,reg_prefix+".checkpoint") # =outdir/registered/reg_prefix.checkpoint
            print('registration complete, creating checkpoint file: ', reg_checkpoint_path)
            with open(reg_checkpoint_path, 'w') as fp:
                pass


if __name__ == '__main__':
    main()
