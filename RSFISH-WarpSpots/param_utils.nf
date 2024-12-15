def default_mf_params() {
    def multifish_container_repo = 'public.ecr.aws/janeliascicomp/multifish'
    def default_airlocalize_params = '/app/airlocalize/params/air_localize_default_params.txt'

    [
        mfrepo: multifish_container_repo,
        airlocalize_container: '',

        dapi_channel: 'c2', // DAPI channel used to drive both the segmentation and the registration
        bleed_channel: 'c3',

        // spot extraction params
        spot_extraction_scale: 's0',

        // RS-Fish params
        rsfish_container_repo: multifish_container_repo,
        rsfish_container_name: 'rs_fish',
        rsfish_container_version: '1.0.1',
        rs_fish_app: '/app/app.jar',
        rsfish_workers: 6,
        rsfish_worker_cores: 8,
        rsfish_gb_per_core: 8,
        rsfish_driver_cores: 1,
        rsfish_driver_memory: '1g',
        rsfish_min: 0,
        rsfish_max: 4096,
        rsfish_anisotropy: 0.7,
        rsfish_sigma: 1.5,
        rsfish_threshold: 0.007,
        rsfish_params: '',
        // RS-Fish parameters adjustable per channel
        per_channel: [
            rsfish_min: '',
            rsfish_max: '',
            rsfish_anisotropy: '',
            rsfish_sigma: '',
            rsfish_threshold: '',
        ],

        bigwarp_container_repo: 'ghcr.io/janeliascicomp',
        bigwarp_container_name: 'bigstream-py',
        bigwarp_container_version: '1.0.1'

    ]
}

def set_derived_defaults(mf_params, user_params) {
    if (mf_params.shared_work_dir) {
        if (!user_params.containsKey('data_dir')) {
            mf_params.data_dir = "${mf_params.shared_work_dir}/inputs"
        }
        if (!user_params.containsKey('output_dir')) {
            mf_params.output_dir = "${mf_params.shared_work_dir}/outputs"
        }
        if (!user_params.containsKey('segmentation_model_dir')) {
            mf_params.segmentation_model_dir = "${mf_params.shared_work_dir}/inputs/model/starfinity"
        }
        if (!user_params.containsKey('spark_work_dir')) {
            mf_params.spark_work_dir = "${mf_params.shared_work_dir}/spark"
        }
        if (!user_params.containsKey('singularity_cache_dir')) {
            mf_params.singularity_cache_dir = "${mf_params.shared_work_dir}/singularity"
        }
    }
    mf_params
}

def get_value_or_default(Map ps, String param, String default_value) {
    if (ps[param])
        ps[param]
    else
        default_value
}

def get_list_or_default(Map ps, String param, List default_list) {
    def source_value = ps[param]

    if (source_value == null) {
        return default_list
    } else if (source_value instanceof Boolean) {
        // most likely the parameter was set as '--param'
        // followed by no value
        return default_list
    } else if (source_value instanceof String) {
        if (source_value.trim() == '') {
            return default_list
        } else {
            return source_value.tokenize(',').collect { it.trim() }
        }
    } else {
        // this is the case in which a parameter was set to a numeric value,
        // e.g., "--param 1000" or "--param 20.3"
        return [source_value]
    }
}

def airlocalize_container_param(Map ps) {
    def spot_extraction_container = ps.spot_extraction_container
    if (!spot_extraction_container)
        "${ps.mfrepo}/spot_extraction:1.2.0"
    else
        airlocalize_container
}
