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


# https://kevinmccarthy.org/2016/07/25/streaming-subprocess-stdin-and-stdout-with-asyncio-in-python/
async def _read_stream(stream, cb):  
    while True:
        ch = await stream.read(1)
        if ch:
            try:
                cb(ch.decode("utf-8"))
            except UnicodeDecodeError:
                print(ch)
        else:
            break

async def _stream_subprocess(cmd, stdout_cb, stderr_cb):  
    process = await asyncio.create_subprocess_exec(*cmd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    await asyncio.wait([
        asyncio.create_task(_read_stream(process.stdout, stdout_cb)),
        asyncio.create_task(_read_stream(process.stderr, stderr_cb))
    ])
    return await process.wait()

def execute(cmd, stdout_cb, stderr_cb):  
    loop = asyncio.new_event_loop()
    #asyncio.set_event_loop(loop)
    rc = loop.run_until_complete(
        _stream_subprocess(
            cmd,
            stdout_cb,
            stderr_cb,
    ))
    loop.close()
    return rc
##################

def main():

    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  calc_stitch.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input files")
    parser.add_argument("-j", "--imagej", dest="imagej", type=str, default=None, help="path to imagej")
    parser.add_argument("-m", "--memory", dest="memory", type=str, default=None, help="amount of heap memory")
    parser.add_argument("-d", "--downsample", dest="downsample", type=str, default="2,2,1", help="downsampling factors")
    parser.add_argument("-r", "--minr", dest="minr", type=float, default=0.1, help="lower threshold of the filter")
    parser.add_argument("-t", "--thread", dest="thread", type=int, default=1, help="number of threads")
    parser.add_argument("--verbose", dest="verbose", default=False, action="store_true", help="enable verbose logging")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    input = args.input
    ij = "/app/fiji/Fiji.app/ImageJ-linux64"
    if args.imagej is not None:
        ij = args.imagej
    
    downsample = args.downsample.split(",")
    minr = args.minr
    threadnum = args.thread

    macro_dir = os.path.dirname(os.path.realpath(__file__))
    print(macro_dir)

    print(downsample)

    in_n5path = ""
    xml = ET.parse(input)
    for item in xml.findall(".//n5"):
        in_n5path = os.path.join(os.path.dirname(input), item.text) 
    with open(os.path.join(in_n5path, "attributes.json"), 'w') as f:
        data = {}
        data['n5'] = "2.5.1"
        f.seek(0)
        json.dump(data, f, indent=4)
        f.truncate() 

    ijargs2 = "select=" + input + " process_angle=[All angles] process_channel=[All channels] process_illumination=[All illuminations] process_tile=[All tiles] process_timepoint=[All Timepoints] method=[Phase Correlation] downsample_in_x=" + downsample[0] + " downsample_in_y=" + downsample[1] + " downsample_in_z=" + downsample[2]
    ijargs2 += ";"
    ijargs2 += "select=" + input + " filter_by_link_quality min_r="+ str(minr) +" max_r=1 filter_by_shift_in_each_dimension max_shift_in_x=100 max_shift_in_y=100 max_shift_in_z=100 max_displacement=0"
    ijargs2 += ";"
    ijargs2 += "select=" + input + " process_angle=[All angles] process_channel=[All channels] process_illumination=[All illuminations] process_tile=[All tiles] process_timepoint=[All Timepoints] relative=2.500 absolute=3.500 global_optimization_strategy=[Two-Round using Metadata to align unconnected Tiles and iterative dropping of bad links] fix_group_0-0"
    ijargs2 += ";"
    ijargs2 += "select=" + input +  " process_angle=[All angles] process_channel=[All channels] process_illumination=[All illuminations] process_tile=[All tiles] process_timepoint=[All Timepoints] icp_refinement_type=[Simple (tile registration)] downsampling=[Downsampling 8/8/4] interest=[Average Threshold] icp_max_error=[Normal Adjustment (<5px)]"
    ijargs2 += ";"
    ijargs2 += str(threadnum)
    commands = []
    commands.append(f"{ij}")
    if args.memory is not None:
        commands.append("--mem")
        commands.append(args.memory)
    commands.append("--headless")
    commands.append("-macro")
    commands.append(os.path.join(macro_dir, "run_stitch.ijm"))
    commands.append(ijargs2)

    print("running imagej...")
    logging.info(commands)
    print(execute(
        commands,
        lambda x: print("%s" % x, end=''),
       lambda x: print("%s" % x, end=''),
    ))

if __name__ == '__main__':
    main()
