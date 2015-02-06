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

from random import SystemRandom
import string

TOKEN_CHARS = string.letters + string.digits + '~_-'


class AttrGetterMeta(type):

    def __getattr__(cls, name):
        return lambda *args, **kwargs: cls._output(name, *args, **kwargs)


class JsonOutput(object):
    __metaclass__ = AttrGetterMeta

    @staticmethod
    def _anon(**kwargs):
        return kwargs

    @staticmethod
    def _output(wrapper, *args, **kwargs):
        if '_list' in kwargs:
            return {wrapper: kwargs['_list']}
        elif args:
            return {wrapper: args[0]}
        else:
            return {wrapper: kwargs}


def random_token(*args, **kwargs):
    length = kwargs.get('length', 64)
    token_chars = kwargs.get('chars', TOKEN_CHARS)
    token = ''.join(SystemRandom().choice(token_chars)
                    for x in range(length))
    return token


class Wrap(object):

    def __init__(self, **kwargs):
        self._items = kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)


def flatten_params(params):
    d = {}
    if params:
        def _map(k):
            elem = params.getall(k)
            if len(elem) > 1:
                d[k] = elem
            else:
                d[k] = elem[0]
        map(_map, params)
    return d
