#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

requires = ['qhue', 'numpy']

setup(
    name='ip_hue',
    install_requires=requires,
    license='GPL2',
)