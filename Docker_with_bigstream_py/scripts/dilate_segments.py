import pandas as pd
import numpy as np
import math
import dask.array as da
import dask
from dask.distributed import LocalCluster, Client
import tifffile

import sys
import argparse

def custom_filter_max(block):
    """
    Apply a custom filter to a 3D block.
    
    Parameters:
    - block: 3D numpy array, a small block of the image with padding.
    
    Returns:
    - filtered_block: 3D numpy array, the filtered block.
    """
    # Initialize the output block with zeros
    filtered_block = np.zeros(block.shape, dtype=block.dtype)
    
    # Iterate through each voxel in the block (excluding the border voxels due to padding)
    for z in range(1, block.shape[0] - 1):
        for y in range(1, block.shape[1] - 1):
            for x in range(1, block.shape[2] - 1):
                val = block[z, y, x]
                if val == 0:
                    neighbors = [block[z-1, y, x], block[z+1, y, x], block[z, y-1, x], block[z, y+1, x], block[z, y, x-1], block[z, y, x+1]]
                    array_1d = np.array(neighbors)
                    max_val = array_1d.max()
                    filtered_block[z, y, x] = max_val
                else:
                    filtered_block[z, y, x] = val
    
    # Return the filtered block, excluding the padding
    return filtered_block

def custom_filter_min(block):
    """
    Apply a custom filter to a 3D block.
    
    Parameters:
    - block: 3D numpy array, a small block of the image with padding.
    
    Returns:
    - filtered_block: 3D numpy array, the filtered block.
    """
    # Initialize the output block with zeros
    filtered_block = np.zeros(block.shape, dtype=block.dtype)
    
    # Iterate through each voxel in the block (excluding the border voxels due to padding)
    for z in range(1, block.shape[0] - 1):
        for y in range(1, block.shape[1] - 1):
            for x in range(1, block.shape[2] - 1):
                val = block[z, y, x]
                if val != 0:
                    neighbors = [block[z-1, y, x], block[z+1, y, x], block[z, y-1, x], block[z, y+1, x], block[z, y, x-1], block[z, y, x+1]]
                    array_1d = np.array(neighbors)
                    min_val = array_1d.min()
                    filtered_block[z, y, x] = min_val
                else:
                    filtered_block[z, y, x] = val
    
    # Return the filtered block, excluding the padding
    return filtered_block

def apply_custom_filter_dask(image, chunk_size=(100, 100, 100), iteration=1):
    """
    Apply a custom 3x3x3 filter to a 3D image using Dask.
    
    Parameters:
    - image: 3D numpy array, the input image.
    - chunk_size: tuple, the size of the chunks for the Dask array.
    - iteration: iteration number of filtering.
    
    Returns:
    - filtered_image: 3D numpy array, the filtered image.
    """
    # Convert the input image to a Dask array with specified chunks
    image_da = da.from_array(image, chunks=chunk_size)

    print(image_da.shape)

    dilate = True;
    filter = custom_filter_max
    if iteration < 0:
        dilate = False
        iteration = abs(iteration)
        filter = custom_filter_min
    
    for i in range(iteration):
        print("iteration " + str(i))
        # Apply the custom filter using map_overlap
        tmp_da = image_da.map_overlap(filter,
                                      depth=1,
                                      boundary='nearest')
        filtered_image = tmp_da.compute()
        print(filtered_image.shape)
        image_da = da.from_array(filtered_image, chunks=chunk_size)
    
    return filtered_image

def dilate_segments():
    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  dilate_segments.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input spot csv files")
    parser.add_argument("-o", "--output", dest="output", type=str, default=None, help="output file path")
    parser.add_argument("-t", "--thread", dest="thread", type=int, default=8, help="number of threads")
    parser.add_argument("-r", "--radius", dest="radius", type=int, default=10, help="radius of dilation (r > 0) or elosion (r < 0)")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    client = Client(n_workers=args.thread, threads_per_worker=1)
    input_file_path = args.input
    output_file_path = args.output
    iteration = args.radius
    
    # Load the TIFF file as a NumPy array
    with tifffile.TiffFile(input_file_path) as tif:
        image = tif.asarray()

    filtered_image = apply_custom_filter_dask(image, chunk_size=(100, 100, 100), iteration=iteration)

    tifffile.imsave(output_file_path, filtered_image, compression=("ZLIB", 6))    

def main():
    dilate_segments()


if __name__ == '__main__':
    main()