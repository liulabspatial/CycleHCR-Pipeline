#!/usr/bin/env nextflow

nextflow.enable.dsl=2

params.input_dirs = ''

params.outputPath = ''

// config for running single process
params.cpus = 48
params.mem_gb = params.cpus * 10
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

params.input_images = ''
params.spot_extraction_output_dirs = ''
params.spot_channels = ''
params.bleedthrough_channels = ''


include { getOptions; getParent } from '../utils' 


// include {
//     default_spark_params;
// } from '../external-modules/spark/lib/param_utils'

include {
    default_mf_params;
    set_derived_defaults;
    get_value_or_default;
    get_list_or_default;
    airlocalize_container_param;
} from '../param_utils'

include { SPARK_START } from '../subworkflows/janelia/spark_start/main.nf'
include { SPARK_STOP  } from '../subworkflows/janelia/spark_stop/main.nf'
include { RS_FISH } from '../modules/janelia/rs_fish/main.nf'

// app parameters
final_params = set_derived_defaults(default_mf_params() + params, params)

bleedthrough_channels = final_params.bleed_channel?.split(',') as List
channels = get_list_or_default(final_params, 'channels',[]) as List
spot_channels = channels - [final_params.dapi_channel]
input_dirs = final_params.input_dirs?.split(',') as List
rsfish_output_dirs = final_params.rsfish_output_dirs?.split(',') as List
output_dirs = final_params.output_dirs?.split(',') as List

process bigstream_warp {
    container 'ghcr.io/janeliascicomp/bigstream-py:0.0.16'
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
    /entrypoint.sh bigstream_warpspots_in_memory -z $n5 -td $transform_dir -sd $spots_dir -o $out_dir $force --iterations ${params.iterations} --downsample_field_xy ${params.downsample_field_xy}
    """
}

process create_checkpoint {
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
        fpath = meta.checkpoint_base + c + "_s" + meta.rs_scale + ".checkpoint"
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
    spotDir = file(rsfish_output_dirs[0])
    spotResult = spotDir.mkdirs()
    println spotResult ? "Created $spotDir" : "Cannot create directory: $spotDir"

    base_name = params.base_name
    if (params.base_name.isEmpty()) {
        base_name = file(input_dirs[0]).parent.baseName + "_" + file(input_dirs[0]).baseName
        println base_name
    }

    checkpoint_base = rsfish_output_dirs[0] + "/spots_" + base_name + "_"
    checkpoint_path = checkpoint_base + spot_channels[0] + "_s" + final_params.spot_extraction_scale + ".checkpoint"

    input_dirs_ch = Channel.fromList(input_dirs)
    rsfish_output_dirs_ch = Channel.fromList(rsfish_output_dirs)

    if (!file(checkpoint_path).exists() || params.force) {
        Channel.fromPath(rsfish_output_dirs[0]).first().map { it.mkdirs() }

        // Find channel folders (c0, c1, c2, ...) in input_dirs[0]
        ch_input_images = Channel.fromPath("${input_dirs[0]}/c*", type: 'dir')
            .filter { channel_folder ->
                channel_folder.name != params.dapi_channel
            }
            .map { channel_folder ->
                def channel_name = channel_folder.name
                def meta = [
                    id: channel_name,
                    input_file: channel_folder.name,
                    channel_name: channel_name
                ]
                [ meta, channel_folder ]
            }

        // Prepare data paths for Spark (needed for mounting in containers)
        ch_meta_with_data = ch_input_images
            .map { meta, input_image ->
                def data_paths = [ input_image ]
                [ meta, data_paths ]
            }

        // Spark configuration
        def spark_config = [
            'spark.serializer': 'org.apache.spark.serializer.KryoSerializer',
        ]

        // Calculate workers per channel: rsfish_workers / number of channels, floor, min 1
        // Count channel folders directly from filesystem (excluding dapi_channel)
        def input_dir_path = final_params.input_dirs.split(',')[0]
        def dapi_ch = params.dapi_channel
        def channel_folders = file(input_dir_path).listFiles().findAll { f ->
            f.isDirectory() && f.name.startsWith('c') && f.name != dapi_ch
        }
        def num_channels = channel_folders.size()
        def workers_per_channel = Math.max(1, (int) Math.floor(final_params.rsfish_workers / num_channels))
        log.info "Number of channels: ${num_channels}, workers per channel: ${workers_per_channel}"

        // Start Spark cluster
        SPARK_START(
            ch_meta_with_data,
            spark_config,
            true,
            "${workDir}/spark/${workflow.sessionId}",
            workers_per_channel,   // spark workers
            workers_per_channel,   // required workers
            final_params.rsfish_worker_cores,   // worker cpus
            final_params.rsfish_gb_per_core,   // gb_per_cpu
            final_params.rsfish_driver_cores,   // driver cpus
            final_params.rsfish_driver_memory,   // driver memory in GB
        )

        // Prepare RS_FISH inputs
        ch_rs_fish_inputs = ch_input_images
            .join(SPARK_START.out.spark_context, by: 0)
            .map { meta, input_image, spark ->
                def spots_output_dir = file("${rsfish_output_dirs[0]}")
                def output_filename = "spots_${base_name}_${meta.channel_name}_s${final_params.spot_extraction_scale}.csv"
                [
                    meta,
                    input_image,
                    "/${final_params.spot_extraction_scale}",
                    rsfish_output_dirs[0],
                    output_filename,
                    "--storage ZARR --minIntensity=${final_params.rsfish_min} --maxIntensity=${final_params.rsfish_max} --anisotropy=${final_params.rsfish_anisotropy} --sigma=${final_params.rsfish_sigma} --threshold=${final_params.rsfish_threshold}",
                    spark
                ]
            }

        // Run RS_FISH
        RS_FISH(ch_rs_fish_inputs)

        stop_param = RS_FISH.out.params.map { 
            def (meta, INPUT_IMG, input_dataset, spots_output_dir, spots_result_name, spark) = it
            [ meta, spark ]
        }
        
        // Stop Spark cluster
        SPARK_STOP(
            stop_param,
            true
        )

        // Prepare create_checkpoint inputs after SPARK_STOP completion
        ch_checkpoint_inputs = SPARK_STOP.out.done
            .map { meta, spark ->
                [ meta.id, meta ]
            }
            .join(
                ch_input_images.map { meta, input_image ->
                    [ meta.id, input_image ]
                }
            )
            .map { id, meta, input_image ->
                [
                    meta + [
                        checkpoint_base: checkpoint_base,
                        spot_channels: spot_channels,
                        rs_scale: final_params.spot_extraction_scale
                    ],
                    input_image
                ]
            }

        // Run create_checkpoint after SPARK_STOP
        create_checkpoint(ch_checkpoint_inputs, SPARK_STOP.out.done)

        // Wait for all create_checkpoint to complete, then run bigstream_warp once
        all_checkpoints_done = create_checkpoint.out.acquisitions.collect()

        // Prepare bigstream_warp input after ALL create_checkpoint completions
        ch_bigstream_inputs = all_checkpoints_done
            .map { items ->
                def input_image = file(input_dirs[0])
                def meta = [
                    id: input_image.baseName,
                    bg_n5: input_image,
                    bw_transform_dir: final_params.transform_dir,
                    bw_spots_dir: rsfish_output_dirs[0],
                    bw_out_dir: output_dirs[0]
                ]
                [ meta, input_image ]
            }

        // Run bigstream_warp after ALL create_checkpoint are complete
        bigstream_warp(ch_bigstream_inputs)

        // Emit results
        emit:
        rs_fish_results = RS_FISH.out.csv
        rs_fish_versions = RS_FISH.out.versions
        checkpoint_results = create_checkpoint.out.acquisitions
        bigstream_results = bigstream_warp.out.acquisitions
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
