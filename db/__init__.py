from . import base, sql, helpers
from .columns import Column

dal_register = {}

def get_db(dburl):
    db_args = helpers.parse_dburl(dburl)
    if dburl not in dal_register:
        dal_register[dburl] = base.database(**db_args)
    cur_db = dal_register[dburl]
    return sql.SQLDatabase(cur_db)