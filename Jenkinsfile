#!groovy

@Library('katsdpjenkins') _
katsdp.killOldJobs()
katsdp.setDependencies(['ska-sa/katsdpdockerbase/master'])
katsdp.standardBuild(
    python3: true,
    python2: false,
    docker_venv: true,
    push_external: true)
katsdp.mail('sdpdev+katsdpdisp@ska.ac.za')
