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

import abc
import json


class LoggerPluginBase(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def __init__(self, config):
        pass

    @abc.abstractmethod
    def set_context_from_config(self):
        pass

    @abc.abstractmethod
    def log(self, **kwargs):
        pass


class FrameBase(object):

    def __init__(self):
        self.header = {'type': self.frame_type}
        self.body = []
        self.seq_no = 0

    @classmethod
    def create(cls, **kwargs):
        _type = kwargs.pop('type')
        frame = None
        if _type == "INITIAL":
            frame = InitialFrame()
        elif _type == "PARTIAL":
            frame = BodyFrame()
        elif _type == "FINISHED":
            frame = SummaryFrame()
        else:
            return None
        frame.push(**kwargs)
        return frame

    @classmethod
    def restore(cls, seq_no, **keys):
        _type = keys.pop('type')
        frame = None
        if _type == "I":
            frame = InitialFrame()
        elif _type == "B":
            frame = BodyFrame()
        elif _type == "S":
            frame = SummaryFrame()
        else:
            return None
        frame.seq_no = seq_no
        frame.header = keys
        return frame

    def push(self, **kwargs):
        self.header.update(kwargs)

    def __repr__(self):
        return "Frame: <%s> <%s>" % (self.frame_type, self.seq_no)


class InitialFrame(FrameBase):
    frame_type = "I"

    def push(self, seq_no=None, job_id=None, step_id=None, **kwargs):
        self.body = [json.dumps(kwargs)]
        self.seq_no = seq_no
        self.header['job_id'] = job_id
        self.header['step_id'] = step_id


class BodyFrame(FrameBase):
    frame_type = "B"

    def push(self, seq_no=None, node=None, step_id=None,
             stdout=None, stderr=None, **kwargs):
        if stdout:
            self.body = stdout.splitlines()
        elif stderr:
            self.body = stderr.splitlines()
        self.seq_no = seq_no
        self.header['node'] = node
        self.header['step_id'] = step_id


class SummaryFrame(FrameBase):
    frame_type = "S"

    def push(self, seq_no=None, job_id=None, step_id=None, **kwargs):
        self.body = [json.dumps(kwargs)]
        self.seq_no = seq_no
        self.header['job_id'] = job_id
        self.header['step_id'] = step_id
