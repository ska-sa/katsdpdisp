#!groovy

def katsdp = fileLoader.fromGit('scripts/katsdp.groovy', 'git@github.com:ska-sa/katsdpjenkins', 'master', 'katpull', '')
katsdp.setDependencies(['ska-sa/katsdpdockerbase/master'])
katsdp.standardBuild(maintainer: 'mattieu@ska.ac.za')
