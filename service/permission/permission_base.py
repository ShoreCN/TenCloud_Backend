from collections import defaultdict

from tornado.gen import coroutine

from service.base import BaseService
from constant import  PERMISSIONS
from utils.general import get_in_formats


class PermissionBaseService(BaseService):
    table = ''
    fields = ''
    resource = ''

    @staticmethod
    def merge_servers(data):

        """
        :param [
                  {"a":{"b":[1,2]}},
                  {"a":{"b":[3,4]}},
                  {"c":{"d":[1,2]}},
                ]
        :return: {
                    "a":{
                        "b":[1,2,3,4]
                        }
                    },
                    "c":{
                        "d":[1,2]
                        }
                    }
        """
        if len(data) == 0:
            return

        res = list()
        result = defaultdict(dict)

        for d in data:
            provider, region = d['provider'], d['region_name']

            if region not in result[provider]:
                result[provider][region] = []

            result[provider][region].append(d)
        tmp = dict(result.items())
        for k in tmp:
            a_regions = list()
            tmp_provider = {
                'name': k,
                'data': []
            }
            for x in tmp[k]:
                tmp_region = {
                    'name': x,
                    'data': tmp[k][x]
                }
                a_regions.append(tmp_region)
            tmp_provider['data'] = a_regions
            res.append(tmp_provider)
        return res

    @staticmethod
    def merge_permissions(data):
        if len(data) == 0:
            return

        res = list()
        result = dict()
        for column in data:
            tmp = {
                'id': column['id'],
                'name': column['name'],
                'group': column['group']
            }
            if column['group'] not in result.keys():
                result[column['group']] = [tmp]
            else:
                result[column['group']].append(tmp)
        # 企业资料，员工管理，权限模版划分为企业管理临时方案
        temp_data = {
            'name': '企业管理',
            'data': []
        }
        for k in result:
            tmp_dict = {
                'name': PERMISSIONS[k],
                'data': result[k]
            }
            if k in [3, 4, 5]:
                temp_data['data'].append(tmp_dict)
                continue
            res.append(tmp_dict)
        res.append(temp_data)
        return res

    @coroutine
    def fetch_instance_info(self, extra=''):
        sql = """
                SELECT i.status, i.public_ip, i.provider, i.region_name, s.id as sid, s.name FROM instance i 
                JOIN server s USING(instance_id) {extra}
              """.format(extra=extra)
        cur = yield self.db.execute(sql)
        info = cur.fetchall()
        return info

    @coroutine
    def check_right(self, params):
        ''' 检查ids是否为员工功能权限/数据权限的子集
        :param params: {'uid', 'cid', 'ids'}
        :return: 如果权限不够，raise
        '''
        result = yield self.select(fields=self.resource, conds={'uid': params['uid'], 'cid': params['cid']})
        self.issub(params.get('ids'), result)

    def issub(self, ids, db_data):
        ''' ids是否是数据库数据的子集
        :param ids:    list, e.g. [1, 2]
        :param db_data: list, e.g. [{'sid/pid/...'},..]
        '''
        limits = set([d[self.resource] for d in db_data])

        ids = set(ids) if isinstance(ids, (list, tuple)) else set([ids])

        if not ids.issubset(limits):
            raise ValueError('您没有操作的权限')

    @coroutine
    def get_by_permission(self, fields, table, where_fields, where_table, params):
        sql = """
                SELECT {fields} FROM {table} AS a JOIN {where_table} AS b 
                ON {where_fields} WHERE b.uid=%s AND b.cid=%s
              """.format(fields=fields, table=table, where_fields=where_fields, where_table=where_table)

        cur = yield self.db.execute(sql, params)
        data = cur.fetchall()
        return data

    @coroutine
    def check_exist(self, table, ids, extra=''):
        if not ids:
            return ''
        ids = [i for i in ids.split(',')]
        conds = get_in_formats('id', ids)
        sql = """
        SELECT id FROM {table} WHERE  {conds} {extra}
        """.format(table=table, conds=conds, extra=extra)
        cur = yield self.db.execute(sql, ids)
        data = ','.join([str(i['id']) for i in cur.fetchall()])
        return data
