__author__ = 'Ivelin Slavov'

SQL_TYPES = {
    'boolean': 'CHAR(1)',
    'string': 'VARCHAR(%(length)s)',
    'text': 'LONGTEXT',
    'blob': 'LONGBLOB',
    'integer': 'INTEGER',
    'bigint': 'BIGINT',
    'float': 'FLOAT',
    'double': 'DOUBLE',
    'decimal': 'NUMERIC(%(precision)s,%(scale)s)',
    'date': 'DATE',
    'time': 'TIME',
    'datetime': 'DATETIME',
    'timestamp': 'TIMESTAMP',
    'id': 'INTEGER AUTOINCREMENT NOT NULL',
    'reference': 'INT, INDEX %(index_name)s (%(field_name)s), FOREIGN KEY '
    '(%(field_name)s) REFERENCES %(foreign_key)s '
    'ON DELETE %(on_delete_action)s',
}

SQL_OVERRIDES = {
    'postgres': {
    'id': 'INTEGER SERIAL NOT NULL',
    'text': 'TEXT',
    },
    'sqlite3': {
    'id': 'INTEGER NOT NULL'
    },
    'sqlite': {
    'id': 'INTEGER NOT NULL'
    }
}


def column_to_sql(db, column):

    col_def = None
    if db.dbname in SQL_OVERRIDES:
        # Check for override
        col_def = SQL_OVERRIDES[db.dbname].get(column.col_type)

    if not col_def:
        col_def = SQL_TYPES.get(column.col_type, None)

    if col_def is None:
        raise Exception("Cannot define column as %s. "
                        "Supported types are %s" %
                       (column.col_type, SQL_TYPES.keys()))
    sql_def = col_def % column.kwargs

    if column.primary_key:
        sql_def += " PRIMARY KEY"

    if column.autoincrement and db.supports('autoincrement'):
        sql_def += " AUTOINCREMENT"

    if not column.null:
        sql_def += " NOT NULL"

    if column.default is not None:
        sql_def += " DEFAULT %s" % (column.default)

    return sql_def


def generate_table_str(db, table_name, **kwargs):
    """
    Generate create table sql:
        >>> generate_table_str('mytable2', \
        id=Column('integer', primary_key=True), \
        name=Column('string', length=32))
        'CREATE TABLE mytable2 (id INT PRIMARY KEY NOT NULL,\\nname VARCHAR(32))'
    """

    create_table_tpl = "CREATE TABLE %(table_name)s (%(column_definitions)s)"
    column_definitions = ", ".join(
        "%s %s" % (name, column_to_sql(db, column))
        for name, column in kwargs.items()
    )

    create_table_str = create_table_tpl % {
        "table_name": table_name,
        "column_definitions": column_definitions
    }
    return create_table_str


def proxy_for_table(func, table_name):
    def wrapped(*args, **kwargs):
        return func(table_name, *args, **kwargs)
    return wrapped


class Table(object):

    def __init__(self, db, tablename, schema=None):
        self.tablename = tablename
        self.db = db
        self.schema = schema

    def __getattr__(self, item):
        func = getattr(self.db, item)
        if item in ['select', 'insert', 'update', 'delete', 'where',
                    'insert_multiple']:
            return proxy_for_table(func, table_name=self.tablename)
        return func

    def exists(self):
        try:
            self.select(limit=1)
        except Exception as exc:
            return False
        return True

    def create(self):
        if self.schema is None:
            raise Exception('There is no schema defined for table "%s"' % (
                self.tablename
            ))

        if self.exists():
            raise Exception('Table %s already exist' % (self.tablename))

        table_str = generate_table_str(db=self.db,
                                       table_name=self.tablename,
                                       **self.schema)
        return self.db.query(table_str)

    def join(self, table):
        pass


class SQLDatabase(object):

    def __init__(self, db_conn):
        self.db = db_conn
        self.schema = None

    def define_schema(self, schema):
        if self.schema is not None:
            raise Exception("A schema is already defined for this database")
        self.schema = schema
        for key, sch in self.schema.items():
            setattr(self, key, Table(self.db, key, sch))

    def create_tables(self):
        for table_name in self.schema:
            table = getattr(self, table_name)
            if not table.exists():
                table.create()
