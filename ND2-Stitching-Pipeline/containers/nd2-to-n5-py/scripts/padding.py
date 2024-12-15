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

def get_chunk_size_at_position(position, chunk_size, dataset_shape):
    """
    Calculate the actual chunk size at a specific position in the dataset.
    
    :param position: Tuple of integers indicating the chunk position.
    :param chunk_size: Tuple of integers indicating the regular chunk size.
    :param dataset_shape: Tuple of integers indicating the overall dataset shape.
    :return: Tuple of integers indicating the actual chunk size at the given position.
    """
    # Calculate the start and end coordinates of the chunk
    chunk_start = [pos * cs for pos, cs in zip(position, chunk_size)]
    chunk_end = [min(start + cs, ds) for start, cs, ds in zip(chunk_start, chunk_size, dataset_shape)]
    
    # Calculate the actual chunk size
    actual_chunk_size = [end - start for start, end in zip(chunk_start, chunk_end)]
    return tuple(actual_chunk_size)

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


def padding2(in_dataset, out_dataset, idx, median, amp, retry, wait):

    try:
        # Attempt to read the chunk
        data_chunk = in_dataset.read_chunk(idx)
        create_empty = False
        if data_chunk is None:
            create_empty = True
            print(f"Chunk {idx} is missing.")
                    
        # Check for NaNs or infinite values
        if create_empty == False:
            if np.isnan(data_chunk).any() or np.isinf(data_chunk).any():
                create_empty = True
                print(f"Chunk {idx} contains NaNs or infinite values. It will be ignored")
        
        if create_empty == True:
            chunk_size = get_chunk_size_at_position(idx, in_dataset.chunks, in_dataset.shape)
            data_chunk = np.zeros(chunk_size, dtype=in_dataset.dtype)
            print(f"Empty chunk {idx} is created.")
            
    except Exception as e:
        print(f"Error reading chunk {idx}: {e}")
        return False
    
    mm = median

    # Calculate vv
    vv = int(mm // amp)  # Use integer division

    # Generate masks for low intensity pixels
    masks = (data_chunk < mm - vv)

    # Set all low intensity pixels to zero
    data_chunk = data_chunk * (~masks).astype(np.uint16)

    white_noise = np.random.normal(0, 1.0, data_chunk.shape) * vv + mm
    data_chunk += (white_noise * masks).astype(np.uint16)

    done = False
    for i in range(0, retry):
        try:
            out_dataset.write_chunk(idx, data_chunk)
            chk = validate_chunk(out_dataset, idx)
            if chk == True:
                break
        except Exception as e:
            print(f"Error writing chunk {idx}: {e}")
        print(f"retry to write chunk {idx}")
        time.sleep(wait)

    return True

def compute_histogram(chunk, bins, range):
    hist, edges = np.histogram(chunk, bins=bins, range=range)
    return hist

def compute_histogram2(dataset, idx, bins, range):
    try:
        # Attempt to read the chunk
        data_chunk = dataset.read_chunk(idx)
        if data_chunk is None:
            print(f"Chunk {idx} is missing. It will be ignored.")
            data_chunk = np.array([])
                
        # Check for NaNs or infinite values
        if np.isnan(data_chunk).any() or np.isinf(data_chunk).any():
            print(f"Chunk {idx} contains NaNs or infinite values. It will be ignored.")
            data_chunk = np.array([])

        hist, edges = np.histogram(data_chunk, bins=bins, range=range)
        return hist
                
    except Exception as e:
        print(f"Error reading chunk {idx}: {e}")
        return None
    return None

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

    with open(os.path.join(base_path, "attributes.json"), 'w') as f:
        data = {}
        data['n5'] = "2.2.0"
        f.seek(0)
        json.dump(data, f, indent=4)
        f.truncate()

    group_paths = []
    for scale in scales:
        group_path = 'setup' + ch + '/timepoint0/' + scale
        group_paths.append(group_path)

    n5input = z5py.File(base_path, use_zarr_format=False)

    bins = 65534
    range = (1, 65535)

    cluster = LocalCluster(n_workers=threadnum, threads_per_worker=1)
    client = Client(cluster)
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

        shape = n5input[g].shape
        chunks = n5input[g].chunks
        num_chunks = [int(np.ceil(s / c)) for s, c in zip(shape, chunks)]
        futures = []
        for idx in np.ndindex(*num_chunks):
            future = dask.delayed(compute_histogram2)(dataset=n5input[g], idx=idx, bins=bins, range=range)
            futures.append(future)
        histograms = dask.compute(futures)[0]
        overall_histogram = np.sum(histograms, axis=0)
        median_value = find_median_from_histogram(overall_histogram, range)

        new_dataset_path = 'tmp_'+ g
        new_dataset = n5input.create_dataset(new_dataset_path, shape=n5input[g].shape, chunks=n5input[g].chunks, dtype=n5input[g].dtype)
        
        futures = []
        for idx in np.ndindex(*num_chunks):
            future = dask.delayed(padding2)(in_dataset=n5input[g], out_dataset=new_dataset, idx=idx, median=median_value, amp=10, retry=10, wait=5)
            futures.append(future)
        padding_results = dask.compute(futures)[0]

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
