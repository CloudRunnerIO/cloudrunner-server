#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed
#  * without the express permission of CloudRunner.io
#  *******************************************************/

from os import path
import sys

common = []

if sys.version_info < (2, 7):
    # 2.6 fix for unit tests
    # http://bugs.python.org/issue15881#msg170215
    import multiprocessing  # noqa
    common = ['ordereddict']
    req_file = path.join(path.dirname(path.abspath(__file__)),
                         'requirements-py26.txt')
else:
    import os
    os.system('ls %s' % path.dirname(path.abspath(__file__)))
    req_file = path.join(path.dirname(path.abspath(__file__)),
                         'requirements-py27.txt')

from distutils.core import setup
from setuptools import find_packages

from cloudrunner_server.version import VERSION

requirements = [req.strip() for req in open(req_file).read().split()]

common = common + requirements
test_requirements = common + ['mock', 'coverage', 'flake8']

setup(
    name='cloudrunner_server',
    version=VERSION,
    url='http://www.cloudrunner.io/',
    author='CloudRunner.io',
    author_email='dev@cloudrunner.io',
    description=('Script execution engine for cloud environments.'),
    license='Proprietary',
    packages=find_packages(),
    package_data={'': ['*.txt', '*.rst'], 'conf': ['.*.conf'], 'db': ['*.*'],
                  'api': ["*.html"], 'doc': ["*.*"]},
    include_package_data = True,
    install_requires=requirements,
    tests_require = test_requirements,
    test_suite = 'nose.collector',
    scripts=['bin/cloudrunner-server-autocomplete'],
    entry_points={
        "console_scripts": [
            "cloudrunner-master = cloudrunner_server.master.cli:main",
            "cloudrunner-dsp = cloudrunner_server.dispatcher.server:main",
            "cloudrunner-trigger = cloudrunner_server.triggers.manager:main",
        ]
    },
    classifiers=[
        'Development Status :: 4 - Beta',
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
