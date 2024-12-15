#!/bin/bash
usage() {
	echo "Usage: rs_warp.sh [OPTION]... [FILE]"
	echo "RSFISH and Warping Spots Pipeline"
	echo
	echo "Options:"
	echo "  -i, --input		    path to an input n5 directory"
	echo "  -x, --transform		path to a transform directory"
	echo "  -o, --outdir    	path to an output directory"
	echo "  -r, --rsoutdir    	path to a rsfish output directory"
	echo "  -n, --basename		base name of an output data."
	echo "  -d, --dapi		    channel id of a dapi channel."
	echo "  -s, --scale		    target scale level for rsfish."
    echo "  -t, --thread    	number of threads for bigstream"
    echo "  -w, --worker    	number of workers for rsfish"
    echo "  -c, --core    	    number of cores per worker for rsfish"
	echo "  -p, --params    	other parameters"
    echo "  -f, --force         overwrite existing results"
	echo "  -h, --help		    display this help and exit"
	exit 1
}

RSWORKERNUM="--rsfish_workers 8"
RSCORENUM="--rsfish_worker_cores 10"
THREADNUM="--cpus 48"
RSSCALE="--spot_extraction_scale s0"

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
			INPUTN5="$2"
			shift 2
			;;
		'-x'|'--transform' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			TRANSFORMDIR="$2"
			shift 2
			;;
		'-o'|'--outdir' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			OUTDIR="$2"
			shift 2
			;;
		'-r'|'--rsoutdir' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			RSOUTDIR="$2"
			shift 2
			;;
		'-d'|'--dapi' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			DAPI="$2"
			shift 2
			;;
		'-n'|'--basename' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			BASENAME="--base_name $2"
			shift 2
			;;
		'-s'|'--scale' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			RSSCALE="--spot_extraction_scale $2"
			shift 2
			;;
        '-t'|'--thread' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			THREADNUM="--cpus $2"
			shift 2
			;;
        '-w'|'--worker' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			RSWORKERNUM="--rsfish_workers $2"
			shift 2
			;;
        '-c'|'--core' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			RSCORENUM="--rsfish_worker_cores $2"
			shift 2
			;;
		'-f'|'--force' )
			FORCE="--force"
			shift 1
			;;
		'-p'|'--params' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			PARAMS="$2"
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

INPUTDIR=$(dirname "$INPUTN5")

RAND=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 13;)

NXFTMPDIR="/tmp/$USER/$RAND/nextflow_temp"
if [ ! -d "$NXFTMPDIR" ]; then
    mkdir -p "$NXFTMPDIR"
    echo "Directory created: $NXFTMPDIR"
else
    echo "Directory already exists: $NXFTMPDIR"
fi

if [ ! -d "$OUTDIR" ]; then
    mkdir -p "$OUTDIR"
    echo "Directory created: $OUTDIR"
else
    echo "Directory already exists: $OUTDIR"
fi

BASEDIR=$(dirname "$0")

export TMPDIR="$NXFTMPDIR"
export NXF_TEMP="$NXFTMPDIR"
cd $BASEDIR

CH_NAMES=$(find "$INPUTN5" -maxdepth 1 -mindepth 1 -type d -print | xargs -n 1 basename | tr '\n' ',' | sed 's/,$//')

echo nextflow run $BASEDIR/workflows/main.nf -c $BASEDIR/nextflow.config --runtime_opts \"-B /home \" $FORCE $THREADNUM $RSWORKERNUM $RSCORENUM $RSSCALE $BASENAME --input_dirs $INPUTN5 --transform_dir $TRANSFORMDIR --output_dirs $OUTDIR --rsfish_output_dirs $RSOUTDIR --dapi_channel $DAPI --channels $CH_NAMES $param

nextflow run $BASEDIR/workflows/main.nf -c $BASEDIR/nextflow.config --runtime_opts "-B /home -B $BASEDIR -B /tmp" $FORCE $THREADNUM $RSWORKERNUM $RSCORENUM $RSSCALE $BASENAME --input_dirs $INPUTN5 --transform_dir $TRANSFORMDIR --output_dirs $OUTDIR --rsfish_output_dirs $RSOUTDIR --dapi_channel $DAPI --channels $CH_NAMES $param

rm -rf "$BASEDIR/spark"
rm -rf "$BASEDIR/work"
rm -rf "$BASEDIR/.nextflow"