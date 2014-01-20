#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 CloudRunner.IO
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import shutil
import sys

if sys.version_info < (2, 7):
    # 2.6 fix for unit tests
    # http://bugs.python.org/issue15881#msg170215
    import multiprocessing

from distutils.core import setup
from setuptools import find_packages

from version import VERSION

os_requirements = []

if os.name == 'nt':
    # Add Windows requirements
    os_requirements.append('pywin32')

test_requirements = ['nose>=1.0', 'mock', 'coverage']

setup(
    name='cloudrunner',
    version=VERSION,
    url='http://www.cloudrunner.io/',
    author='CloudRunner.io',
    author_email='dev@cloudrunner.io',
    description=('Script execution engine for cloud environments.'),
    license='BSD',
    packages=find_packages(),
    package_data={'': ['*.txt', '*.rst'], 'conf': ['.*.conf'], 'db': ['*.py']},
    include_package_data = True,
    install_requires=[
        'pyzmq', 'python-crontab', 'M2Crypto', 'httplib2'] + os_requirements,
    tests_require = test_requirements,
    test_suite = 'nose.collector',
    scripts=['bin/cloudrunner-autocomplete'],
    entry_points={
        "console_scripts": [
            "cloudrunner = cloudrunner.shell.runner:main",
            "cloudrunner-master = cloudrunner.master.cli:main",
            "cloudrunner-node = cloudrunner.node.agent:main",
            "cloudrunner-dsp = cloudrunner.dispatcher.server:main",
        ]
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
