#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
# vim: ai ts=4 sts=4 et sw=4
from setuptools import setup

setup(
    name="pdu",
    version="1.0",
    license="MIT",
    author="Grégory Duchatelet",
    author_email="skygreg@gmail.com",
    maintainer="Grégory Duchatelet",
    maintainer_email="skygreg@gmail.com",
    install_requires=["termcolor", "nicelog", "pysnmp"],
    description="APC PDU tool",
    url="https://github.com/gregorg/pdu",
    packages=[],
    scripts=["pdu.py"]
)
