
inputpath="/home/liulab/labdata/pipeline_test/step1_output/"
outputpath="/home/liulab/labdata/pipeline_test/step2_output/"
fix="b0/t2"
dapi="c3"
res="s0"

/home/liulab/labdata/scripts/bigstream_Jun.sh \
	-i "$inputpath" \
	-o "$outputpath" \
	-f "$fix" \
	-d "$dapi" \
	-s "$res"
