#!/usr/bin/env python
from setuptools import setup, find_packages

setup (
    name = "katsdpdisp",
    description = "Karoo Array Telescope Online Signal Displays",
    author = "MeerKAT SDP team",
    author_email = "sdpdev+katsdpdisp@ska.ac.za",
    packages = find_packages(),
    package_data={'': ['html/*']},
    include_package_data = True,
    scripts = [
        "scripts/time_plot.py",
        ],
    zip_safe = False,
    setup_requires=["katversion"],
    install_requires=["spead2>=1.5.0", "katsdpservices[argparse]"],
    use_katversion=True
)
