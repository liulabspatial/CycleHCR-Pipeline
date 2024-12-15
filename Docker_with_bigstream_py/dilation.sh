#!/bin/bash

usage() {
	echo "Usage: dilation.sh [OPTION]... [FILE]"
	echo "dilate or elode segments"
	echo
	echo "Options:"
	echo "  -i, --input		path to an input csv"
	echo "  -o, --output    path to an output file"
	echo "  -t, --thread	number of threads"
	echo "  -r, --radius	radius of dilation (r > 0) or erosion (r < 0)"
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
		'-t'|'--thread' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			thread="$2"
			shift 2
			;;
		'-r'|'--radius' )
			radius="$2"
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

echo "$input"
echo "$output"

parent_indir=$(dirname "$input")
parent_outdir=$(dirname "$output")
mkdir -p "$parent_outdir"

echo singularity run \
        --env TINI_SUBREAPER=true \
        -B "$parent_indir":"$parent_indir" \
        -B "$parent_outdir":"$parent_outdir" \
        ./bigstream-py-0.0.10.sif \
        /entrypoint.sh dilate_segments \
        -i $input \
        -o $output \
        -t $thread \
		-r $radius

singularity run \
        --env TINI_SUBREAPER=true \
        -B "$parent_indir":"$parent_indir" \
        -B "$parent_outdir":"$parent_outdir" \
        ./bigstream-py-0.0.10.sif \
        /entrypoint.sh dilate_segments \
        -i $input \
		-o $output \
        -t $thread \
		-r $radius