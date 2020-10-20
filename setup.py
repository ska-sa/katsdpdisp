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
    python_requires=">=3.5",
    install_requires=["spead2>=1.5.0,<3", "katsdpservices[argparse]", "six"],
    use_katversion=True
)
