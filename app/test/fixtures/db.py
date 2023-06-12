from dbClient import *
from pony import orm
import pytest
import logging


class DBMock(dbClient):
    def __init__(self):
        self.MemDB()
        self.logger = logging.getLogger(__name__)
        self.devmode = True

    def MemDB(self):
        super().dbClient.bind(provider="sqlite", filename=":memory:", create_db=True)
        orm.set_sql_debug(True)
        super().dbClient.generate_mapping(create_tables=True)
        return self

    def reset_db(self):
        self.dbClient.drop_all_tables(with_all_data=True)
        self.dbClient.disconnect()
        self.dbClient.provider = None
        self.dbClient.schema = None
