
include { rsfish } from './rs_fish'

workflow spot_extraction {
    take:
    input_images
    spot_extraction_output_dirs
    spot_channels
    base_name
    bleedthrough_channels

    main:

    rsfish(
        input_images,
        spot_extraction_output_dirs,
        spot_channels,
        params.spot_extraction_scale,
        params.dapi_channel,
        base_name,
        bleedthrough_channels
    ) // [ input_image, ch, scale, spots_file ]
    rsfish.out.postprocess_spots.subscribe { println "RS-FISH results: $it" }

    emit:
    rsfish.out.postprocess_spots
}