CloudRunner.io Server
=======================


Copyright (c) 2013-2014 CloudRunner.io

SERVICE CONFIGURATION

-------------------------------

* Initial setup


Add CloudRunner Yum Repo

.. code-block::
    
    # Create the file /etc/yum.repos.d/cloudrunner-stable.repo
    # with the following contents:
    
    # For Centos 6 (EPEL6):

    [cloudrunner-stable]
    name=CloudRunner Stable Repo
    baseurl=https://user:pass@repo-stable.cloudrunner.io/el6/
    # mirrorlist=
    enabled=1
    gpgcheck=1
    gpgkey=https://repo-stable.cloudrunner.io/repo-stable.cloudrunner.io.pub.asc


    # For Centos 7 (EPEL7):

    [cloudrunner-stable]
    name=CloudRunner Stable Repo
    baseurl=https://user:pass@repo-stable.cloudrunner.io/el7/
    # mirrorlist=
    enabled=1
    gpgcheck=1
    gpgkey=https://repo-stable.cloudrunner.io/repo-stable.cloudrunner.io.pub.asc


then install the packages

.. code-block:: bash

    yum install cloudrunner-server


Then configure server

.. code-block:: bash

    cloudrunner-master config create


* Starting the service

From console

.. code-block:: bash
    cloudrunner-dsp run

or as a daemon:

.. code-block:: bash
    cloudrunner-dsp start --pidfile=file.pid


As a service from packages:

.. code-block:: bash

    service cloudrunner-dsp start

