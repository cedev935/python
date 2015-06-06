#!/usr/bin/env python
# -*- encoding: utf-8 -*-
from __future__ import absolute_import, print_function
import io
import os
import re
from glob import glob
from os.path import basename
from os.path import dirname
from os.path import join
from os.path import relpath
from os.path import splitext

from setuptools import find_packages
from setuptools import setup


def read(*names, **kwargs):
    return io.open(
        join(dirname(__file__), *names),
        encoding=kwargs.get('encoding', 'utf8')
    ).read()

setup(
    name='aspectlib',
    version='1.3.0',
    license='BSD',
    description="aspectlib is an aspect-oriented programming, monkey-patch and decorators library. It is useful when "
                "changing behavior in existing code is desired. It includes tools for debugging and testing: simple "
                "mock/record and a complete capture/replay framework.",
    long_description="%s\n%s" % (read('README.rst'), re.sub(':(obj|func):`~?(.*?)`', r'``\1``', read('docs', 'changelog.rst'))),
    author='Ionel Cristian Mărieș',
    author_email='contact@ionelmc.ro',
    url='https://github.com/ionelmc/python-aspectlib',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    py_modules=[splitext(basename(path))[0] for path in glob('src/*.py')],
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        # complete classifier list: http://pypi.python.org/pypi?%3Aaction=list_classifiers
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: Unix',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Topic :: Utilities',
    ],
    keywords=[
        'aop', 'aspects', 'aspect oriented programming', 'decorators', 'patch', 'monkeypatch', 'weave', 'debug', 'log',
        'tests', 'mock', 'capture', 'replay', 'capture-replay', 'debugging', 'patching', 'monkeypatching', 'record',
        'recording', 'mocking', 'logger'
    ],
    install_requires=[
    ],
    extras_require={
    }
)
