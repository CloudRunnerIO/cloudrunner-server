===============
CloudRunner Master configuration service
===============


SYNOPSIS
========

::

usage: cloudrunner-master [-h] {org,cert,config,users,schedule} ...

DESCRIPTION
===========

CloudRunner Master configuration tool.
Performs configuration of the master functions.


OPTIONS
=======

positional arguments:
  {org,cert,config,users,schedule}
                        Commands
    cert                Manage node certificates
    config              Initial certificate configuration
    schedule            Run scheduled jobs
    org                 Organization management
    users               User management

optional arguments:
  -h, --help            show this help message and exit
