

#Options:
#  -i, --input           path to an input n5 directory or tiff image
#  -o, --output          path to an output tiff image
#  -c, --channel         target channel of an input n5 dataset
#  -s, --scale           target scale level of an input n5 dataset
#  -m, --minseg          minimum size of segement
#  -d, --diameter        diameter of segment (if it is 0 or null, cellpose will use a diameter in a model)
#  --model               path to a cellpose model (xyz)
#  --model_xy            path to a cellpose model (xy)
#  --model_yz            path to a cellpose model (yz)
#  -h, --help            display this help and exit

/home/liulab/labdata/scripts/cellpose.sh \
        -i /home/liulab/labdata/Jun_test/step1_multiTiles_new1/b0/t0 \
        -o /home/liulab/labdata/Jun_test/step4_multiTiles_new1/seg_b0_t0_c3_s2.tif \
        -c c3 -s s2 -m 400 \
        --model_xy /home/liulab/labdata/Takashi/Cellpose/CP_20240406_192511_xy27 \
        --model_yz /home/liulab/labdata/Takashi/Cellpose/CP_noxy13
