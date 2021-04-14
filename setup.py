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
    python_requires=">=3.5",
    install_requires=[
        "h5py",
        "manhole",
        "matplotlib",
        "netifaces",
        "numpy",
        "psutil",
        "six",
        "spead2>=3.0.0",
        "katsdpservices[argparse]",
        "katsdptelstate",
        "katdal",
        "katpoint"],
    use_katversion=True
)
