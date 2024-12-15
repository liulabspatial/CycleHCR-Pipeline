
# list of inputs
# step1dir
# step2dir
# step3dir
# rsfish param

# loop through batch, loop through time, save as n5_arr

step1dir=/home/liulab/labdata/Jun_test/step1_point0_3_subset/
step2dir=/home/liulab/labdata/Jun_test/step2_point0_3_subset2/
step3dir=/home/liulab/labdata/Jun_test/step3_point0_3_subset3/
dapi=c3
rsparam="--rsfish_gb_per_core 8 --rsfish_min 50 --rsfish_max 300 --rsfish_anisotropy 1.1 --rsfish_sigma 1.5 --rsfish_threshold 0.007"



declare -a batch_arr=($(ls $step1dir))
declare -a n5_arr=()
for b in "${batch_arr[@]}"; do
    declare -a time_arr=($(ls "$step1dir"/"$b/" -I *mask.tif -I *.checkpoint))
    for t in "${time_arr[@]}"; do
        n5=$(realpath "$step1dir"/"$b"/"$t")
        n5_arr+=("$n5")
    done
done
declare -p n5_arr

do_warp_spots() {
	local n5=$(realpath $1)
	local transformdir=$(realpath $2)/transform
	local spotsdir=$(realpath $3)/spots
	local warpdir=$(realpath $3)/spots_registered
	local dapi=$4
	local rsparam=$5
#	echo "$n5"
#	echo "$transformdir"
#	echo "$spotsdir"
#	echo "$warpdir"
#	echo "\"$rsparam\""

	/home/liulab/labdata/nf/RSFISH-WarpSpots/rs_warp.sh \
		-i "$n5" \
		-o "$warpdir" \
		-r "$spotsdir" \
		-x "$transformdir" \
		-w 10 -d "$dapi" -s s0 \
		-- "$rsparam"

}

export -f do_warp_spots

for n in "${n5_arr[@]}"; do
	do_warp_spots "$n" "$step2dir" "$step3dir" "$dapi" "$rsparam"
done


