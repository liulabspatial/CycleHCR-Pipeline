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
        if found == True:
            opath = os.path.join(outdirpath, stem + "-t" + str(t) + ".xml")
            xml.write(opath)
            outlist.append(opath)
    
    with open(csvoutput, 'w') as csvfile:
        for fname in outlist:
            csvfile.write(fname + "\n")


    


if __name__ == '__main__':
    main()
