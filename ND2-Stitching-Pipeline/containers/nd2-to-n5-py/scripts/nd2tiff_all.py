import os
import sys
import argparse
import time
from pathlib import Path

import nd2
import numpy as np
import tifffile
import dask
from dask import delayed, compute
from dask.distributed import Client, LocalCluster

def get_key_index(dictionary, key):
    for i, k in enumerate(dictionary.keys()):
        if k == key:
            return i
    return -1

def save_tiff(region, z, h, w, out_path):
    arr = np.zeros((z, h, w), dtype=region.dtype)
    arr[:z, :h, :w] = region
    arr = np.expand_dims(arr, axis=0)  # T
    arr = np.expand_dims(arr, axis=2)  # C

    tifffile.imwrite(
        out_path,
        arr,
        imagej=True,
        metadata={'axes': 'TZCYX'},
        compression="ZLIB",
        compressionargs={"level": 1}
    )
    print(f"Saved: {out_path}")
    return out_path

def convert_all_nd2_frames():
    argv = sys.argv[1:]

    parser = argparse.ArgumentParser(description="ND2 to multi-TIFF converter with Dask")
    parser.add_argument("-i", "--input", type=str, required=True, help="Input ND2 file")
    parser.add_argument("-o", "--output", type=str, required=True, help="Output directory path")
    parser.add_argument("-c", "--crop", type=str, default="0,0,0,0", help="Cropping percentage (top,bottom,left,right)")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    args = parser.parse_args(argv)

    input_path = args.input
    output_dir = args.output
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    crop = [float(x) for x in args.crop.split(",")]
    crop_top, crop_bottom, crop_left, crop_right = crop

    # Start Dask cluster
    cluster = LocalCluster(
            n_workers=args.workers,
            threads_per_worker=1,
            memory_limit='8GB'
        )
    client = Client(cluster)
    print("Dask cluster started:", client)

    # Read image metadata
    darray = nd2.imread(input_path, dask=True)

    with nd2.ND2File(input_path) as nd2file:
        sizes = nd2file.sizes
        print("ND2 sizes:", sizes)

        T = sizes.get('T', 1)
        P = sizes.get('P', 1)
        C = sizes.get('C', 1)
        Z = sizes.get('Z', 1)
        Y = sizes.get('Y', 1)
        X = sizes.get('X', 1)

        time_idx = get_key_index(sizes, 'T')
        tile_idx = get_key_index(sizes, 'P')
        ch_idx = get_key_index(sizes, 'C')

    st_x = int(crop_left * 0.01 * X + 0.5)
    ed_x = int((1.0 - crop_right * 0.01) * X + 0.5)
    st_y = int(crop_top * 0.01 * Y + 0.5)
    ed_y = int((1.0 - crop_bottom * 0.01) * Y + 0.5)

    cropped_w = ed_x - st_x
    cropped_h = ed_y - st_y

    tasks = []

    for t in range(T):
        for p in range(P):
            for c in range(C):
                # Dynamic slicing
                index = []
                if time_idx >= 0: index.append(t)
                if tile_idx >= 0: index.append(p)
                index.append(slice(0, Z))
                if ch_idx >= 0: index.append(c)
                index.extend([slice(st_y, ed_y), slice(st_x, ed_x)])

                region = darray[tuple(index)]

                out_filename = f"t{t:03d}_c{c:02d}_p{p:02d}.tiff"
                out_path = os.path.join(output_dir, out_filename)

                task = delayed(save_tiff)(region, Z, cropped_h, cropped_w, out_path)
                tasks.append(task)

    start = time.time()
    compute(*tasks)
    end = time.time()

    print(f"\nAll files processed in {end - start:.2f} seconds")
    client.shutdown()

def main():
    convert_all_nd2_frames()

if __name__ == '__main__':
    main()