#!/bin/bash

outdir=/home/liulab/labdata/Takashi/Docker_with_bigstream_py/test_dataset

fix=${outdir}/step1/b0/t0/
mov=${outdir}/step1/b1/t3/
out=${outdir}/step2/

echo "$fix"
echo "$mov"

mkdir -p "$out"

# Absolute path to this script, e.g. /home/user/bin/foo.sh
SCRIPT=$(readlink -f "$0")
# Absolute path this script is in, thus /home/user/bin
SCRIPTPATH=$(dirname "$SCRIPT")

singularity run \
        --env TINI_SUBREAPER=true \
        -B "$fix":"$fix" \
        -B "$mov":"$mov" \
        -B "$out":"$out" \
        $SCRIPTPATH/ghcr.io-janeliascicomp-bigstream-py-0.0.16.img \
        /entrypoint.sh thread_num