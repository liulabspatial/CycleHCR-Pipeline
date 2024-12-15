
include { getOptions; getParent } from '../utils' 

process STITCHING_PREPARE {
    tag "${meta.id}"
    label 'process_single'

    input:
    tuple val(meta), path(files)

    output:
    tuple val(meta), path(files)

    script:
    """
    umask 0002
    mkdir -p ${meta.spark_work_dir}
    """
}

process remove_dir {
    scratch true

    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "16 GB" }
    cpus { 2 }

    input:
    val(tar)
    val(control_1) 

    output:
    val "${tar}"
    
    script:
    """
    rm -rf $tar
    """
}

process create_checkpoint {
    scratch true

    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "1 GB" }
    cpus { 1 }

    input:
    val(tar)
    val(control_1) 

    output:
    val "${tar}"
    
    script:
    file = new File("${tar}")
    file.createNewFile() 
    """
    echo creating checkpoint files
    """
}