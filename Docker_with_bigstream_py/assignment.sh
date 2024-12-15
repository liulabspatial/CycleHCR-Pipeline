#!/bin/bash

usage() {
	echo "Usage: assignment.sh [OPTION]... [FILE]"
	echo "spot-to-cell assignment"
	echo
	echo "Options:"
	echo "  -i, --input		path to an input csv"
	echo "  -o, --output    path to an output file"
	echo "  -p, --output2   path to an output file 2 (percentage of assigned spots)"
	echo "  -v, --voxel     voxel size"
	echo "  -s, --seg		path to a segmented image"
	echo "  -h, --help		display this help and exit"
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
			input="$2"
			shift 2
			;;
		'-o'|'--output' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			output="$2"
			shift 2
			;;
		'-p'|'--output2' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			output2="$2"
			shift 2
			;;
		'-v'|'--voxel' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			voxel="$2"
			shift 2
			;;
		'-s'|'--seg' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			seg="$2"
			shift 2
			;;
		'--'|'-' )
			shift 1
			param+=( "$@" )
			break
			;;
		-*)
			echo "$PROGNAME: illegal option -- '$(echo $1 | sed 's/^-*//')'" 1>&2
			exit 1
			;;
		*)
			if [[ ! -z "$1" ]] && [[ ! "$1" =~ ^-+ ]]; then
				#param=( ${param[@]} "$1" )
				param+=( "$1" )
				shift 1
			fi
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

echo "$input"
echo "$output"
IFS=',' read -r -a input_array <<< "$input"
real_input_path=$(realpath "${input_array[0]}")
parent_indir=$(dirname "$real_input_path")
real_output_path=$(realpath "$output")
parent_outdir=$(dirname "$real_output_path")
mkdir -p "$parent_outdir"

echo singularity run \
        --env TINI_SUBREAPER=true \
        -B "$parent_indir":"$parent_indir" \
        -B "$parent_outdir":"$parent_outdir" \
        ./bigstream-py-0.0.10.sif \
        /entrypoint.sh spot_assignment \
        -i $input \
        -o $output \
        -s $seg \
		-p $output2 \
		-v $voxel

singularity run \
        --env TINI_SUBREAPER=true \
        -B "$parent_indir":"$parent_indir" \
        -B "$parent_outdir":"$parent_outdir" \
        ./bigstream-py-0.0.10.sif \
        /entrypoint.sh spot_assignment \
        -i $input \
        -o $output \
        -s $seg \
		-p $output2 \
		-v $voxel