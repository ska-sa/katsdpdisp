#!/usr/bin/env python
from setuptools import setup, find_packages

setup (
    name = "katsdisp",
    version = "trunk",
    description = "Karoo Array Telescope Online Signal Displays",
    author = "Mattieu de Villiers",
    packages = find_packages(),
    package_data={'': ['html/*']},
    include_package_data = True,
    scripts = [
        "scripts/time_plot.py",
        ],
    zip_safe = False,
)
