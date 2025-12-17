process RS_FISH {
    tag "${meta.id}"
    container { task && task.ext.container ?: 'ghcr.io/janeliascicomp/rs_fish:2.0.0' }
    cpus { spark.driver_cores }
    memory { spark.driver_memory }

    input:
    tuple val(meta),
          path(input_image),
          val(input_dataset),
          path(spots_output_dir, stageAs: 'spots/*'),
          val(spots_result_name),
          val(rsfish_args),
          val(spark)

    output:
    tuple val(meta),
          env(INPUT_IMG),
          val(input_dataset),
          path(spots_output_dir),
          val(spots_result_name),
          val(spark),                           emit: params
    tuple val(meta), env(full_output_filename), emit: csv
    path "versions.yml",                        emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def extra_args = task.ext.args ?: ''
    def output_filename = spots_result_name ?: "${meta.id}-points.csv"
    def executor_memory = spark.executor_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    def driver_memory = spark.driver_memory.replace(" KB",'k').replace(" MB",'m').replace(" GB",'g').replace(" TB",'t')
    """
    INPUT_IMG=\$(realpath ${input_image})
    full_spots_dir=\$(readlink -m ${spots_output_dir})
    mkdir -p \${full_spots_dir}
    full_output_filename=\${full_spots_dir}/${output_filename}
    CMD=(
        /opt/scripts/runapp.sh
        "${workflow.containerEngine}"
        "${spark.work_dir}"
        "${spark.uri}"
        /app/app.jar
        net.preibisch.rsfish.spark.SparkRSFISH
        ${spark.parallelism}
        ${spark.worker_cores}
        ${executor_memory}
        ${spark.driver_cores}
        ${driver_memory}
        --image=\${INPUT_IMG}
        --dataset=${input_dataset}
        --output=\${full_output_filename}
        ${rsfish_args}
        ${extra_args}
    )
    echo "CMD: \${CMD[@]}"
    (exec "\${CMD[@]}")

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spark: \$(cat /opt/spark/VERSION)
        rs-fish-spark: \$(cat /app/VERSION)
    END_VERSIONS
    """
}
