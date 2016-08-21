#!/usr/bin/env python

from distutils.core import setup

with open('requirements.txt') as f:
    required = f.read().splitlines()

setup(name='Endoapi',
      version_format='dev{commitcount}+{gitsha}',
      setup_requires=['setuptools-git-version'],
      description='Unofficial API for Endomondo based on https://github.com/yannickcarer/endomondo-export',
      author='Piotr',
      author_email='podusowski@gmail.com',
      url='https://github.com/podusowski/endoapi',
      packages=['endoapi'],
      install_requires=required,
     )
