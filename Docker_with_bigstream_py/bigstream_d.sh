#!/bin/bash

usage() {
	echo "Usage: bigstream_d.sh [OPTION]... [FILE]"
	echo "Bigstream distributed"
	echo
	echo "Options:"
	echo "  -i, --input		    path to a step1 directory"
    echo "  -o, --output		path to a step2 directory"
    echo "  -d, --distribute	turn on distribute"
    echo "  -b, --blocksize     blocksize"
    echo "  -w, --worker        threads per worker"
    echo "  -m, --memory        memory limit"
    echo "  -z, --zarr          option to output registered images as zarr in addition to tiff"
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
		'-i'|'--input' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			INPUT="$2"
			shift 2
			;;
		'-o'|'--output' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			OUTPUT="$2"
			shift 2
			;;
        '-d'|'--distribute' )
			DISTRIBUTE="--distribute 1"
			shift 1
			;;
        '-b'|'--blocksize' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			BLOCKSIZE="--blocksize $2"
			shift 2
			;;
        '-w'|'--worker' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			WORKERS="--n_workers $2"
			shift 2
			;;
        '-m'|'--memory' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			MEMORYLIMIT="--memory_limit $2"
			shift 2
			;;
        '-z'|'--zarr' )
			ZARR="--outzarr 1"
			shift 1
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

# specify 3 things: directory of step1 (stitching), specify fix N5, specify output directory of below process, step2 (registration) #

step1outdir=${INPUT}
fix=${step1outdir}/b0/t0/
step2outdir=${OUTPUT}

if [ ! -d "$step2outdir" ]; then
    mkdir -p "$step2outdir"
    echo "Directory created: $step2outdir"
else
    echo "Directory already exists: $step2outdir"
fi

# loop through batch, loop through time, save as mov_arr except for fix n5
declare -a batch_arr=($(ls $step1outdir))
declare -a mov_arr=()
for b in "${batch_arr[@]}"; do
    declare -a time_arr=($(ls "$step1outdir"/"$b/" -I *mask.tif))
    for t in "${time_arr[@]}"; do
        n5=$(realpath "$step1outdir"/"$b"/"$t")
        if [ "$n5" != "$(realpath $fix)" ]; then
            mov_arr+=("$n5")
        fi
    done
done
declare -p mov_arr

# make a function that runs singularity, and takes three inputs: fix, mov, output
do_bigstream() {
    fix=$1
    mov=$2
    out=$3

    # get path of mask.tif from fix/mov path
    fix_mask="$(dirname $fix)/$(basename $fix)_mask.tif"
    mov_mask="$(dirname $mov)/$(basename $mov)_mask.tif"

    singularity run \
            --env TINI_SUBREAPER=true \
            -B "$fix":"$fix" \
            -B "$mov":"$mov" \
            -B "$out":"$out" \
            -B "$fix_mask":"$fix_mask" \
            -B "$mov_mask":"$mov_mask" \
            ./bigstream-py-0.0.10.sif \
            /entrypoint.sh bigstream_in_memory \
            -f "$fix" \
            -m "$mov" \
            --fix_mask "$fix_mask" \
            --mov_mask "$mov_mask" \
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
            --def_cps 130 \
            $DISTRIBUTE \
            $BLOCKSIZE \
            $WORKERS \
            $MEMORYLIMIT \
            $ZARR

}
export -f do_bigstream

############# fix N5 to tiff ##################
singularity run \
        --env TINI_SUBREAPER=true \
        -B "$fix":"$fix" \
        -B "$step2outdir":"$step2outdir" \
        ./bigstream-py-0.0.10.sif \
        /entrypoint.sh fix_n5tiff \
        -f "$fix" \
        -o "$step2outdir" \
        -s s4

############ parallel registration over mov_arr ###############
# fix and output directory doesn't change #
parallel --jobs=4 --verbose do_bigstream ::: "$fix" ::: ${mov_arr[@]} ::: "$step2outdir"