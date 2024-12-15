
def getOptions(paths) { 
    def uniquePaths = paths.unique(false)
    switch (workflow.containerEngine) {
        case 'docker': 
            def bindPaths = uniquePaths.collect { "-v $it:$it" } join(' ')
            //println "${params.runtime_opts} ${bindPaths}"
            return "${params.runtime_opts} ${bindPaths}"
        case 'singularity':
            def bindPaths = uniquePaths.collect { "-B $it" } join(' ')
            //println "${params.runtime_opts} ${bindPaths}"
            return "${params.runtime_opts} ${bindPaths}"
        default:
            throw new IllegalStateException("Container engine is not supported: ${workflow.containerEngine}")
    }
}

def getParent(path) { 
    def parent = file(path).parent
    return "${parent}"
}