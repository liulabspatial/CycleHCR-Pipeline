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

    usage_text = ("Usage:" + "  fix_n5xml.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input files")
    parser.add_argument("-o", "--output", dest="output", type=str, default=None, help="output file path (.xml)")
    parser.add_argument("--verbose", dest="verbose", default=False, action="store_true", help="enable verbose logging")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    input = args.input
    output = args.output

    dataname = os.path.basename(input)
    indirpath = os.path.dirname(input)
    stem = os.path.splitext(dataname)[0]

    xml = ET.parse(input)
    for item in xml.findall(".//ViewTransform"):
        name = item.find("./Name").text
        if name == "Translation":
            str_mat = item.find("affine")
            print(str_mat.text)
            mat_str_array = str_mat.text.split(" ")
            out_str_mat = ""
            count = 0
            for elem in mat_str_array:
                if count == 7:
                    fval = float(elem)
                    fval *= -1.0
                    out_str_mat += " " + str(fval)
                else:
                    if count > 0:
                        out_str_mat += " "
                    out_str_mat += elem
                count += 1
            print(out_str_mat)
            str_mat.text = out_str_mat

    xml.write(output)

    


if __name__ == '__main__':
    main()
