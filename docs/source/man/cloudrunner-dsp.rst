===============
CloudRunner Dispatcher service
===============

SYNOPSIS
========

::

  cloudrunner-dsp [-h] [-p PIDFILE] [-c CONFIG] {start,stop,restart,run}

DESCRIPTION
===========

cloudrunner-dsp is the main server that dispatches and coordinates the execution
of scripts from users to nodes.

OPTIONS
=======

positional arguments:
  {start,stop,restart,run}
                        Apply action on the daemonized process For the actions
                        [start, stop, restart] - pass a pid file Run - start
                        process in debug mode

optional arguments:
  -h, --help            show this help message and exit
  -p PIDFILE, --pidfile PIDFILE
                        Daemonize process with the given pid file
  -c CONFIG, --config CONFIG
                        Config file
