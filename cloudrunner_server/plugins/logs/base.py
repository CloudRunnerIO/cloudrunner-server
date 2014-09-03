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
import msgpack


class LoggerPluginBase(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def __init__(self, config):
        pass

    @abc.abstractmethod
    def set_context_from_config(self):
        pass

    @abc.abstractmethod
    def log(self, msg):
        pass


class FrameBase(object):

    def __init__(self):
        self.header = {'type': self.frame_type}
        self.body = []
        self.seq_no = 0

    @classmethod
    def create(cls, msg):
        _type = msg.type
        frame = None
        if _type == "INITIAL":
            frame = InitialFrame()
        elif _type == "PARTIAL":
            frame = BodyFrame()
        elif _type == "FINISHED":
            frame = SummaryFrame()
        else:
            return None
        frame.push(**msg.values())
        return frame

    @classmethod
    def restore(cls, seq_no, ts, **keys):
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
        frame.ts = ts
        frame.header = keys
        return frame

    def push(self, **kwargs):
        self.header.update(kwargs)

    def __repr__(self):
        return "Frame: <%s> <%s>" % (self.frame_type, self.seq_no)


class InitialFrame(FrameBase):
    frame_type = "I"

    def push(self, ts=None, seq_no=None, job_id=None, step_id=None,
             session_id=None, **kwargs):
        self.body = [msgpack.packb(kwargs)]
        self.seq_no = seq_no
        self.ts = int(ts or 0)
        self.header['job_id'] = job_id
        self.header['session_id'] = session_id
        self.header['step_id'] = step_id


class BodyFrame(FrameBase):
    frame_type = "B"

    def push(self, ts=None, seq_no=None, node=None, step_id=None,
             session_id=None, stdout=None, stderr=None, **kwargs):
        if stdout:
            self.body = stdout.splitlines()
            self.header['src'] = 'O'
        elif stderr:
            self.body = stderr.splitlines()
            self.header['src'] = 'E'
        self.seq_no = seq_no
        self.ts = int(ts or 0)
        self.header['node'] = node
        self.header['step_id'] = step_id
        self.header['session_id'] = session_id


class SummaryFrame(FrameBase):
    frame_type = "S"

    def push(self, ts=None, seq_no=None, job_id=None, step_id=None,
             session_id=None, **kwargs):
        self.body = [msgpack.packb(kwargs)]
        self.seq_no = seq_no
        self.ts = int(ts or 0)
        self.header['job_id'] = job_id
        self.header['step_id'] = step_id
        self.header['session_id'] = session_id
