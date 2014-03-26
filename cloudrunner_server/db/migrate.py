#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed without the express
#  * permission of CloudRunner.io
#  *******************************************************/

import sys
import sqlite3

import cloudrunner
try:
    from cloudrunner import CONFIG_LOCATION, LOG_LOCATION
    from cloudrunner.util.config import Config
    CONFIG = Config(CONFIG_LOCATION)
    DB_LOC = CONFIG.users.db
except:
    if len(sys.argv) < 1:
        print "No database location found"
        sys.exit(1)
    DB_LOC = sys.argv
    if not os.path.exists(DB_LOC):
        print "No database location found"
        sys.exit(1)


def migrate():
    db = sqlite3.connect(DB_LOC)
    cur = db.cursor()

    try:
        has_org = cur.execute('SELECT * FROM Organizations').fetchone()
    except:
        print "CREATING Organizations TABLE"
        cur.execute('CREATE TABLE Organizations (id integer primary key, '
                    'name text, org_uid text, active int)')
        db.commit()

    try:
        has_users = cur.execute('SELECT * FROM Users').fetchone()
    except:
        print "CREATING Users TABLE"
        cur.execute('CREATE TABLE Users (id integer primary key, '
                    'username text, token text, org_uid text)')
        db.commit()

    try:
        has_active = cur.execute('SELECT active FROM Organizations').fetchone()
    except:
        print "CREATING COLUMN 'active' on Organizations"
        cur.execute('ALTER TABLE Organizations ADD COLUMN active int')
        db.commit()

    try:
        has_org_id = cur.execute('SELECT org_uid FROM Users').fetchone()
    except:
        print "CREATING COLUMN 'org_uid' on Users"
        cur.execute('ALTER TABLE Users ADD COLUMN org_uid text')
        db.commit()

    try:
        has_acc_map = cur.execute('SELECT * FROM AccessMap').fetchone()
    except:
        print "CREATING AccessMap TABLE"
        cur.execute('CREATE TABLE AccessMap (user_id integer, '
                    'servers text, role text)')
        db.commit()

    try:
        has_tokens = cur.execute('SELECT * FROM Tokens').fetchone()
    except:
        print "CREATING Tokens TABLE"
        cur.execute('CREATE TABLE Tokens (user_id integer, '
                    'token text, expiry timestamp)')
        db.commit()

if __name__ == '__main__':
    migrate()
