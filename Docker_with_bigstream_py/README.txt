singularity pull bigstream-py-0.0.3.sif docker://ghcr.io/janeliascicomp/bigstream-py:0.0.3

# How I am running this thing #
1. make docker: docker build -t mydocker .
2. run mydocker using the following run_docker.sh


#!/bin/bash

outdir=/mnt/d/Docker_test/

fix=${outdir}/step1/b0/t0/
mov=${outdir}/step1/b1/t3/
out=${outdir}/step2/

echo "$fix"
echo "$mov"


# docker run, mount N5 data and output folder
# call entrypoint.sh, which consumes the name of the python script without .py
# list python parameters; double dash (--) are optional parameters
docker run \
        --rm \
        -v "$fix":"$fix" \
        -v "$mov":"$mov" \
        -v "$out":"$out" \
        mydocker \
        /entrypoint.sh bigstream_in_memory \
        -f "$fix" \
        -m "$mov" \
        -s s4 \
        -d c3 \
        -o "$out" \
        --aff_as 2 \
        --aff_sf 2,1 \
        --aff_ss 2,0 \
        --aff_n 1 \
        --def_as 2 \
        --def_sf 2,1 \
        --def_ss 0.25,0 \
        --def_n 1 \
        --def_cps 130