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

import shutil

def main():

    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  fix_res.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input directory")
    parser.add_argument("-o", "--output", dest="output", type=str, default=None, help="output directory")
    parser.add_argument("-x", "--xml", dest="xml", type=str, default=None, help="original bigstitcher xml")
    parser.add_argument("--verbose", dest="verbose", default=False, action="store_true", help="enable verbose logging")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    input = args.input
    output = args.output
    xml = args.xml
    t_ints = [int(s) for s in re.findall("\d+", input)]
    time = t_ints[-1]
    print("time: " + str(time))

    res = [1.0, 1.0, 1.0]
    if xml is not None and os.path.exists(xml):
        xml = ET.parse(xml)
        for item in xml.findall(".//voxelSize"):
            size = item.find("./size").text
            res = [float(i) for i in size.split()]
            break
    
    print(res)

    re_setup = re.compile(r'^.*setup[0-9]+$')
    re_timepoint = re.compile(r'^.*timepoint[0-9]+$')

    in_n5path = ""
    xml = ET.parse(input)
    for item in xml.findall(".//n5"):
        in_n5path = os.path.join(os.path.dirname(input), item.text)  
    
    out_n5path = output #os.path.join(output, "t" + str(time))

    os.makedirs(out_n5path, exist_ok=True)

    setupfolders = [ d.path for d in os.scandir(in_n5path) if d.is_dir() ]
    for dirpath in setupfolders:
        if re_setup.fullmatch(dirpath):
            print(dirpath)
            chints = [int(s) for s in re.findall("\d+", dirpath)]
            chid = chints[-1]
            tpfolders = [ d.path for d in os.scandir(dirpath) if d.is_dir() ]
            for tppath in tpfolders:
                if re_timepoint.fullmatch(tppath):
                    print(tppath)
                    ints = [int(s) for s in re.findall("\d+", tppath)]
                    if ints[-1] == 0:
                        shutil.move(tppath, os.path.join(out_n5path, "c" + str(chid)))
                        print(os.path.join(out_n5path, "c" + str(chid)))
    
    re_ch = re.compile(r'^.*c[0-9]+$')

    downsampling_factors = []
    subfolders = [ d.path for d in os.scandir(out_n5path) if d.is_dir() ]
    for dirpath in subfolders:
        if re_ch.fullmatch(dirpath):
            ch_attr = os.path.join(dirpath, "attributes.json")
            if os.path.isfile(ch_attr):
                with open(ch_attr, 'r+') as f:
                    data = json.load(f)
                    data['resolution'] = res
                    data['backgroundValue'] = 0.0
                    f.seek(0)
                    json.dump(data, f, indent=4)
                    f.truncate()
            else:
                print("No such file " + ch_attr)
            s = 0
            downsampling_factors = []
            while os.path.exists(os.path.join(dirpath, "s"+str(s))):
                s_attr = os.path.join(dirpath, "s"+str(s)+os.path.sep+"attributes.json")
                with open(s_attr, 'r+') as f:
                    data = json.load(f)
                    downsampling_factors.append(data['downsamplingFactors'])
                    data['pixelResolution'] = res
                    f.seek(0)
                    json.dump(data, f, indent=4)
                    f.truncate()
                s += 1
    with open(os.path.join(out_n5path, "attributes.json"), 'w') as f:
        data = {}
        data['scales'] = downsampling_factors
        data['pixelResolution'] = {"unit":"um","dimensions": res}
        data['n5'] = "2.2.0"
        f.seek(0)
        json.dump(data, f, indent=4)
        f.truncate()

if __name__ == '__main__':
    main()
