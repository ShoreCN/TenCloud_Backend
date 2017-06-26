__author__ = 'Jon'

'''
所有service的父类

说明
---------------
* DB的增/删/查/改 (复杂的需要手写sql语句)
* HTTP的异步请求

'''
import json
import datetime
from tornado.gen import coroutine
from tornado.httputil import url_concat, HTTPHeaders
from tornado.httpclient import AsyncHTTPClient
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor

from utils.db import DB, REDIS
from utils.log import LOG
from utils.ssh import SSH
from utils.general import get_formats, choose_user_agent
from constant import CLUSTER_DATE_FORMAT, CLUSTER_DATE_FORMAT_ESCAPE, POOL_COUNT, HTTP_TIMEOUT, ALIYUN_DOMAIN


class BaseService():
    executor = ThreadPoolExecutor(max_workers=POOL_COUNT)

    def __init__(self):
        self.db = DB
        self.redis = REDIS
        self.log = LOG

    ############################################################################################
    # DB SELECT
    ############################################################################################
    @coroutine
    def select(self, fields=None, conds=None, params=None, ct=True, ut=True, df=None, one=False):
        '''
        :param fields 字段名, str类型, 默认为类变量fields, 可传'id, name, ...'
        :param conds  条件, list类型, 可传['id=%s', 'name=%s']
        :param params 条件值, list类型, 对应conds, 可传[1, 'foo']
        :param ct     是否获取创建时间, True/False
        :param ut     是否获取更新时间, True/False
        :param df     创建时间/更新时间的字符串格式, 可传'%Y-%m-%d %H:%M:%S'
        :param one    是否一行, True/False

        Usage::
            >>> self.select(conds=['id=%s'], params=[1], ct=False)

        :return: [{'id': 1, ...}, ...]
        '''
        sql_params = self._create_query(fields=fields, conds=conds, params=params, ct=ct, ut=ut, df=df)
        cur = yield self.db.execute(*sql_params)

        data = cur.fetchone() if one else cur.fetchall()

        return data

    def _create_query(self, fields=None, conds=None, params=None, ct=True, ut=True, df=None):
        '''创建查询语句与参数, 供db.excute执行
           create_time, update_time比较特殊, 默认都有, 不需要时ct=False, ut=False

        :return: sql or [sql, params]
        '''
        sql = "SELECT {fields} ".format(fields=fields or self.fields)

        if df is None:
            df = CLUSTER_DATE_FORMAT_ESCAPE if conds else CLUSTER_DATE_FORMAT

        if ct:
            sql += ", DATE_FORMAT(create_time, '%s') AS create_time" % df

        if ut:
            sql += ", DATE_FORMAT(update_time, '%s') AS update_time " % df

        sql += 'FROM {table} '.format(table=self.table)

        if not conds:
            sql_params = [sql]
        else:
            sql += ' WHERE ' + ' AND '.join(conds)

            sql_params = [sql, params]

        return sql_params

    ############################################################################################
    # DB ADD
    ############################################################################################
    @coroutine
    def add(self, params=None):
        '''
        :param params: hash 数据库字段:值, 可传{'name': 'foo', 'description': 'boo'}
        :return: {
            'id': cur.lastrowid,
            'update_time': datetime.datetime.now().strftime(CLUSTER_DATE_FORMAT)
        }
        '''
        fields = ','.join(params.keys())
        values = list(params.values())

        sql = "INSERT INTO {table} ({fields}) VALUES ({formats})".format(table=self.table,
                                                                         fields=fields,
                                                                         formats=get_formats(values))

        cur = yield self.db.execute(sql, values)

        return {
            'id': cur.lastrowid,
            'update_time': datetime.datetime.now().strftime(CLUSTER_DATE_FORMAT)
        }

    ############################################################################################
    # DB UPDATE
    ############################################################################################
    @coroutine
    def update(self, sets=None, conds=None, params=None):
        '''
        :param sets:   list e.g. ['name=%s', 'description=%s']
        :param conds:  list e.g. ['id in (%s, %s)']
        :param params: list e.g. ['foo', 'boo', 1, 2]
        :return:
        '''
        sql = "UPDATE {table} SET ".format(table=self.table)

        sql += ','.join(sets)

        sql += ' WHERE ' + ' AND '.join(conds)

        yield self.db.execute(sql, params)

    ############################################################################################
    # DB DELETE
    ############################################################################################
    @coroutine
    def delete(self, conds=None, params=None):
        '''
        :param conds:  list 同select 必需的
        :param params: list 同select 必需的
        :return:
        '''
        sql = " DELETE FROM {table} ".format(table=self.table)

        sql += ' WHERE ' + ' AND '.join(conds)

        yield self.db.execute(sql, params)

    ############################################################################################
    # HTTP GET
    ############################################################################################
    @coroutine
    def get(self, data=None, host=ALIYUN_DOMAIN, timeout=HTTP_TIMEOUT, headers=None):
        '''
        如果必要可以添加kwargs, 比如headers
        :param data:    dict e.g. dict(x=1, y=2)
        :param host:    str  e.g. 'http://host'
        :param timeout: int  e.g. 10
        :param headers: dict e.g. dict(Authorization='')
        :return:        e.g. {'status': 0, 'message': 'success', 'data': {}}

        Usage::
            >>> uri, data = '/api', {'x': 1}
            >>> res = yield self.get(uri, data)
        '''
        url = url_concat(host, data)

        payload = {
            'request_timeout': timeout,
            'headers': {'User-Agent': choose_user_agent()}
        }

        if headers:
            payload['headers'].update(headers)

        payload['headers'] = HTTPHeaders(payload['headers'])

        res = yield AsyncHTTPClient().fetch(url, **payload)
        data = json.loads(res.body.decode())

        return data

    ############################################################################################
    # SSH
    ############################################################################################
    @run_on_executor
    def remote_ssh(self, params, cmd):
        """ 远程控制主机
        """
        try:
            ssh = SSH(hostname=params['public_ip'], username=params['username'], passwd=params['passwd'])
            ssh.exec(cmd)
            ssh.close()
        except Exception as e:
            return str(e)