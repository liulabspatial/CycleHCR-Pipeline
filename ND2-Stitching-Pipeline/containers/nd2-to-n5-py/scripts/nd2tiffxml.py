import glob
import os
import sys
import re
import argparse
import platform

import subprocess

import logging

import asyncio

import xml.etree.ElementTree as ET
import copy

import json

def main():

    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  nd2tiffxml.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input files")
    parser.add_argument("-o", "--output", dest="output", type=str, default=None, help="output file path (.xml)")
    parser.add_argument("-c", "--csv", dest="csv", type=str, default=None, help="output csv file path (.csv)")
    parser.add_argument("-x", "--crop", dest="crop", type=str, default="0,0,0,0", help="cropping percentage (top,bottom,left,right)")
    parser.add_argument("--verbose", dest="verbose", default=False, action="store_true", help="enable verbose logging")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    input = args.input
    output = args.output
    csvoutput = args.csv
    crop_percentages = [float(num) if '.' in num else int(num) for num in args.crop.split(',')]

    outlist = []

    for t in range(0, 100):
        dataname = os.path.basename(output)
        outdirpath = os.path.dirname(output)
        stem = os.path.splitext(dataname)[0]

        found = False
        xml = ET.parse(input)
        parent_map = {c: p for p in xml.iter() for c in p}
        for item in xml.findall(".//FileMapping"):
            tile_id = int(item.attrib['series'])
            time_id = int(item.attrib['timepoint'])
            ch_id = int(item.attrib['channel'])
            if time_id == t:
                file = item.find("./file")
                file.text = "./tiff_" + str(tile_id) + "_" + str(ch_id) + "_" + str(time_id) + ".tif"
                item.attrib['series'] = '0';
                item.attrib['timepoint'] = '0';
                item.attrib['channel'] = '0';
                found = True
            else:
                parent_map[item].remove(item)
        for item in xml.findall(".//ViewRegistration"):
            time_id = int(item.attrib['timepoint'])
            if time_id != t:
                parent_map[item].remove(item)
            else:
                item.attrib['timepoint'] = '0';
        for item in xml.findall(".//Timepoints"):
            item.find("./last").text = '0'

        mat_offset_dic = {}
        tile_offset_dic = {}

        for item in xml.findall(".//ViewSetup"):
            vs_item = item.find("./voxelSize")
            str_val = vs_item.find("./size").text
            str_array = str_val.split(" ")
            voxel_size = []
            for elem in str_array:
                voxel_size.append(float(elem))

            setup_id = item.find("./id").text
            attr_item = item.find("./attributes")
            tile_item = attr_item.find("./tile")
            tile_id = tile_item.text

            size = item.find("./size")
            str_array = size.text.split(" ")
            num_array_mat = []
            num_array_physical = []
            out_str_arr = ""

            w = int(str_array[0])
            h = int(str_array[1])

            st_x = int(crop_percentages[2] * 0.01 * w + 0.5)
            ed_x = int( (1.0 - crop_percentages[3] * 0.01) * w + 0.5)
            st_y = int(crop_percentages[0] * 0.01 * h + 0.5)
            ed_y = int( (1.0 - crop_percentages[1] * 0.01) * h + 0.5)

            num_array_mat.append(st_x)
            num_array_physical.append( num_array_mat[0] * voxel_size[0] )
            out_str_arr += str(ed_x - st_x)

            num_array_mat.append(st_y)
            num_array_physical.append( num_array_mat[1] * voxel_size[1] )
            out_str_arr +=  " " + str(ed_y - st_y)

            num_array_mat.append(0)
            out_str_arr += " " + str_array[2]

            mat_offset_dic[setup_id] = num_array_mat
            tile_offset_dic[tile_id] = num_array_physical
            size.text = out_str_arr

        print("mat " + str(mat_offset_dic))
        print("tile " + str(tile_offset_dic))

        for item in xml.findall(".//Tile"):
            id_item = item.find("./id")
            if id_item is None:
                continue
            tile_id = id_item.text
            location = item.find("./location")
            if location is None:
                continue
            str_array = location.text.split(" ")
            out_str = ""
            fval = float(str_array[0]) + tile_offset_dic[tile_id][0]
            out_str += str(fval)
            fval = -1.0 * float(str_array[1]) + tile_offset_dic[tile_id][1]
            out_str += " " + str(fval)
            out_str += " " + str_array[2]
            location.text = out_str

        for r_item in xml.findall(".//ViewRegistration"):
            setup_id = r_item.attrib['setup']
            item = r_item.find("./ViewTransform")
            name = item.find("./Name").text
            if name == "Translation":
                str_mat = item.find("affine")
                print(str_mat.text)
                mat_str_array = str_mat.text.split(" ")
                out_str_mat = ""
                count = 0
                for elem in mat_str_array:
                    if count == 3:
                        fval = float(elem) + mat_offset_dic[setup_id][0]
                        out_str_mat += " " + str(fval)
                    elif count == 7:
                        fval = float(elem) + mat_offset_dic[setup_id][1]
                        out_str_mat += " " + str(fval)
                    else:
                        if count > 0:
                            out_str_mat += " "
                        out_str_mat += elem
                    count += 1
                print(out_str_mat)
                str_mat.text = out_str_mat

        if found == True:
            opath = os.path.join(outdirpath, stem + "-t" + str(t) + ".xml")
            xml.write(opath)
            outlist.append(opath)

    
    with open(csvoutput, 'w') as csvfile:
        for fname in outlist:
            csvfile.write(fname + "\n")


    


if __name__ == '__main__':
    main()
