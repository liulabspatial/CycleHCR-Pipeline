#!/bin/bash

usage() {
	echo "Usage: crop_s0.sh [OPTION]... [FILE]"
	echo "cropping s0 level"
	echo
	echo "Options:"
    echo "  -o, --output		    path to an output directory"
    echo "  --step1		            output directory of step1"
    echo "  --step2		            output directory of step2, has subdirectory transform"
    echo "  --fix                   path to fix N5 used to perform registration in step2 (e.g. b0/t0)"
    echo "  --seg                   path to segmentation tiff from cellpose"
    echo "  --idx                   comma separated list of index"
	echo "  -h, --help		    display this help and exit"
	exit 1
}

for OPT in "$@"
do
	case "$OPT" in
		'-h'|'--help' )
			usage
			exit 1
			;;
		'-o'|'--output' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			outdir="$2"
			shift 2
			;;
        '--step1' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			step1dir="$2"
			shift 2
			;;
        '--step2' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			step2dir="$2"
			shift 2
			;;
        '--fix' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			fix_subpath="$2"
			shift 2
			;;
        '--seg' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			seg="$2"
			shift 2
			;;
        '--idx' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			idx="$2"
			shift 2
			;;
	esac
done

# Absolute path to this script, e.g. /home/user/bin/foo.sh
SCRIPT=$(readlink -f "$0")
# Absolute path this script is in, thus /home/user/bin
SCRIPTPATH=$(dirname "$SCRIPT")
cd $SCRIPTPATH

SIFFILE="bigstream-py-0.0.10.sif"
if [ ! -f "$SIFFILE" ]; then
    singularity build "$SIFFILE" docker://ghcr.io/janeliascicomp/bigstream-py:0.0.10.sif
fi

fix=${step1dir}/${fix_subpath}

# loop through batch, loop through time, save as n5_arr
declare -a batch_arr=($(ls $step1dir))
declare -a mov_arr=()
for b in "${batch_arr[@]}"; do
    declare -a time_arr=($(ls "$step1dir"/"$b/" -I *mask.tif))
    for t in "${time_arr[@]}"; do
        n5=$(realpath "$step1dir"/"$b"/"$t")
        if [ "$n5" != "$(realpath $fix)" ]; then
            mov_arr+=("$n5")
        fi
    done
done
declare -p mov_arr

do_cropping() {
    fix=$1
    mov=$2
    transformdir=$3
    seg=$4
    idx=$5
    out=$6

    singularity run \
        --env TINI_SUBREAPER=true \
        -B "$fix":"$fix" \
        -B "$mov":"$mov" \
        -B "$transformdir":"$transformdir" \
        -B "$seg":"$seg" \
        -B "$out":"$out" \
        ./bigstream-py-0.0.10.sif \
        /entrypoint.sh bigstream_segment_s0 \
        -f "$fix" \
        -m "$mov" \
        -td "$transformdir" \
        -seg "$seg" \
        -idx "$idx" \
        -o "$out"
}

do_cropping_fix() {
    fix=$1
    seg=$2
    idx=$3
    out=$4

    singularity run \
        -B "$fix":"$fix" \
        -B "$seg":"$seg" \
        -B "$out":"$out" \
        ./bigstream-py-0.0.10.sif \
        /entrypoint.sh fix_segment_s0 \
        -f "$fix" \
        -seg "$seg" \
        -idx "$idx" \
        -o "$out"
}

export -f do_cropping_fix
export -f do_cropping


do_cropping_fix "$fix" "$seg" "$idx" "$outdir"
parallel --jobs=4 --verbose do_cropping "$fix" ::: ${mov_arr[@]} ::: "$step2dir/transform" ::: "$seg" ::: "$idx" ::: "$outdir"