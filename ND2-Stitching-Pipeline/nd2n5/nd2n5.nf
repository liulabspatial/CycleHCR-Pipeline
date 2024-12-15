#!/usr/bin/env nextflow

nextflow.enable.dsl=2

// path to the TIFF series
params.inputPath = ""

// path to the output n5
params.outputPath = ""

params.baseimg = ""

params.bgimg = ""

params.crop = "0,0,0,0"

params.prestitch = false

params.dapi_channel = ""

params.fusionOnly = false

params.oneTileWins = false

// path to the output dataset
params.outputDataset = "/s0"

// chunk size for n5
params.blockSize = "512,512,128"

// config for running single process
params.cpus = 48
params.mem_gb = params.cpus * 14
//params.mem_gb = "80"
//params.cpus = 8

params.spark_local_dir = null
params.spark_cluster = false
params.spark_workers = 4
params.spark_worker_cores = 16
params.spark_gb_per_core = 8//14
params.spark_worker_cores_for_fusion = 16
params.spark_gb_per_core_for_fusion = 8//14
params.spark_driver_cores = 1
params.spark_driver_memory = '12 GB'

include { getOptions; getParent } from '../utils' 

include { SPARK_START         } from '../subworkflows/bits/spark_start/main'
include { SPARK_STOP          } from '../subworkflows/bits/spark_stop/main'

include { SPARK_START as SPARK_START2 } from '../subworkflows/bits/spark_start/main'
include { SPARK_STOP as SPARK_STOP2 } from '../subworkflows/bits/spark_stop/main'

include { SPARK_START as SPARK_START3 } from '../subworkflows/bits/spark_start/main'
include { SPARK_STOP as SPARK_STOP3 } from '../subworkflows/bits/spark_stop/main'

include { SPARK_STOP as SPARK_STOP_SINGLE } from '../subworkflows/bits/spark_stop/main'

include { STITCHING_PREPARE; remove_dir; create_checkpoint } from './reusables'
include { STITCHING_PREPARE as STITCHING_PREPARE2} from './reusables'
include { STITCHING_PREPARE as STITCHING_PREPARE3} from './reusables'
include { remove_dir as remove_dir_single} from './reusables'
include { create_checkpoint as create_checkpoint_single} from './reusables'

process define_dataset {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-fiji:0.0.4'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "4 GB" }
    cpus { 1 }

    input:
    tuple val(infile), val(outfile)

    output:
    val "${outfile}"
    
    script:
    """
    /entrypoint.sh define -i $infile -o $outfile -t 2
    """
}

process fix_n5xml {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-py:0.0.7'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "4 GB" }
    cpus { 1 }

    input:
    tuple val(infile), val(outfile)

    output:
    val "${outfile}"
    
    script:
    """
    /entrypoint.sh fix_n5xml -i $infile -o $outfile
    """
}

process calc_stitching_resume {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-fiji:0.0.4'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "${params.mem_gb} GB" }
    cpus { params.cpus }

    input:
    tuple val(inxml), val(basepath)

    output:
    val(basepath)
    
    script:
    """
    /entrypoint.sh calc_stitch -i $inxml -m ${params.mem_gb}G  > /dev/null 2>&1
    """
}

process calc_stitching {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-fiji:0.0.4'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "${params.mem_gb} GB" }
    cpus { params.cpus }

    input:
    tuple val(meta), path(files), val(spark)
    val(done) 

    output:
    path(files)
    
    script:
    inxml = meta.resave_outxml
    """
    /entrypoint.sh calc_stitch -i $inxml -m ${params.mem_gb}G -t ${params.cpus} -d 8,8,4 -r 0.3  > /dev/null 2>&1
    """
}

process gen_csv {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-py:0.0.7'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "4 GB" }
    cpus { 1 }

    input:
    tuple val(src), val(tar)

    output:
    val "${tar}"
    
    script:
    """
    /entrypoint.sh nd2tiffcsv -i $src -o $tar
    """
}

process split_xml {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-py:0.0.12'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "4 GB" }
    cpus { 1 }

    input:
    tuple val(src), val(tar), val(csv), val(crop)
    val(control_1) 

    output:
    val "${csv}"
    
    script:
    """
    /entrypoint.sh nd2tiffxml -i $src -o $tar -c $csv -x $crop
    """
}

process nd2tiff {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-py:0.0.11'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "16 GB" }
    cpus { 1 }

    input:
    tuple val(src), val(tar), val(bg), val(crop)

    output:
    val("process_complete"), emit: control_1
    
    script:
    """
    /entrypoint.sh nd2tiff -i $src -o $tar -c $crop
    """
}

process padding {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-py:0.0.10'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "${params.mem_gb} GB" }
    cpus { params.cpus }

    input:
    tuple val(meta), path(files), val(spark)
    val(control_1)

    output:
    tuple val(meta), path(files), val(spark), emit: acquisitions
    
    script:
    n5dir = meta.padding_n5dir
    dapi = meta.dapi
    parsed_xml = new XmlSlurper().parse("$n5dir")
    maxChannelId = parsed_xml.'**'.findAll{ it.name() == 'Channel' }.size() - 1
    """
    for i in {0..$maxChannelId}; do
        /entrypoint.sh padding -i $n5dir -c \$i -s "s0" -t ${params.cpus}
    done
    """
}

process padding_single {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-py:0.0.10'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "${params.mem_gb} GB" }
    cpus { params.cpus }

    input:
    tuple val(meta), path(files), val(spark)
    val(control_1) 

    output:
    tuple val(meta), path(files), val(spark), emit: acquisitions
    
    script:
    n5dir = meta.padding_n5dir
    dapi = meta.dapi
    parsed_xml = new XmlSlurper().parse("$n5dir")
    maxChannelId = parsed_xml.'**'.findAll{ it.name() == 'Channel' }.size() - 1
    """
    for i in {0..$maxChannelId}; do
        /entrypoint.sh padding -i $n5dir -c \$i -s "s0" -t ${params.cpus}
    done
    """
}

process padding_mask {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-py:0.0.12'
    containerOptions { getOptions([getParent(params.inputPath), getParent(params.outputPath)]) }

    memory { "${params.mem_gb} GB" }
    cpus { params.cpus }

    input:
    tuple val(n5dir), val(output)

    output:
    val(output), emit: control_1
    
    script:
    """
    /entrypoint.sh padding_mask -i $n5dir -o $output -c ${params.dapi_channel} -s 2 -t ${params.cpus}
    """
}

process padding_mask_single {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-py:0.0.12'
    containerOptions { getOptions([getParent(params.inputPath), getParent(params.outputPath)]) }

    memory { "${params.mem_gb} GB" }
    cpus { params.cpus }

    input:
    tuple val(n5dir), val(output)

    output:
    val(output), emit: control_1
    
    script:
    """
    /entrypoint.sh padding_mask -i $n5dir -o $output -c ${params.dapi_channel} -s 0 -t ${params.cpus}
    """
}

process SPARK_RESAVE {
    scratch true

    tag "${meta.id}"
    container 'ghcr.io/janeliascicomp/bigstitcher-spark:0.0.11'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }
    cpus { spark.driver_cores }
    memory { spark.driver_memory }

    input:
    tuple val(meta), path(xml), val(spark)

    output:
    tuple val(meta), path(xml), val(spark), emit: acquisitions
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    extra_args = task.ext.args ?: ''
    executor_memory = spark.executor_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    driver_memory = spark.driver_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    outdir = meta.outdir
    inxml = meta.resave_inxml
    tmpxml = meta.tmpdir + "/" + meta.id + "_resaved.xml"
    outxml = meta.resave_outxml
    tmpn5dir = meta.tmpdir + "/" + meta.id + "_resaved.n5"
    n5dir = meta.resave_n5dir
/*     """
    /opt/scripts/runapp.sh "$workflow.containerEngine" "$spark.work_dir" "$spark.uri" \
        /app/app.jar net.preibisch.bigstitcher.spark.SparkResaveN5 \
        $spark.parallelism $spark.worker_cores "$executor_memory" $spark.driver_cores "$driver_memory" \
        -x ${inxml} -xo ${tmpxml} -o ${tmpn5dir} --blockSize ${params.blockSize} -ds 1,1,1

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        stitching-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """ */

    """
    /opt/spark/bin/spark-class org.apache.spark.deploy.SparkSubmit \
        --class net.preibisch.bigstitcher.spark.SparkResaveN5 \
        --master local[$spark.worker_cores] \
        --driver-memory 600G \
        --executor-memory 16G \
        /app/app.jar \
        -x ${inxml} -xo ${tmpxml} -o ${tmpn5dir} --blockSize ${params.blockSize} -ds 1,1,1 --retry 10

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        stitching-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """ 
}

process SPARK_RESAVE_SINGLE {
    scratch true

    tag "${meta.id}"
    container 'ghcr.io/janeliascicomp/bigstitcher-spark:0.0.11'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }
    cpus { spark.driver_cores }
    memory { spark.driver_memory }

    input:
    tuple val(meta), path(xml), val(spark)

    output:
    tuple val(meta), path(xml), val(spark), emit: acquisitions
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    extra_args = task.ext.args ?: ''
    executor_memory = spark.executor_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    driver_memory = spark.driver_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    outdir = meta.outdir
    inxml = meta.resave_inxml
    tmpxml = meta.tmpdir + "/" + meta.id + "_resaved.xml"
    outxml = meta.resave_outxml
    tmpn5dir = meta.tmpdir + "/" + meta.id + "_resaved.n5"
    n5dir = meta.resave_n5dir
/*     """
    /opt/scripts/runapp.sh "$workflow.containerEngine" "$spark.work_dir" "$spark.uri" \
        /app/app.jar net.preibisch.bigstitcher.spark.SparkResaveN5 \
        $spark.parallelism $spark.worker_cores "$executor_memory" $spark.driver_cores "$driver_memory" \
        -x ${inxml} -xo ${tmpxml} -o ${tmpn5dir} --blockSize ${params.blockSize} -ds "1,1,1"

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        stitching-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """ */

    """
    /opt/spark/bin/spark-class org.apache.spark.deploy.SparkSubmit \
        --class net.preibisch.bigstitcher.spark.SparkResaveN5 \
        --master local[$spark.worker_cores] \
        --driver-memory 600G \
        --executor-memory 16G \
        /app/app.jar \
        -x ${inxml} -xo ${tmpxml} -o ${tmpn5dir} --blockSize ${params.blockSize} -ds 1,1,1 --retry 10

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        stitching-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """ 
}

process SPARK_DOWNSAMPLE {
    scratch true

    tag "${meta.id}"
    container 'ghcr.io/janeliascicomp/bigstitcher-spark:0.0.11'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }
    cpus { spark.driver_cores }
    memory { spark.driver_memory }

    input:
    tuple val(meta), path(xml), val(spark)

    output:
    tuple val(meta), path(xml), val(spark), emit: acquisitions
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    extra_args = task.ext.args ?: ''
    executor_memory = spark.executor_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    driver_memory = spark.driver_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    inxml = meta.fusion_outxml
    outxml = meta.ds_outxml
    n5dir = meta.ds_n5dir
/*     """
    /opt/scripts/runapp.sh "$workflow.containerEngine" "$spark.work_dir" "$spark.uri" \
        /app/app.jar net.preibisch.bigstitcher.spark.SparkResaveN5 \
        $spark.parallelism $spark.worker_cores "$executor_memory" $spark.driver_cores "$driver_memory" \
        -x ${inxml} -xo ${outxml} -o ${n5dir} --blockSize ${params.blockSize} -ds "1,1,1;2,2,1;4,4,1;8,8,2;16,16,2"

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        stitching-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """ */
    """
    /opt/spark/bin/spark-class org.apache.spark.deploy.SparkSubmit \
        --class net.preibisch.bigstitcher.spark.SparkResaveN5 \
        --master local[$spark.worker_cores] \
        --driver-memory 600G \
        --executor-memory 16G \
        /app/app.jar \
        -x ${inxml} -xo ${outxml} -o ${n5dir} --blockSize ${params.blockSize} -ds "1,1,1;2,2,1;4,4,1;8,8,2;16,16,2" --retry 10

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        stitching-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """ 
}

process SPARK_FUSION {
    scratch true

    tag "${meta.id}"
    container 'ghcr.io/janeliascicomp/bigstitcher-spark:0.0.11'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }
    cpus { spark.driver_cores }
    memory { spark.driver_memory }

    input:
    tuple val(meta), path(xml), val(spark) 

    output:
    tuple val(meta), path(xml), val(spark), emit: acquisitions
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    extra_args = task.ext.args ?: ''
    executor_memory = spark.executor_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    driver_memory = spark.driver_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    inxml = meta.fusion_inxml
    outxml = meta.fusion_outxml
    n5dir = meta.fusion_n5dir
    oneTileWins = params.oneTileWins ? '--oneTileWins' : ''

    parsed_xml = new XmlSlurper().parse("$inxml")
    maxChannelId = parsed_xml.'**'.findAll{ it.name() == 'Channel' }.size() - 1

/*     """
    for i in {0..$maxChannelId}; do
        /opt/scripts/runapp.sh "$workflow.containerEngine" "$spark.work_dir" "$spark.uri" \
            /app/app.jar net.preibisch.bigstitcher.spark.SparkAffineFusion \
            $spark.parallelism $spark.worker_cores "$executor_memory" $spark.driver_cores "$driver_memory" \
            --bdv 0,\$i --channelId \$i -x ${inxml} -xo ${outxml} -o ${n5dir} --blockSize ${params.blockSize} ${oneTileWins} --UINT16 --minIntensity 0.0 --maxIntensity 65535.0 --downsampling "1,1,1" --preserveAnisotropy
    done
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        stitching-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """ */

    """
    for i in {0..$maxChannelId}; do
        /opt/spark/bin/spark-class org.apache.spark.deploy.SparkSubmit \
            --class net.preibisch.bigstitcher.spark.SparkAffineFusion \
            --master local[$spark.worker_cores] \
            --driver-memory 600G \
            --executor-memory 16G \
            /app/app.jar \
            --bdv 0,\$i --channelId \$i -x ${inxml} -xo ${outxml} -o ${n5dir} --blockSize ${params.blockSize} ${oneTileWins} --UINT16 --minIntensity 0.0 --maxIntensity 65535.0 --downsampling "1,1,1" --preserveAnisotropy --retry 10
    done
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        stitching-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """ 
}

process SPARK_MASK {
    scratch true

    tag "${meta.id}"
    container 'ghcr.io/janeliascicomp/bigstitcher-spark:0.0.11'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }
    cpus { spark.driver_cores }
    memory { spark.driver_memory }

    input:
    tuple val(meta), path(xml), val(spark) 

    output:
    tuple val(meta), path(xml), val(spark), emit: acquisitions
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    extra_args = task.ext.args ?: ''
    executor_memory = spark.executor_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    driver_memory = spark.driver_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    inxml = meta.fusion_inxml
    outxml = meta.mask_outxml
    n5dir = meta.mask_n5dir
    oneTileWins = params.oneTileWins ? '--oneTileWins' : ''

    parsed_xml = new XmlSlurper().parse("$inxml")
    maxChannelId = parsed_xml.'**'.findAll{ it.name() == 'Channel' }.size() - 1

/*     """
    for i in {0..$maxChannelId}; do
        /opt/scripts/runapp.sh "$workflow.containerEngine" "$spark.work_dir" "$spark.uri" \
            /app/app.jar net.preibisch.bigstitcher.spark.SparkAffineFusion \
            $spark.parallelism $spark.worker_cores "$executor_memory" $spark.driver_cores "$driver_memory" \
            --bdv 0,\$i --channelId \$i -x ${inxml} -xo ${outxml} -o ${n5dir} --blockSize ${params.blockSize} ${oneTileWins} --masks --UINT16 --minIntensity 0.0 --maxIntensity 65535.0 --downsampling "1,1,1;2,2,2;4,4,4"
    done
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        stitching-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """ */

    """
    for i in {0..$maxChannelId}; do
        /opt/spark/bin/spark-class org.apache.spark.deploy.SparkSubmit \
            --class net.preibisch.bigstitcher.spark.SparkAffineFusion \
            --master local[$spark.worker_cores] \
            --driver-memory 600G \
            --executor-memory 16G \
            /app/app.jar \
            --bdv 0,\$i --channelId \$i -x ${inxml} -xo ${outxml} -o ${n5dir} --blockSize ${params.blockSize} ${oneTileWins} --masks --UINT16 --minIntensity 0.0 --maxIntensity 65535.0 --downsampling "1,1,1;2,2,2;4,4,4" --preserveAnisotropy --retry 10
    done
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        stitching-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """ 
}

process SPARK_MASK {
    scratch true

    tag "${meta.id}"
    container 'ghcr.io/janeliascicomp/bigstitcher-spark:0.0.7'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }
    cpus { spark.driver_cores }
    memory { spark.driver_memory }

    input:
    tuple val(meta), path(xml), val(spark) 

    output:
    tuple val(meta), path(xml), val(spark), emit: acquisitions
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    extra_args = task.ext.args ?: ''
    executor_memory = spark.executor_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    driver_memory = spark.driver_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    inxml = meta.fusion_inxml
    outxml = meta.mask_outxml
    n5dir = meta.fusion_n5dir
    oneTileWins = params.oneTileWins ? '--oneTileWins' : ''

    parsed_xml = new XmlSlurper().parse("$inxml")
    maxChannelId = parsed_xml.'**'.findAll{ it.name() == 'Channel' }.size() - 1

    """
    for i in {0..$maxChannelId}; do
        /opt/scripts/runapp.sh "$workflow.containerEngine" "$spark.work_dir" "$spark.uri" \
            /app/app.jar net.preibisch.bigstitcher.spark.AffineFusion \
            $spark.parallelism $spark.worker_cores "$executor_memory" $spark.driver_cores "$driver_memory" \
            --bdv 0,\$i --channelId \$i -x ${inxml} -xo ${outxml} -o ${n5dir} --blockSize ${params.blockSize} ${oneTileWins} --mask --UINT16 --minIntensity 0.0 --maxIntensity 65535.0 --downsampling "1,1,1;2,2,2;4,4,4"
    done
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        stitching-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """
}

process fix_res {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-py:0.0.9'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "4 GB" }
    cpus { 1 }

    input:
    tuple val(src), val(dst), val(xml)
    val(control_1) 

    output:
    val(dst), emit: control_1
    
    script:
    """
    /entrypoint.sh fix_res -i $src -o $dst -x $xml
    """
}

process fix_res_mask {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-py:0.0.9'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "4 GB" }
    cpus { 1 }

    input:
    tuple val(src), val(dst), val(xml)
    val(control_1) 

    output:
    val(dst), emit: control_1
    
    script:
    """
    /entrypoint.sh fix_res -i $src -o $dst -x $xml
    """
}

process fix_res_single {
    scratch true

    container 'ghcr.io/janeliascicomp/nd2-to-n5-py:0.0.9'
    containerOptions { getOptions([getParent(params.inputPath), params.outputPath]) }

    memory { "4 GB" }
    cpus { 1 }

    input:
    tuple val(src), val(dst), val(xml)
    val(control_1) 

    output:
    val(dst), emit: control_1
    
    script:
    """
    /entrypoint.sh fix_res -i $src -o $dst -x $xml
    """
}

workflow {
    infile = params.inputPath
    indir = file(params.inputPath).parent
    outdir = params.outputPath
    tmpdir = params.outputPath + "/tmp_" + workflow.sessionId.toString()
    sparkdir = params.outputPath + "/spark"
    bgpath = params.bgimg

    myDir = file(outdir)
    result = myDir.mkdirs()
    println result ? "Created $myDir" : "Cannot create directory: $myDir"
    myDir2 = file(tmpdir)
    result2 = myDir2.mkdirs()
    println result2 ? "Created $myDir2" : "Cannot create directory: $myDir2"

    nd2 = Channel.fromPath(infile)
    base_name = file(infile).getBaseName()
    nd2.subscribe { println "nd2: $it" }

    param = nd2.map{ tuple("${infile}", "${tmpdir}/${file(it).baseName}.xml") }
    n5xml = define_dataset(param)
    n5xml.subscribe { println "n5xml: $it" }

    param2 = n5xml.map{ tuple("$it", "${tmpdir}/${file(it).baseName}_fixed.xml") }
    fixedxml = fix_n5xml(param2)
    fixedxml.subscribe { println "fixedxml: $it" }

    if ( !params.fusionOnly ) {
        param_t = nd2.map{ tuple("${infile}", "${tmpdir}/${file(it).baseName}.csv") }
        csv = gen_csv(param_t)
        csv.subscribe { println "csv: $it" }

        csv
        .map { file(it) }
        .set { csvfile }

        csvfile
        .splitCsv(header:false, sep: '\t')
        .map { row-> row[0] }
        .set { flist }

        param_tif = flist.map{ tuple("${infile}", "${it}", "${bgpath}", "${params.crop}") }
        tiff1 = nd2tiff(param_tif)

        param_t = fixedxml.map{ tuple("$it", "${tmpdir}/${file(it).baseName}_tiff.xml", "${tmpdir}/${file(it).baseName}_tiff.csv", "${params.crop}") }
        csv2 = split_xml(param_t, nd2tiff.out.control_1.collect())
        csv2.subscribe { println "csv2: $it" }

        csv2
        .map { file(it) }
        .set { csvfile2 }

        csvfile2
        .splitCsv(header:false, sep: '\t')
        .map { row-> row[0] }
        .set { flist2 }

        flist2.subscribe { println "flist2: $it" }

        flist2.map {
            def xml = it
            meta = [:]
            meta.id = file(xml).baseName
            meta.spark_work_dir = "${outdir}/spark/${workflow.sessionId}/${meta.id}"
            meta.outdir = tmpdir + "/" + meta.id
            meta.tmpdir = tmpdir
            meta.resave_inxml = xml
            meta.resave_outxml = meta.tmpdir + "/" + meta.id + "_resaved.xml"
            meta.resave_n5dir = meta.tmpdir + "/" + meta.id + "_resaved.n5"
            meta.single_tile = "${tmpdir}/SingleTile"
            meta.dapi = "${params.dapi_channel}"
            meta.padding_n5dir = meta.tmpdir + "/" + meta.id + "_resaved.xml"
            [meta, xml]
        }.set { ch_acquisitions }

        STITCHING_PREPARE(
            ch_acquisitions
        )

        sp_start = SPARK_START(
            STITCHING_PREPARE.out, 
            [indir, outdir], //directories to mount
            params.spark_cluster,
            params.spark_workers as int,
            params.spark_worker_cores as int,
            params.spark_gb_per_core as int,
            params.spark_driver_cores as int,
            params.spark_driver_memory
        )

        sp_start.branch {
            single: file(it[0].single_tile).exists() == true
            multi: file(it[0].single_tile).exists() == false
        }.set{ sp_start_branching }

        SPARK_RESAVE(sp_start_branching.multi)
        done = SPARK_STOP(SPARK_RESAVE.out.acquisitions)

        SPARK_RESAVE_SINGLE(sp_start_branching.single)
        done_single = SPARK_STOP_SINGLE(SPARK_RESAVE_SINGLE.out.acquisitions)

        padding_single(SPARK_RESAVE_SINGLE.out.acquisitions, SPARK_STOP_SINGLE.out.collect())

        param_single = padding_single.out.acquisitions.map{ tuple("${it[0].resave_outxml}", "${outdir}", "${it[0].resave_outxml}") }
        fix_res_single(param_single, SPARK_STOP_SINGLE.out.collect())

        param_mask_single = fix_res_single.out.control_1.map{ tuple("${it}", "${outdir}_mask.tif") }
        padding_mask_single(param_mask_single)

        tmpdir_ch_single = Channel.fromPath(tmpdir)
        remove_dir_single(tmpdir_ch_single, padding_mask_single.out.control_1.collect())

        checkpoint_ch_single = Channel.fromPath("${outdir}/${base_name}.checkpoint")
        create_checkpoint_single(checkpoint_ch_single, remove_dir_single.out.collect())
        
    }
    else
    {
        param_t = fixedxml.map{ tuple("$it", "${tmpdir}/${file(it).baseName}_tiff.xml", "${tmpdir}/${file(it).baseName}_tiff.csv") }
        csv2 = split_xml(param_t, fix_n5xml.out.collect())
        csv2.subscribe { println "csv2: $it" }

        csv2
        .map { file(it) }
        .set { csvfile2 }

        csvfile2
        .splitCsv(header:false)
        .map { row-> row[0] }
        .set { flist2 }

        flist2.subscribe { println "flist2: $it" }

        flist2.map{ tuple("${tmpdir}/${file(it).baseName}/${file(it).baseName}_resaved.xml", "$it") }.set{ param_resaved }
    }

    if ( params.prestitch ) {
        tmpdir_ch = Channel.fromPath(tmpdir)
        remove_dir(tmpdir_ch, SPARK_STOP.out.collect())
    }
    else {
        if ( !params.fusionOnly ) {
            calc_results = calc_stitching(SPARK_RESAVE.out.acquisitions, done)
        }
        else {
            calc_results = calc_stitching_resume(param_resaved)
        }
        calc_results.map {
            def xml = it
            meta = [:]
            meta.id = file(xml).baseName + "_resaved"
            meta.spark_work_dir = "${outdir}/spark/${workflow.sessionId}/${meta.id}"
            meta.indir = outdir + "/" + file(xml).baseName
            meta.tmpdir = tmpdir
            meta.fusion_inxml = meta.tmpdir + "/" + meta.id + ".xml"
            meta.fusion_outxml = meta.tmpdir + "/" + file(xml).baseName + "_fused.xml"
            meta.fusion_n5dir = meta.tmpdir + "/" + file(xml).baseName + "_fused.n5"
            meta.mask_outxml = meta.tmpdir + "/" + file(xml).baseName + "_mask.xml"
            meta.mask_n5dir = meta.tmpdir + "/" + file(xml).baseName + "_mask.n5"
            meta.dapi = "${params.dapi_channel}"
            meta.padding_n5dir = meta.tmpdir + "/" + file(xml).baseName + "_fused.xml"
            meta.ds_outxml = meta.tmpdir + "/" + file(xml).baseName + "_ds.xml"
            meta.ds_n5dir = meta.tmpdir + "/" + file(xml).baseName + "_ds.n5"
            [meta, xml]
        }.set { ch_acquisitions2 }


        STITCHING_PREPARE2(
            ch_acquisitions2
        )

        SPARK_START2(
            STITCHING_PREPARE2.out, 
            [indir, outdir], //directories to mount
            params.spark_cluster,
            params.spark_workers as int,
            params.spark_worker_cores_for_fusion as int,
            params.spark_gb_per_core_for_fusion as int,
            params.spark_driver_cores as int,
            params.spark_driver_memory
        )

        //SPARK_MASK(SPARK_START2.out)
        //SPARK_FUSION(SPARK_MASK.out.acquisitions)

        SPARK_FUSION(SPARK_START2.out)

        done = SPARK_STOP2(SPARK_FUSION.out.acquisitions)

        padding(SPARK_FUSION.out.acquisitions, SPARK_STOP2.out.collect())

        padding.out.acquisitions.map {
            def xml = it[1]
            meta = it[0]
            meta.id = file(xml).baseName + "_fused"
            meta.spark_work_dir = "${outdir}/spark/${workflow.sessionId}/${meta.id}"
            [meta, it[1]]
        }.set { padding_acquisitions2 }


        STITCHING_PREPARE3(
            padding_acquisitions2
        )

        SPARK_START3(
            STITCHING_PREPARE3.out, 
            [indir, outdir], //directories to mount
            params.spark_cluster,
            params.spark_workers as int,
            params.spark_worker_cores as int,
            params.spark_gb_per_core as int,
            params.spark_driver_cores as int,
            params.spark_driver_memory
        )

        SPARK_DOWNSAMPLE(SPARK_START3.out)

        done = SPARK_STOP3(SPARK_DOWNSAMPLE.out.acquisitions)

        param5 = SPARK_DOWNSAMPLE.out.acquisitions.map{ tuple("${it[0].ds_outxml}", "${outdir}", "${it[0].fusion_inxml}") }

        fix_res(param5, SPARK_STOP3.out.collect())

        //param6 = SPARK_MASK.out.acquisitions.map{ tuple("${it[0].mask_outxml}", "${outdir}/step1/${params.batchLabel}/mask", "${it[0].fusion_inxml}") }
        //fix_res_mask(param6, SPARK_STOP2.out.collect())

        param_mask = fix_res.out.control_1.map{ tuple("${it}", "${outdir}_mask.tif") }
        padding_mask(param_mask)

        tmpdir_ch = Channel.fromPath(tmpdir)
        remove_dir(tmpdir_ch, padding_mask.out.control_1.collect())

        checkpoint_ch = Channel.fromPath("${outdir}/${base_name}.checkpoint")
        create_checkpoint(checkpoint_ch, remove_dir.out.collect())
    }
}
