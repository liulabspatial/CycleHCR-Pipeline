process SPARK_TERMINATE {
    label 'process_single'
    container 'ghcr.io/janeliascicomp/spark:3.3.2-scala2.12-java17-ubuntu24.04-gzip-zstd'

    input:
    // we need to pass the data_paths because it should contain the spark work dir
    // and that needs to be mounted in the container
    tuple val(meta), val(spark), path(spark_work_dir)

    output:
    tuple val(meta), val(spark)

    script:
    terminate_file_name = "${spark_work_dir}/terminate-spark"
    """
    /opt/scripts/terminate.sh "$terminate_file_name"
    """
}

/**
 * Terminate the specified Spark clusters.
 */
workflow SPARK_STOP {
    take:
    ch_meta_and_spark // channel: [ val(meta), val(spark) ]
    spark_cluster     // boolean: use a distributed cluster?

    main:
    if (spark_cluster) {
        done = ch_meta_and_spark
        | map {
            def (meta, spark) = it
            log.debug "Stop spark: [$meta, $spark]"
            [ meta, spark, file(spark.work_dir) ]
        }
        | SPARK_TERMINATE
    } else {
        done = ch_meta_and_spark
    }
    done.subscribe { log.debug "Terminated spark cluster: $it" }

    emit:
    done
}
