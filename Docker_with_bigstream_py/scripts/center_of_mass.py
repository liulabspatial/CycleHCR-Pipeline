import numpy as np
from scipy.ndimage import center_of_mass
import dask.array as da
from dask import delayed, compute
from dask.distributed import LocalCluster, Client
import tifffile

import sys
import argparse

import csv

from scipy.ndimage import find_objects

def find_objects_in_chunk(image_chunk, offset):
    """
    Find bounding boxes for each segment in a chunk of a 3D indexed image.

    :param image_chunk: 3D numpy array representing a chunk of the image.
    :param offset: Tuple representing the offset of this chunk in the full image (z, y, x).
    :return: Dictionary with segment labels as keys and their bounding boxes as values.
    """
    bounding_boxes = {}

    z_offset, y_offset, x_offset = offset

    for z in range(image_chunk.shape[0]):
        for y in range(image_chunk.shape[1]):
            for x in range(image_chunk.shape[2]):
                label = image_chunk[z, y, x]
                if label != 0:  # Skip background
                    if label not in bounding_boxes:
                        bounding_boxes[label] = [[np.inf, -np.inf], [np.inf, -np.inf], [np.inf, -np.inf]]
                    bbox = bounding_boxes[label]
                    # Update bounding box coordinates with respect to the full image
                    bbox[0][0] = min(bbox[0][0], z + z_offset)  # Min Z
                    bbox[0][1] = max(bbox[0][1], z + z_offset)  # Max Z
                    bbox[1][0] = min(bbox[1][0], y + y_offset)  # Min Y
                    bbox[1][1] = max(bbox[1][1], y + y_offset)  # Max Y
                    bbox[2][0] = min(bbox[2][0], x + x_offset)  # Min X
                    bbox[2][1] = max(bbox[2][1], x + x_offset)  # Max X

    return bounding_boxes

def merge_bounding_boxes(bboxes_list):
    """
    Merge bounding boxes from multiple chunks into a single dictionary.

    :param bboxes_list: List of bounding boxes dictionaries from different chunks.
    :return: Merged dictionary of bounding boxes.
    """
    merged_bboxes = {}
    for bboxes in bboxes_list:
        for label, bbox in bboxes.items():
            if label not in merged_bboxes:
                merged_bboxes[label] = bbox
            else:
                for i in range(3):
                    merged_bboxes[label][i][0] = min(merged_bboxes[label][i][0], bbox[i][0])
                    merged_bboxes[label][i][1] = max(merged_bboxes[label][i][1], bbox[i][1])
    return merged_bboxes

def calculate_centers_of_mass(image, bounding_boxes):
    """
    Calculate the centers of mass for each segment in a 3D indexed image using bounding boxes.

    :param image: 3D numpy array where each unique integer represents a different segment.
    :param bounding_boxes: Dictionary of bounding boxes for each segment.
    :return: Dictionary with segment labels as keys and their centers of mass as values.
    """
    centers_of_mass = {}

    for label, bbox in bounding_boxes.items():
        z_range, y_range, x_range = bbox
        # Extract the subvolume containing the segment
        subvolume = image[z_range[0]:z_range[1]+1, y_range[0]:y_range[1]+1, x_range[0]:x_range[1]+1]
        
        # Create a mask for the current label within the subvolume
        mask = subvolume == label

        # Calculate the coordinates of the center of mass
        total_mass = np.sum(mask)
        if total_mass > 0:
            z_coords, y_coords, x_coords = np.nonzero(mask)
            z_center = np.mean(z_coords) + z_range[0]
            y_center = np.mean(y_coords) + y_range[0]
            x_center = np.mean(x_coords) + x_range[0]
            centers_of_mass[label] = (z_center, y_center, x_center)

    return centers_of_mass

def process_image_in_chunks(image, chunk_size):
    """
    Process a 3D image in chunks and calculate the centers of mass for each segment using Dask.

    :param image: 3D numpy array where each unique integer represents a different segment.
    :param chunk_size: Tuple (z_chunk, y_chunk, x_chunk) indicating the size of each chunk.
    :return: Dictionary with segment labels as keys and their centers of mass as values.
    """
    z_chunks = range(0, image.shape[0], chunk_size[0])
    y_chunks = range(0, image.shape[1], chunk_size[1])
    x_chunks = range(0, image.shape[2], chunk_size[2])

    print(z_chunks)
    print(y_chunks)
    print(x_chunks)

    delayed_bounding_boxes = []

    for z in z_chunks:
        for y in y_chunks:
            for x in x_chunks:
                chunk = image[z:z + chunk_size[0], y:y + chunk_size[1], x:x + chunk_size[2]]
                offset = (z, y, x)
                delayed_bounding_boxes.append(delayed(find_objects_in_chunk)(chunk, offset))

    # Compute all bounding boxes in parallel using Dask
    all_bounding_boxes = compute(*delayed_bounding_boxes)

    # Merge bounding boxes from all chunks
    #merged_bounding_boxes = merge_bounding_boxes(all_bounding_boxes)

    # Calculate centers of mass based on the merged bounding boxes
    #centers_of_mass = calculate_centers_of_mass(image, merged_bounding_boxes)

    centers_of_mass = {}

    return centers_of_mass


def calc_and_save_center_of_mass():
    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  center_of_mass.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input file path")
    parser.add_argument("-o", "--output", dest="output", type=str, default=None, help="output file path")
    parser.add_argument("-t", "--thread", dest="thread", type=int, default=8, help="number of threads")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    client = Client(n_workers=1, threads_per_worker=args.thread)
    input_file_path = args.input
    output_file_path = args.output
    
    # Load the TIFF file as a NumPy array
    with tifffile.TiffFile(input_file_path) as tif:
        image = tif.asarray()

    chunk_size = (256, 256, 256)
    # Process the image in chunks and calculate centers of mass using Dask
    results = process_image_in_chunks(image, chunk_size)

    with open(output_file_path, 'w') as csv_file:  
        writer = csv.writer(csv_file)
        for key, value in results.items():
            writer.writerow([key, value])

def main():
    calc_and_save_center_of_mass()

if __name__ == '__main__':
    main()
