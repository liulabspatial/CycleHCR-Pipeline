#!/usr/bin/env nextflow

nextflow.enable.dsl=2

params.input_dirs = ''

params.outputPath = ''

// config for running single process
params.cpus = 48
params.mem_gb = params.cpus * 14
//params.mem_gb = "80"
//params.cpus = 8

params.rsfish_output_dirs = ''
params.channels = ''
params.scale = ''
params.dapi_channel = ''

params.base_name = ''
params.transform_dir = ''
params.output_dirs = ''

params.force = false

params.downsample_field_xy = 4
params.iterations = 10
params.sqrt_order = 2
params.sqrt_iterations = 5


include { getOptions; getParent } from '../utils' 


include {
    default_spark_params;
} from '../external-modules/spark/lib/param_utils'

include {
    default_mf_params;
    set_derived_defaults;
    get_value_or_default;
    get_list_or_default;
    airlocalize_container_param;
} from '../param_utils'

// app parameters
final_params = set_derived_defaults(default_spark_params() + default_mf_params() + params, params)

bleedthrough_channels = final_params.bleed_channel?.split(',') as List
channels = get_list_or_default(final_params, 'channels',[]) as List
spot_channels = channels - [final_params.dapi_channel]
input_dirs = final_params.input_dirs?.split(',') as List
rsfish_output_dirs = final_params.rsfish_output_dirs?.split(',') as List
output_dirs = final_params.output_dirs?.split(',') as List

include {
    spot_extraction;
} from './spot_extraction' addParams(final_params)

process bigstream_warp {
    scratch true

    container 'ghcr.io/janeliascicomp/bigstream-py:0.0.8'
    containerOptions { getOptions([params.input_dirs[0], params.output_dirs[0]]) }

    memory { "${params.mem_gb} GB" }
    cpus { params.cpus }

    input:
    tuple val(meta), path(files)

    output:
    tuple val(meta), path(files), emit: acquisitions
    
    script:
    n5 = meta.bg_n5
    transform_dir = meta.bw_transform_dir
    spots_dir = meta.bw_spots_dir
    out_dir = meta.bw_out_dir
    force = params.force ? "--force" : ""
    """
    /entrypoint.sh bigstream_warpspots_in_memory -n $n5 -td $transform_dir -sd $spots_dir -o $out_dir $force --iterations ${params.iterations} --sqrt_order ${params.sqrt_order} --sqrt_iterations ${params.sqrt_iterations} --downsample_field_xy ${params.downsample_field_xy}
    """
}

process create_checkpoint {
    scratch true

    containerOptions { getOptions([params.input_dirs[0], params.rsfish_output_dirs[0]]) }

    memory { "1 GB" }
    cpus { 1 }

    input:
    tuple val(meta), path(files)
    val(control_1)

    output:
    tuple val(meta), path(files), emit: acquisitions
    
    script:
    checkpoint = meta.checkpoint
    for( c in meta.spot_channels ) {
        fpath = meta.checkpoint_base + c + "_" + meta.rs_scale + ".checkpoint"
        file = new File(fpath)
        file.createNewFile() 
    }
    """
    echo creating checkpoint files
    """
}

workflow {

    myDir = file(rsfish_output_dirs[0])
    result = myDir.mkdirs()
    println result ? "Created $myDir" : "Cannot create directory: $myDir"
    myDir2 = file(output_dirs[0])
    result2 = myDir2.mkdirs()
    println result2 ? "Created $myDir2" : "Cannot create directory: $myDir2"

    base_name = params.base_name
    if (params.base_name.isEmpty()) {
        base_name = file(input_dirs[0]).parent.baseName + "_" + file(input_dirs[0]).baseName
        println base_name
    }

    checkpoint_base = rsfish_output_dirs[0] + "/spots_" + base_name + "_"
    checkpoint_path = checkpoint_base + spot_channels[0] + "_" + final_params.spot_extraction_scale + ".checkpoint"

    input_dirs_ch = Channel.fromList(input_dirs)
    rsfish_output_dirs_ch = Channel.fromList(rsfish_output_dirs)

    if (!file(checkpoint_path).exists() || params.force) {
        spot_extraction(
            input_dirs_ch,
            rsfish_output_dirs_ch,
            spot_channels,
            base_name,
            bleedthrough_channels
        ) // [ input_image, ch, scale, spots_file ]

        spot_extraction.out.map {
                def xml = it[0]
                meta = [:]
                meta.id = file(it[0]).baseName
                meta.bg_n5 = it[0]
                meta.bw_transform_dir = final_params.transform_dir
                meta.bw_spots_dir = file(it[3]).parent
                meta.bw_out_dir = output_dirs[0]
                meta.checkpoint_base = checkpoint_base
                meta.spot_channels = spot_channels
                meta.rs_scale = final_params.spot_extraction_scale
                [meta, xml]
            }.set { ch_acquisitions }

        create_checkpoint(ch_acquisitions.first(), spot_extraction.out.collect())

        bigstream_warp(create_checkpoint.out.acquisitions)
    }
    else {
        input_image = input_dirs[0]
        meta = [:]
        meta.id = file(input_image).baseName
        meta.bg_n5 = input_image
        meta.bw_transform_dir = final_params.transform_dir
        meta.bw_spots_dir = rsfish_output_dirs[0]
        meta.bw_out_dir = output_dirs[0]
        meta.checkpoint_base = checkpoint_base
        meta.spot_channels = spot_channels
        meta.rs_scale = final_params.spot_extraction_scale
        bigstream_input = Channel.of(tuple(meta, input_image))
        
        bigstream_warp(bigstream_input)
    }
}
