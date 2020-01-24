#!groovy

@Library('katsdpjenkins') _
katsdp.killOldJobs()
katsdp.setDependencies([
    'ska-sa/katsdpdockerbase/python2',
    'ska-sa/katsdpservices/master'
])
katsdp.standardBuild(push_external: true)
katsdp.mail('sdpdev+katsdpdisp@ska.ac.za')
