import numpy as np
import tifffile

import os
import sys
import re
import argparse

import z5py
import dask
import dask.array as da
from distributed import LocalCluster, Client, Variable

from pathlib import Path

import json

import shutil

import time

from scipy.ndimage import binary_fill_holes
from skimage.filters import threshold_triangle, gaussian
from skimage import io, transform, measure, morphology
from scipy.ndimage import maximum_filter, minimum_filter, generate_binary_structure

def padding_mask(data_chunk, median, amp):
    mm = median

    # Calculate vv
    vv = int(mm // amp)  # Use integer division

    # Generate masks for low intensity pixels
    masks = (data_chunk < mm - vv)

    data_chunk = np.iinfo(np.uint8).max * (~masks).astype(np.uint8)

    return data_chunk

def generate_mask(data_chunk, th):
    # Generate masks for low intensity pixels
    masks = (data_chunk < th)

    data_chunk = np.iinfo(np.uint8).max * (~masks).astype(np.uint8)

    return data_chunk


def compute_histogram(chunk, bins, range):
    hist, edges = np.histogram(chunk, bins=bins, range=range)
    return hist

def find_median_from_histogram(histogram, range):
    # Create an array representing the value of each bin
    bin_edges = np.linspace(range[0], range[1], len(histogram) + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    
    # Calculate the cumulative sum of the histogram
    cumulative_sum = np.cumsum(histogram)
    total_count = cumulative_sum[-1]
    
    # Find the index where the cumulative sum reaches or exceeds half the total count
    median_index = np.searchsorted(cumulative_sum, total_count / 2)
    
    # Return the bin center corresponding to the median index
    median_value = bin_centers[median_index]
    return int(median_value)

def validate_chunk(dataset, idx):
    try:
        # Attempt to read the chunk
        chunk = dataset.read_chunk(idx)
        if chunk is None:
            print(f"Chunk {idx} is missing.")
            return False
                
        # Check for NaNs or infinite values
        if np.isnan(chunk).any() or np.isinf(chunk).any():
            print(f"Chunk {idx} contains NaNs or infinite values.")
            return False
                
    except Exception as e:
        print(f"Error reading chunk {idx}: {e}")
        return False
    return True


def triangle_threshold(data):
    """
    Calculate the threshold value using the triangle method.

    Parameters:
    data (numpy array): Histogram data of the image.

    Returns:
    int: Calculated threshold value.
    """
    # Find the first and last non-zero bins in the histogram
    min_val = np.nonzero(data)[0][0]
    min2 = np.nonzero(data)[0][-1]
    max_index = np.argmax(data)
    dmax = data[max_index]

    # Determine if we need to invert the histogram
    inverted = False
    if (max_index - min_val) < (min2 - max_index):
        # Invert histogram by flipping it
        data = data[::-1]
        min_val, max_index = len(data) - min2 - 1, len(data) - max_index - 1
        inverted = True

    # Edge case: if min_val equals max_index, return min_val
    if min_val == max_index:
        return min_val

    # Calculate normalized line parameters for the triangle
    nx = dmax  # max value at the peak
    ny = min_val - max_index
    norm = np.sqrt(nx**2 + ny**2)
    nx /= norm
    ny /= norm
    d = nx * min_val + ny * data[min_val]

    # Compute distances from each histogram point to the line and find max distance
    x_indices = np.arange(min_val, max_index + 1)
    distances = nx * x_indices + ny * data[min_val:max_index + 1] - d
    split = x_indices[np.argmax(distances)] - 1

    # Adjust if inverted
    if inverted:
        return len(data) - split - 1
    else:
        return split


def main():

    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  padding.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input file path (.n5)")
    parser.add_argument("-o", "--output", dest="output", type=str, default=None, help="output file path (.tif)")
    parser.add_argument("-t", "--thread", dest="thread", type=int, default=0, help="number of threads")
    parser.add_argument("-c", "--ch", dest="ch", type=str, default=0, help="channel")
    parser.add_argument("-s", "--scale", dest="scale", type=str, default=0, help="scale")
    parser.add_argument("--verbose", dest="verbose", default=False, action="store_true", help="enable verbose logging")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    input = args.input
    output = args.output
    ch = args.ch
    scale = args.scale
    threadnum = args.thread

    dataname = os.path.basename(input)
    indirpath = os.path.dirname(input)
    stem = os.path.splitext(dataname)[0]

    base_path = os.path.join(indirpath, stem)

    with open(os.path.join(input, "attributes.json"), 'w') as f:
        data = {}
        data['n5'] = "2.2.0"
        f.seek(0)
        json.dump(data, f, indent=4)
        f.truncate()

    group_path = "c" + ch + "/s" + scale
    #group_path = "setup" + ch + "/timepoint0/s" + scale

    n5input = z5py.File(input, use_zarr_format=False)

    bins = 65534
    intensity_range = (1, 65535)

    cluster = LocalCluster(n_workers=threadnum, threads_per_worker=1)
    client = Client(cluster)

    dask_array = da.from_array(n5input[group_path], chunks=n5input[group_path].chunks)
    futures = [dask.delayed(compute_histogram)(chunk=chunk, bins=bins, range=intensity_range) for chunk in dask_array.to_delayed().ravel()]
    histograms = np.array(dask.compute(futures)[0])
    overall_histogram = np.sum(histograms, axis=0)
    threshold_val = triangle_threshold(overall_histogram)
    mask_array = dask_array.map_blocks(generate_mask, th=threshold_val, dtype=dask_array.dtype).compute()

    xy_scale = min(350 / mask_array.shape[1], 350 / mask_array.shape[2])
    if xy_scale > 1.0:
        xy_scale = 1.0
    z_scale = 350 / mask_array.shape[0]
    if z_scale > 1.0:
        z_scale = 1.0
    
    scale_factors = (z_scale, xy_scale, xy_scale)
    new_shape = tuple(int(dim * scale) for dim, scale in zip(mask_array.shape, scale_factors))
    scaled_image = transform.resize(mask_array, new_shape, mode='edge', anti_aliasing=True)

    radius = 30
    # Create a spherical structuring element
    structuring_element = generate_binary_structure(3, 1)  # 3D connectivity
    structuring_element = maximum_filter(structuring_element, size=radius)

    dilated_image = maximum_filter(scaled_image, footprint=structuring_element)
    closed_image = minimum_filter(dilated_image, footprint=structuring_element)
    binary_image = np.where(closed_image > 0, 1, 0).astype(np.uint8)

    fix_mask_fill = np.zeros_like(binary_image)
    for z in range(binary_image.shape[0]):
        fix_mask_fill[z,:,:] = binary_fill_holes(binary_image[z,:,:])
    
    fix_mask_fill2 = binary_fill_holes(fix_mask_fill)

    binary_image2 = np.where(fix_mask_fill2 > 0, 255, 0).astype(np.uint8)

    # Apply Gaussian blur
    sigma = 3  # Adjust this value for more or less blurring
    blurred_image = gaussian(binary_image2, sigma=sigma, mode='nearest', preserve_range=True)

    scaled_image = transform.resize(blurred_image, mask_array.shape, mode='edge', anti_aliasing=True)

    binary_image3 = (scaled_image > 127).astype(np.uint8)

    tifffile.imwrite(output, binary_image3, compression='LZW')
    
    client.close()
    cluster.close()


if __name__ == '__main__':
    main()
