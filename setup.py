#!/usr/bin/env python
from setuptools import setup, find_packages

setup (
    name = "katsdisp",
    version = "trunk",
    description = "Karoo Array Telescope Online Signal Displays",
    author = "Simon Ratcliffe",
    packages = find_packages(),
    scripts = [
        "scripts/k7_augment.py",
        "scripts/k7_capture_katcp.py",
        "scripts/k7_capture.py",
        "scripts/k7_simulator.py",
        ],
    zip_safe = False,
)
