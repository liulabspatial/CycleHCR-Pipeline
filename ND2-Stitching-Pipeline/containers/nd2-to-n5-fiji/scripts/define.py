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

    usage_text = ("Usage:" + "  define.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input files")
    parser.add_argument("-o", "--output", dest="output", type=str, default=None, help="output file path (.xml)")
    parser.add_argument("-j", "--imagej", dest="imagej", type=str, default=None, help="path to imagej")
    parser.add_argument("-t", "--thread", dest="thread", type=int, default=0, help="number of threads")
    parser.add_argument("--verbose", dest="verbose", default=False, action="store_true", help="enable verbose logging")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    input = args.input
    output = args.output
    threadnum = args.thread
    ij = "/app/fiji/Fiji.app/ImageJ-linux64"
    if args.imagej is not None:
        ij = args.imagej

    macro_dir = os.path.dirname(os.path.realpath(__file__))
    print(macro_dir)

    dataname = os.path.basename(output)
    outdirpath = os.path.dirname(output)

    imagej_arg = "define_dataset=[Automatic Loader (Bioformats based)] project_filename=" + dataname + " path=" + input + " exclude=10 bioformats_series_are?=Tiles move_tiles_to_grid_(per_angle)?=[Do not move Tiles to Grid (use Metadata if available)] how_to_load_images=[Load raw data directly] load_raw_data_virtually dataset_save_path=" + outdirpath

    commands = []
    commands.append(f"{ij}")
    commands.append("--headless")
    commands.append("-macro")
    commands.append(os.path.join(macro_dir, "run_bs.ijm"))
    commands.append(imagej_arg)

    print("running imagej...")
    logging.info(commands)
    print(execute(
        commands,
        lambda x: print("%s" % x, end=''),
        lambda x: print("%s" % x, end=''),
    ))

if __name__ == '__main__':
    main()
