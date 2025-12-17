import pandas as pd
import numpy as np
import math
import tifffile

import sys
import os
import re
import argparse
import platform


def read_3d_coordinates_from_csv(file_path):
    """
    Reads 3D coordinates from a CSV file.

    :param file_path: Path to the CSV file.
    :return: DataFrame with 3D coordinates.
    """
    # Load the CSV file
    df = pd.read_csv(file_path)

    # Assuming the columns are named 'x', 'y', 'z'
    if all(col in df.columns for col in ['z', 'y', 'x']):
        return df[['z', 'y', 'x']]
    else:
        raise ValueError("CSV file must contain 'x', 'y', 'z' columns")

def spot_assignment():

    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  spot_assignment.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input spot csv files")
    parser.add_argument("-s", "--seg", dest="seg", type=str, default=None, help="input segmented image file")
    parser.add_argument("-o", "--output", dest="output", type=str, default=None, help="output file path")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    input = args.input.split(",")
    output = args.output
    seg_file_path = args.seg
    
    lb = tifffile.imread(seg_file_path)

    lb_id = np.unique(lb[lb != 0])
    z, y, x = lb.shape

    count = pd.DataFrame(np.empty([len(lb_id), 0]), index=lb_id)
    df = pd.DataFrame(np.zeros([len(lb_id), 1]), index=lb_id, columns=['count'])

    for f in input:
        r = os.path.basename(f).split('/')[-1]
        r = r.split('.')[0]

        spots = read_3d_coordinates_from_csv(f).to_numpy()
        rounded_spots = np.round(spots).astype('int')

        spot_id = 0
        for spot in rounded_spots:
            #print("Z:", spot[0], "Y:", spot[1], "X:", spot[2])
            if np.any(np.isnan(spot)):
                print('NaN found on line# {}'.format(spot_id+1))
            else:
                if np.any(spot<0):
                    print('Point outside of fixed image found on line# {}'.format(spot_id+1))
                else:
                    try:
                        # if all non-rounded coord are valid values (none is NaN)
                        Coord = np.minimum(spot, [x, y, z])
                        idx = lb[Coord[2]-1, Coord[1]-1, Coord[0]-1]
                        if idx > 0 and idx <= len(lb_id):
                            # increment counter
                            df.loc[idx, 'count'] = df.loc[idx, 'count']+1
                    except Exception as e:
                        print('Unexpected error on line# {}: {}'.format(spot_id+1, e))
            spot_id += 1
        count.loc[:, r] = df.to_numpy()

    count = count.astype(int)
    print("Writing", output)
    count.to_csv(output)

def main():
    spot_assignment()


if __name__ == '__main__':
    main()