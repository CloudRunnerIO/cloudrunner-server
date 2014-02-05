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

import sys

if sys.version_info < (2, 7):
    # 2.6 fix for unit tests
    # http://bugs.python.org/issue15881#msg170215
    import multiprocessing

from distutils.core import setup
from setuptools import find_packages

from version import VERSION

test_requirements = ['nose>=1.0', 'mock', 'coverage']

setup(
    name='cloudrunner_server',
    version=VERSION,
    url='http://www.cloudrunner.io/',
    author='CloudRunner.io',
    author_email='dev@cloudrunner.io',
    description=('Script execution engine for cloud environments.'),
    license='BSD',
    packages=find_packages(),
    package_data={'': ['*.txt', '*.rst'], 'conf': ['.*.conf'], 'db': ['*.py']},
    include_package_data = True,
    install_requires=['cloudrunner', 'pyzmq', 'python-crontab',
                      'M2Crypto', 'httplib2'],
    tests_require = test_requirements,
    test_suite = 'nose.collector',
    scripts=['bin/cloudrunner-server-autocomplete'],
    entry_points={
        "console_scripts": [
            "cloudrunner-master = cloudrunner_server.master.cli:main",
            "cloudrunner-dsp = cloudrunner_server.dispatcher.server:main",
            "cloudrunner-plugins-node = "
            "cloudrunner_server.plugins.bin.plugins_node:install",
            "cloudrunner-plugins-openstack-node = "
            "cloudrunner_server.plugins.bin.plugins_openstack_node:install",
            "cloudrunner-plugins-openstack-master = "
            "cloudrunner_server.plugins.bin.plugins_openstack_master:install",
            "cloudrunner-plugins-keystone = "
            "cloudrunner_server.plugins.bin.plugins_keystone:install",
        ]
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Environment :: Plugins',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Information Technology',
        'License :: Other/Proprietary License',
        'Operating System :: Unix',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
