#!/bin/bash

usage() {
	echo "Usage: cellpose.sh [OPTION]... [FILE]"
	echo "Run Cellpose"
	echo
	echo "Options:"
	echo "  -i, --input		path to an input n5 directory or tiff image"
	echo "  -o, --output    	path to an output tiff image"
	echo "  -c, --channel		target channel of an input n5 dataset"
	echo "  -s, --scale		target scale level of an input n5 dataset"
    echo "  -m, --minseg    	minimum size of segement"
    echo "  -d, --diameter    	diameter of segment (if it is 0 or null, cellpose will use a diameter in a model)"
    echo "  --model    	        path to a cellpose model (xyz)"
	echo "  --model_xy    	        path to a cellpose model (xy)"
    echo "  --model_yz    	        path to a cellpose model (yz)"
	echo "  -a, --anisotropy		optional rescaling factor"
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
			image_path="$2"
			shift 2
			;;
		'-o'|'--output' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			out="$2"
			shift 2
			;;
		'-c'|'--channel' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			ch="$2"
			shift 2
			;;
		'-s'|'--scale' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			scale="$2"
			shift 2
			;;
                '-m'|'--minseg' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			min_segsize="--min $2"
			shift 2
			;;
                '-d'|'--diameter' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			diameter="--diameter $2"
			shift 2
			;;
                '--model' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			model_path="--model $2"
			shift 2
			;;
                '--model_xy' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			model_path_xy="--model_xy $2"
			shift 2
			;;
                '--model_yz' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			model_path_yz="--model_yz $2"
			shift 2
			;;
		'-a'|'--anisotropy' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			anisotropy="--anisotropy $2"
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

SIFFILE="cellpose-cuda-liu-0.0.5.sif"
if [ ! -f "$SIFFILE" ]; then
    singularity build "$SIFFILE" docker://ghcr.io/janeliascicomp/cellpose-cuda-liu:0.0.5
fi

echo "$image_path"
echo "$out"

parent_indir=$(dirname "$image_path")
parent_outdir=$(dirname "$out")
mkdir -p "$parent_outdir"


echo singularity run \
        --env TINI_SUBREAPER=true \
        -B "$parent_indir":"$parent_indir" \
        -B "$parent_outdir":"$parent_outdir" \
        --nv \
        ./cellpose-cuda-liu-0.0.5.sif \
        /entrypoint.sh segmentation \
        -i $image_path \
        -o $out \
        -n $ch/$scale \
        $min_segsize \
        $diameter \
        $model_path \
        $model_path_xy \
        $model_path_yz \
		$anisotropy

singularity run \
        --env TINI_SUBREAPER=true \
        -B "$parent_indir":"$parent_indir" \
        -B "$parent_outdir":"$parent_outdir" \
        --nv \
        ./cellpose-cuda-liu-0.0.5.sif \
        /entrypoint.sh segmentation \
        -i $image_path \
        -o $out \
        -n $ch/$scale \
        $min_segsize \
        $diameter \
        $model_path \
        $model_path_xy \
        $model_path_yz \
		$anisotropy \
        --verbose
