import numpy as np
import tifffile

import os
import sys
import re
import argparse

import zarr
import dask
import dask.array as da
from distributed import LocalCluster, Client, Variable

from pathlib import Path

import json

import shutil

def padding(data_chunk, median, amp):
    mm = median

    # Calculate vv
    vv = int(mm // amp)  # Use integer division

    # Generate masks for low intensity pixels
    masks = (data_chunk < mm - vv)

    # Set all low intensity pixels to zero
    data_chunk = data_chunk * (~masks).astype(np.uint16)

    white_noise = np.random.normal(0, 1.0, data_chunk.shape) * vv + mm
    data_chunk += (white_noise * masks).astype(np.uint16)

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

def main():

    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  padding.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input file path (.n5)")
    parser.add_argument("-t", "--thread", dest="thread", type=int, default=0, help="number of threads")
    parser.add_argument("-c", "--ch", dest="ch", type=str, default=0, help="channel")
    parser.add_argument("-s", "--scale", dest="scale", type=str, default=0, help="scale")
    parser.add_argument("--verbose", dest="verbose", default=False, action="store_true", help="enable verbose logging")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    input = args.input
    ch = args.ch
    scales = args.scale.split(",")
    threadnum = args.thread

    dataname = os.path.basename(input)
    indirpath = os.path.dirname(input)
    stem = os.path.splitext(dataname)[0]

    base_path = os.path.join(indirpath, stem + ".n5")

    group_paths = []
    for scale in scales:
        group_path = 'setup' + ch + '/timepoint0/' + scale
        group_paths.append(group_path)

    n5_store = zarr.N5Store(base_path)
    n5input = zarr.open(store=n5_store, mode='r+')

    bins = 65536
    range = (0, 65535)

    cluster = LocalCluster(n_workers=threadnum, threads_per_worker=1)
    client = Client(cluster, asynchronous=True)
    for g in group_paths:
        downsampling_factors = None
        pixel_resolution = None
        if os.path.exists(os.path.join(base_path, g)):
            s_attr = os.path.join(base_path, g+os.path.sep+"attributes.json")
            with open(s_attr, 'r+') as f:
                data = json.load(f)
                if 'downsamplingFactors' in data:
                    downsampling_factors = data['downsamplingFactors']
                if 'pixelResolution' in data:
                    pixel_resolution = data['pixelResolution']
        
        print(n5input[g].shape)
        
        dask_array = da.from_zarr(n5input[g])
        futures = [dask.delayed(compute_histogram)(chunk=chunk, bins=bins, range=range) for chunk in dask_array.to_delayed().ravel()]
        histograms = np.array(dask.compute(futures)[0])
        overall_histogram = np.sum(histograms, axis=0)
        median_value = find_median_from_histogram(overall_histogram, range)
        padded_dask_array = dask_array.map_blocks(padding, median=median_value, amp=10, dtype=dask_array.dtype)

        new_dataset_path = 'tmp_'+ g
        padded_dask_array.to_zarr(n5_store, component=new_dataset_path, compressor=n5input[g].compressor)

        if os.path.exists(os.path.join(base_path, new_dataset_path)):
            s_attr = os.path.join(base_path, new_dataset_path+os.path.sep+"attributes.json")
            with open(s_attr, 'r+') as f:
                data = json.load(f)
                if downsampling_factors is not None:
                    data['downsamplingFactors'] = downsampling_factors
                if pixel_resolution is not None:
                    data['pixelResolution'] = pixel_resolution
                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
        
        del n5input[g]
        try:
            shutil.move(os.path.join(base_path, new_dataset_path), os.path.join(base_path, g))
            shutil.rmtree(os.path.join(base_path, 'tmp_setup'+ch))
        except shutil.Error as e:
            print("Error moving the directory:", e)

    
    client.close()
    cluster.close()


if __name__ == '__main__':
    main()
