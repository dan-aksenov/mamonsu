# -*- coding: utf-8 -*-

import logging
import re
import time
from mamonsu.plugins.pgsql.pool import Pooler


class PostgresInfo(object):

    QueryCommonInfo = (
        """
select
    version(),
    (now() - pg_postmaster_start_time())::time,
    round(sum(blks_hit)*100/sum(blks_hit+blks_read), 2)
from
    pg_catalog.pg_stat_database """,
        ('version', 'uptime', 'cache hit')
    )

    QueryConnections = (
        """
select count(*), 'total' from pg_catalog.pg_stat_activity
union all
select count(*), 'waiting' from pg_catalog.pg_stat_activity where waiting
union all
select count(*), 'active' from pg_catalog.pg_stat_activity
    where state = 'active'
union all
select count(*), 'idle' from pg_catalog.pg_stat_activity where state = 'idle'
union all
select count(*), 'idle in transaction' from pg_catalog.pg_stat_activity
    where state = 'idle in transaction'
"""
    )

    QueryRate = (
        """
select
    date_part('epoch', now()),
    sum(xact_commit),
    sum(xact_rollback)
from pg_catalog.pg_stat_database
"""
    )

    QueryPgSettings = (
        """
select
    name,
    setting,
    unit,
    context,
    vartype,
    source,
    boot_val,
    reset_val
from pg_catalog.pg_settings """,
        ('name', 'setting', 'unit', 'context',
            'vartype', 'source', 'boot_val', 'reset_val'),
        ({
            'Data safe': [
                'fsync', 'synchronous_commit',
                'synchronous_standby_names'
            ],
            'Memory': [
                'shared_buffers', 'huge_pages', 'work_mem',
                'temp_buffers', 'max_connections'
            ],
            'Autovacuum': [
                'autovacuum', 'autovacuum_max_workers',
                'autovacuum_naptime', 'autovacuum_vacuum_cost_delay',
                'autovacuum_analyze_scale_factor',
                'autovacuum_analyze_threshold',
                'autovacuum_vacuum_scale_factor',
                'autovacuum_vacuum_threshold'
            ],
            'BgWriter': [
                'bgwriter_delay',
                'bgwriter_lru_maxpages',
                'bgwriter_lru_multiplier'
            ],
            'KeepAlive': [
                'tcp_keepalives_count',
                'tcp_keepalives_idle',
                'tcp_keepalives_interval'
            ],
            'Libraries': [
                'shared_preload_libraries',
                'session_preload_libraries',
                'local_preload_libraries'
            ]
        })
    )

    QueryDBList = (
        """
select
    d.datname,
    case when pg_catalog.has_database_privilege(d.datname, 'CONNECT')
         then pg_catalog.pg_size_pretty(pg_catalog.pg_database_size(d.datname))
         else 'No Access'
    end,
    pg_catalog.pg_get_userbyid(d.datdba),
    pg_catalog.pg_encoding_to_char(d.encoding),
    d.datcollate,
    d.datctype,
    pg_catalog.array_to_string(d.datacl, E'\n'),
    t.spcname,
    pg_catalog.shobj_description(d.oid, 'pg_database')
from pg_catalog.pg_database d
  join pg_catalog.pg_tablespace t on d.dattablespace = t.oid
order by 1 """,
        ('name', 'size', 'owner', 'encoding', 'collate',
            'ctype', 'privileges', 'tablespace', 'description')
    )

    def __init__(self, args):
        self.args = args
        logging.info('Test connection...')
        self.connected = self._is_connection_work()
        if not self.connected:
            return
        logging.info('Collect pg common info...')
        self.common_info = self._collect_query(self.QueryCommonInfo)
        logging.info('Collect rate.,.')
        self.rate = self._collect_rate()
        logging.info('Collect connection info...')
        self.connections = self._collect_connections()
        logging.info('Collect pg_setting info...')
        self.settings = self._collect_query(self.QueryPgSettings)
        logging.info('Collect database list...')
        self.dblist = self._collect_query(self.QueryDBList)
        logging.info('Collect biggest table...')
        self.biggest_tables = self._collect_biggest()

    def collect(self):
        info = self.printable_info()
        logging.error("\n{0}\n".format(self.store_raw()))
        return info

    def _is_connection_work(self):
        try:
            Pooler.query('select 1')
            return True
        except Exception as e:
            logging.error('Test query error: {0}'.format(e))
            return False

    _suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']

    def _humansize_bytes(self, nbytes):
        if nbytes == 0:
            return '0 B'
        i = 0
        while nbytes >= 1024 and i < len(self._suffixes)-1:
            nbytes /= 1024.
            i += 1
        f = ('%.2f' % nbytes).rstrip('0').rstrip('.')
        return '%s %s' % (f, self._suffixes[i])

    def _humansize(self, value):
        m = re.search('(\d+) (\S+)', value)
        if m is None:
            return value
        val, suff = m.group(1), m.group(2)
        val, suff = int(val), suff.upper()
        if suff == 'S':
            return value
        if suff == 'MS':
            return value
        if suff == 'B':
            return self._humansize_bytes(val)
        if suff == 'KB':
            return self._humansize_bytes(val*1024)
        if suff == '4KB':
            return self._humansize_bytes(val*1024*4)
        if suff == '8KB':
            return self._humansize_bytes(val*1024*8)
        if suff == '16KB':
            return self._humansize_bytes(val*1024*16)
        if suff == 'MB':
            return self._humansize_bytes(val*1024*1024)
        if suff == 'GB':
            return self._humansize_bytes(val*1024*1024*1024)
        if suff == 'TB':
            return self._humansize_bytes(val*1024*1024*1024*1024)
        return value

    def store_raw(self):

        def format_obj(val):
            if isinstance(val, list) or isinstance(val, tuple):
                result = ''
                for row in val:
                    result += format_obj(row)
                result += "\n"
                return result
            if isinstance(val, dict):
                result = ''
                for key in val:
                    result += '{0}:{1}\n'.format(key, format_obj(val[key]))
                return result
            return '{0:10}|'.format(val)

        def format_out(info, val):
            return "# {0} ##################################\n{1}\n".format(
                info, val)

        if not self.connected:
            out = format_out('Test connection', 'Failed')
            return out
        out = format_out('PG COMMON', format_obj(self.common_info))
        out += format_out('PG RATE', format_obj(self.rate))
        out += format_out('PG CONNECTIONS', format_obj(self.connections))
        out += format_out('PG SETTINGS', format_obj(self.settings))
        out += format_out('PG DBLIST', format_obj(self.dblist))
        out += format_out('TABLES LIST', format_obj(self.biggest_tables))
        return out

    def printable_info(self):

        def format_header(info):
            return "\n###### {0:20} ###########################\n".format(info)

        def format_out(key, val):
            return "{0:40s}|    {1}\n".format(key, val)

        out = ''
        if not self.connected:
            out += format_header('PGSQL Error')
            out += format_out('Test connection', 'Failed')
            return out
        out += format_header('PostgreSQL')
        out += format_out('version', self.common_info[1][0])
        out += format_out('uptime', self.common_info[1][1])
        out += format_out('cache hit', '{0} %'.format(self.common_info[1][2]))
        out += format_out('tps', self.rate['_TPS'])
        out += format_out('rollbacks', self.rate['_ROLLBACKS'])
        out += format_header('Connections')
        for info in self.connections:
            count, name = info
            out += format_out(name, count)
        for key in self.QueryPgSettings[2]:
            out += format_header(key)
            for row in self.settings:
                for name in self.QueryPgSettings[2][key]:
                    if row[0] == name:
                        val = row[1]
                        if row[2] is not None:
                            val += ' {0}'.format(row[2])
                            val = self._humansize(val)
                        out += format_out(
                            name, val)
        out += format_header('Database sizes')
        for i, row in enumerate(self.dblist):
            if i == 0:
                continue
            out += format_out(row[0], self._humansize(row[1]))
        out += format_header('Biggest tables')
        for i, key in enumerate(sorted(
                self.biggest_tables,
                key=self.biggest_tables.__getitem__,
                reverse=True)):
            if i > 20:
                break
            out += format_out(
                key, self._humansize_bytes(self.biggest_tables[key]))
        return out

    def _collect_query(self, query_desc):
        result = [query_desc[1]]
        try:
            for row in Pooler.query(query_desc[0]):
                result.append(row)
        except Exception as e:
            logging.error("Query {0} error: {1}".format(query_desc[0], e))
        return result

    def _collect_rate(self):
        result = {}
        result['_TPS'], result['_ROLLBACKS'] = '', ''
        try:
            result['row_1'] = Pooler.query(self.QueryRate)[0]
            time.sleep(2)
            result['row_2'] = Pooler.query(self.QueryRate)[0]
            exec_time = float(result['row_2'][0] - result['row_1'][0])
            result['_TPS'] = float(
                result['row_2'][1] - result['row_1'][1]) / exec_time
            result['_ROLLBACKS'] = float(
                result['row_2'][2] - result['row_1'][2]) / exec_time
        except Exception as e:
            logging.error('Query rate error: {0}'.format(e))
        return result

    def _collect_connections(self):
        result = []
        try:
            result = Pooler.query(self.QueryConnections)
        except Exception as e:
            logging.error('Query connections error: {0}'.format(e))
        return result

    def _collect_biggest(self):
        result = {}
        for info_dbs in Pooler.query('select datname \
                from pg_catalog.pg_database where datistemplate = false'):
            try:
                for info_sizes in Pooler.query("select n.nspname, c.relname, \
                        pg_catalog.pg_total_relation_size(c.oid) as size from \
                        pg_catalog.pg_class c \
                            left join pg_catalog.pg_namespace n \
                            on n.oid = c.relnamespace \
                        where c.relkind IN ('r','v','m','S','f','') \
                        order by size \
                        desc", info_dbs[0]):
                    table_name = '{0}.{1}.{2}'.format(
                        info_dbs[0], info_sizes[0], info_sizes[1])
                    result[table_name] = info_sizes[2]
            except Exception as e:
                logging.error("Connect to db {0} error: {1}".format(
                    info_dbs[0], e))
        return result
