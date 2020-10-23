#!groovy

@Library('katsdpjenkins') _
katsdp.killOldJobs()
katsdp.setDependencies(['ska-sa/katsdpdockerbase/new-rdma-core',
                        'ska-sa/katsdpservices/master'])
katsdp.standardBuild(
    python3: true,
    python2: false,
    docker_venv: true,
    push_external: true,
    katsdpdockerbase_ref: 'new-rdma-core')
katsdp.mail('sdpdev+katsdpdisp@ska.ac.za')
