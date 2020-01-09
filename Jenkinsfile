#!groovy

@Library('katsdpjenkins') _
katsdp.killOldJobs()
katsdp.setDependencies(['ska-sa/katsdpdockerbase/python2'])
katsdp.standardBuild(push_external: true)
katsdp.mail('sdpdev+katsdpdisp@ska.ac.za')
