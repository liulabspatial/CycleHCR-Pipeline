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

import io

import gzip

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
        if data_chunk is None:
            print(f"Chunk {idx} is missing.")
            return False
                    
        # Check for NaNs or infinite values
        if np.isnan(data_chunk).any() or np.isinf(data_chunk).any():
            print(f"Chunk {idx} contains NaNs or infinite values.")
            return False
                    
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
            print(f"Chunk {idx} is missing.")
            return None
                
        # Check for NaNs or infinite values
        if np.isnan(data_chunk).any() or np.isinf(data_chunk).any():
            print(f"Chunk {idx} contains NaNs or infinite values.")
            return None

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

def validate_chunk(n5_path, dataset_name, idx):
    chunk_subpath = os.path.join(*[str(id) for id in reversed(idx)])
    absolute_chunk_path = os.path.join(n5_path, dataset_name, chunk_subpath)

    try:
        with open(absolute_chunk_path, 'rb') as f:
            # Skip the first 16 bytes
            f.seek(16)
            
            # Read the rest of the file
            remaining_data = f.read()

            # Use a BytesIO buffer to decompress the remaining data
            buffer = io.BytesIO(remaining_data)
            with gzip.GzipFile(fileobj=buffer) as g:
                # Try to read the decompressed data
                while g.read(8192):
                    pass

        return True
    except Exception as e:
        print(f"The GZIP file is invalid after the first 16 bytes: {e}")
        return False

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

    bins = 65536
    range = (0, 65535)

    cluster = LocalCluster(n_workers=threadnum, threads_per_worker=1)
    client = Client(cluster)
    for g in group_paths:

        shape = n5input[g].shape
        chunks = n5input[g].chunks
        num_chunks = [int(np.ceil(s / c)) for s, c in zip(shape, chunks)]
        futures = []
        for idx in np.ndindex(*num_chunks):
            future = dask.delayed(validate_chunk)(n5_path=base_path, dataset_name=g, idx=idx)
            futures.append(future)
        isvalid = dask.compute(futures)[0]
        
        sum = 0
        for r in isvalid:
            if r == False:
                sum += 1

        print("error: " + str(sum))

    
    client.close()
    cluster.close()


if __name__ == '__main__':
    main()
