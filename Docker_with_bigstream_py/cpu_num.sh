#!/bin/bash

outdir=/home/liulab/labdata/Takashi/Docker_with_bigstream_py/test_dataset

fix=${outdir}/step1/b0/t0/
mov=${outdir}/step1/b1/t3/
out=${outdir}/step2/

echo "$fix"
echo "$mov"

mkdir -p "$out"

singularity run \
        --env TINI_SUBREAPER=true \
        -B "$fix":"$fix" \
        -B "$mov":"$mov" \
        -B "$out":"$out" \
        ./bigstream-py-0.0.2.sif \
        /entrypoint.sh thread_num