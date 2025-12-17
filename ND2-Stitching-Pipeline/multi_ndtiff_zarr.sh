#!/bin/bash

usage() {
	echo "Usage: multi_ndtiff_zarr.sh [OPTION]... [FILE]"
	echo "ND2/Multi-NDTIFF Stitching Pipeline"
	echo
	echo "Options:"
	echo "  -i, --input		    path to an input directory"
	echo "  -o, --outdir    	path to an output directory"
	echo "  -d, --dapi		    channel id of a dapi channel."
    echo "  -t, --thread    	number of threads for non-spark processes"
    echo "  -c, --core    	    number of cores per worker for spark processes"
	echo "  -c2, --core2    	number of cores per worker for spark fusion processes"
	echo "  -x, --crop    	    cropping percentage (top, bottom, left, right)"
	echo "  --oneTileWins		use the one-tile-wins strategy for stitching"
	echo "  --skipDeform		skip affine deformation on stitching"
	echo "  --padding			target resolution level for padding"
	echo "  --mask				target resolution level for padding mask"
    echo "  -r, --resume    	resume a workflow execution"
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
			INPUTDIR="$2"
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
		'-d'|'--dapi' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			DAPI="$2"
			shift 2
			;;
        '-t'|'--thread' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			CONV_THREAD_NUM="--n-workers $2"
            THREADNUM="--cpus $2"
			shift 2
			;;
        '-c'|'--core' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			CORENUM="--spark_worker_cores $2"
			MFCORENUM="--worker_cores $2"
			RSCORENUM="--rsfish_worker_cores $2"
			shift 2
			;;
		'-c2'|'--core2' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			CORENUM2="--spark_worker_cores_for_fusion $2"
			shift 2
			;;
		'-x'|'--crop' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			CROP="--crop $2"
			shift 2
			;;
		'--oneTileWins' )
			ONETILEWINS="--oneTileWins"
			shift 1
			;;
		'--padding' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			PADDINGLV="--padding_scale $2"
			shift 2
			;;
		'--mask' )
			if [[ -z "$2" ]] || [[ "$2" =~ ^-+ ]]; then
				echo "$PROGNAME: option requires an argument -- $1" 1>&2
				exit 1
			fi
			MASKLV="--mask_scale $2"
			shift 2
			;;
		'--skipDeform' )
			SKIPDEFORM="--skipDeform"
			shift 1
			;;
        '-r'|'--resume' )
			RESUME="-resume"
			shift 1
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

if [ ! -d "$OUTDIR" ]; then
    mkdir -p "$OUTDIR"
    echo "Directory created: $OUTDIR"
else
    echo "Directory already exists: $OUTDIR"
fi

echo "extra param: $param"

singularity exec \
            --env TINI_SUBREAPER=true \
            -B "$INPUTDIR":"$INPUTDIR" \
            -B "/tmp":"/tmp" \
            -B "$OUTDIR":"$OUTDIR" \
            -B "$SCRIPTPATH":"$SCRIPTPATH" \
            ./ghcr.io-janeliascicomp-nd2-to-n5-py-0.0.24.img \
            /entrypoint.sh ndtiff2tiff_all \
            -i "$INPUTDIR" \
            -o "$OUTDIR/tmp" \
            -c "$OUTDIR/tmp/list.csv" \
            --n-workers 10


RAND=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 13;)

NXFTMPDIR="/tmp/$USER/$RAND/nextflow_temp"
if [ ! -d "$NXFTMPDIR" ]; then
    mkdir -p "$NXFTMPDIR"
    echo "Directory created: $NXFTMPDIR"
else
    echo "Directory already exists: $NXFTMPDIR"
fi

export TMPDIR="$NXFTMPDIR"
export NXF_TEMP="$NXFTMPDIR"
export PATH="$SCRIPTPATH:$PATH"
if [ -d "$SCRIPTPATH/../tools/jdk-17" ]; then
    export NXF_JAVA_HOME="$SCRIPTPATH/../tools/jdk-17"
fi

ulimit -n 65536

# Read CSV file and process each XML file
if [ -f "$OUTDIR/tmp/list.csv" ]; then
    echo "Processing XML files from CSV: $OUTDIR/tmp/list.csv"
    
    while IFS= read -r xml_path; do
        # Skip empty lines
        if [ -z "$xml_path" ]; then
            continue
        fi
        
        echo "Processing XML file: $xml_path"
        
        # Extract the relative path from $OUTDIR/tmp to the XML file's directory
        # Example: if xml_path is /path/to/outdir/tmp/p1/t0/bdv_metadata_p1_t0.xml
        # and OUTDIR is /path/to/outdir, then we want the relative path p1/t0
        xml_dir=$(dirname "$xml_path")
        relative_path=$(realpath --relative-to="$OUTDIR/tmp" "$xml_dir")
        
        # Create OUTN5DIR by appending the relative path to OUTDIR
        OUTN5DIR="$OUTDIR/$relative_path"
        
        echo "Output directory: $OUTN5DIR"
        
        # Create output directory if it doesn't exist
        if [ ! -d "$OUTN5DIR" ]; then
            mkdir -p "$OUTN5DIR"
            echo "Created output directory: $OUTN5DIR"
        fi
        
        # Change to output directory
        cd "$OUTN5DIR"
        
        # Execute the nextflow command
        echo "Executing nextflow command for: $xml_path"
        echo "Command: nextflow run $SCRIPTPATH/nd2n5/bdv_zarr.nf -c $SCRIPTPATH/nextflow.config -profile standard $RESUME --runtime_opts \"--env TMPDIR=$NXFTMPDIR -B $OUTDIR/tmp -B /tmp -B $OUTN5DIR\" --dapi_channel \"$DAPI\" --inputPath \"$xml_path\" --outputPath \"$OUTN5DIR\" $ONETILEWINS $SKIPDEFORM $THREADNUM $CORENUM $CORENUM2 $CROP $param"
        nextflow run "$SCRIPTPATH/nd2n5/bdv_zarr.nf" \
            -c "$SCRIPTPATH/nextflow.config" \
            -profile standard $RESUME \
            --runtime_opts "--env TMPDIR=$NXFTMPDIR -B $OUTDIR -B /tmp -B $OUTN5DIR" \
            --dapi_channel "$DAPI" \
            --inputPath "$xml_path" \
            --outputPath "$OUTN5DIR" \
            $ONETILEWINS $SKIPDEFORM $THREADNUM $CORENUM $CORENUM2 $CROP $PADDINGLV $MASKLV $param
        
        sleep 5

        # Remove logs
        rm -rf "$OUTN5DIR/spark"
        rm -rf "$OUTN5DIR/work"
        rm -rf "$OUTN5DIR/.nextflow"
        rm -rf "$OUTN5DIR/.nextflow.log"
        
        # Remove temp files
        rm -rf "$xml_dir"
        
        echo "Completed processing: $xml_path"
        echo "----------------------------------------"
        
    done < "$OUTDIR/tmp/list.csv"
    
    rm -rf "$OUTDIR/tmp"
    
    echo "All XML files processed successfully."
else
    echo "Error: CSV file not found: $OUTDIR/tmp/list.csv"
    exit 1
fi

