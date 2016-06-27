# -*- coding: utf-8 -*-

import os
import mamonsu.lib.platform as platform


class PgsqlConfig(object):

    @staticmethod
    def default_user():
        user = os.environ.get('PGUSER') or os.environ.get('USER') or 'postgres'
        return user

    @staticmethod
    def default_pgpassword():
        password = os.environ.get('PGPASSWORD')
        return password

    @staticmethod
    def default_host():
        if platform.WINDOWS:
            host = os.environ.get('PGHOST') or 'localhost'
        if platform.LINUX:
            host = os.environ.get('PGHOST') or 'auto'
        return host

    @staticmethod
    def default_port():
        port = int(os.environ.get('PGPORT') or 5432)
        return port

    @staticmethod
    def default_app():
        app = os.environ.get('PGAPPNAME') or 'mamonsu'
        return app

    @staticmethod
    def default_db():
        database = os.environ.get('PGDATABASE') or os.environ.get('PGUSER')
        database = database or os.environ.get('USER') or 'postgres'
        return database


class DefaultConfig(PgsqlConfig):
    pass