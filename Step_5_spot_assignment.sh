
spots_directory="/home/liulab/labdata/Jun_test/forTakashi_spotcell/spots_registered/"

files=($spots_directory/*spot*.csv)

if [ ${#files[@]} -gt 0 ]; then
    
    # Join the array elements into a comma-separated string
    file_list=$(IFS=, ; echo "${files[*]}")

else
    echo "no matching files found"
fi
# -s is segmentation image
# -v -v is relative voxel ratio, value multiplied to spots before assigning to segmentation file
    # if image is upscaled in z by 2, the spots need to be upscaled by 2 in z, so -v 1,1,2
# -o gene-by-cell matrix
# -p percent of spots assigned

/home/liulab/labdata/Takashi/Docker_with_bigstream_py/assignment.sh \
    -s /home/liulab/labdata/Jun_test/spot_assign_test/fix_b1_t5_c3_s2_iso3_cellpose_seg_min1000.tiff \
    -v 1.0,1.0,1.4615 \
    -o test_4.csv \
    -p test_4_percent.csv \
    -i $file_list

