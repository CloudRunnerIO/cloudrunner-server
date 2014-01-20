__author__ = 'Ivelin Slavov'

from unittest import TestCase
from cloudrunner.db import get_db, Column
import os


class DbTest(TestCase):

    def tearDown(self):
        self.destroy_db()

    def setUp(self):
        self.destroy_db()

    def destroy_db(self):
        try:
            os.remove('/tmp/test')
        except:
            pass

    def test_get_database(self):
        dbw = get_db('sqlite:////tmp/test')

    def test_create_database_tables(self):
        schema = {
            "organizations": {
                "id": Column('id', primary_key=True),
                "name": Column('string', length=80),
                "org_uid": Column('text'),
                "active": Column('boolean'),
            },
            "users": {
                "id": Column('id', primary_key=True),
                "username": Column('string', length=80),
                "token": Column('text'),
                "role": Column('text'),
            },
            "access_map": {
                "user_id": Column('integer'),
                "servers": Column('text'),
                "role": Column('boolean'),
            },
            "user_tokens": {
                "user_id": Column('integer'),
                "token": Column('text'),
                "expiry": Column('timestamp'),
            }
        }
        dbw = get_db('sqlite:////tmp/test')
        dbw.define_schema(schema)
        dbw.create_tables()

        getattr(dbw, 'access_map')
        ins = dbw.users.insert(username="iu", token='token-token', role='main')
        sel = len(list(dbw.users.where(username="iu")))
        self.assertEqual(ins, sel)
