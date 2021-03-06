__author__ = 'Jon'

from tornado.gen import coroutine
from service.base import BaseService
from constant import APPLICATION_STATUS, FULL_DATE_FORMAT, ERR_TIP
from utils.general import fuzzyfinder
from utils.error import AppError


class CompanyEmployeeService(BaseService):
    table  = 'company_employee'
    fields = 'id, cid, uid, is_admin, status'

    @coroutine
    def check_admin(self, cid, uid):
        ''' 是否管理员
        :param cid: 公司id
        :param uid: 用户id
        '''
        data = yield self.select({'cid': cid, 'uid': uid, 'is_admin': 1}, one=True)

        if not data:
            raise AppError(ERR_TIP['not_this_company_admin']['msg'], ERR_TIP['not_this_company_admin']['sts'])

    @coroutine
    def check_admin_bool(self, cid, uid):
        ''' 是否管理员
        :param cid: 公司id
        :param uid: 用户id
        '''
        data = yield self.select({'cid': cid, 'uid': uid, 'is_admin': 1}, one=True)

        resp = True
        if not data:
            resp = False
        return resp

    @coroutine
    def check_staff(self, cid, uid):
        ''' 是否公司员工
        :param cid: 公司id
        :param uid: 用户id
        '''
        data = yield self.select({'cid': cid, 'uid': uid, 'status': [APPLICATION_STATUS['accept'], APPLICATION_STATUS['founder']]}, one=True)

        if not data:
            raise AppError(ERR_TIP['not_this_company_employee']['msg'], ERR_TIP['not_this_company_employee']['sts'])

    @coroutine
    def limit_admin(self, id):
        ''' 管理员不能对自己进行，允许/拒绝/解除
        :param id: 员工表id
        '''
        data = yield self.select({'id': id, 'is_admin': 1}, one=True)

        if data:
            raise AppError(ERR_TIP['admin_operate_themselves']['msg'], ERR_TIP['admin_operate_themselves']['sts'])

    @coroutine
    def add_employee(self, params):
        ''' 添加员工，需先判断员工之前的状态
        :param params: {'cid', 'uid'}
        :return: 审核中或审核通过会抛出异常，已拒绝或新增会更新数据库
        '''
        data = yield self.select(fields='status', conds={'cid': params['cid'], 'uid': params['uid']}, one=True)

        status = data['status'] if data else ''

        if status == APPLICATION_STATUS['process']:
            raise AppError(ERR_TIP['have_submit_application']['msg'], ERR_TIP['have_submit_application']['sts'])
        elif status in [APPLICATION_STATUS['accept'], APPLICATION_STATUS['founder']]:
            raise AppError(ERR_TIP['employee_already']['msg'], ERR_TIP['employee_already']['sts'])
        elif status in [APPLICATION_STATUS['reject'], APPLICATION_STATUS['waiting']]:
            yield self.update(sets={'status': APPLICATION_STATUS['process']}, conds={'cid': params['cid'], 'uid': params['uid']})
        else:
            params = {
                'status': APPLICATION_STATUS['process'],
                'uid': params['uid'],
                'cid': params['cid']
            }
            yield self.add(params)

    @coroutine
    def get_app_info(self, id):
        ''' 通过员工表id获取一些信息
        :param id: 员工表id
        :return: {'company_name', 'cid', 'uid', 'code'}
        '''
        sql = '''
            SELECT c.name AS company_name, c.id AS cid, ce.uid AS uid, ces.code AS code
            FROM company c
            JOIN company_employee ce ON c.id=ce.cid
            JOIN company_entry_setting ces ON c.id=ces.cid
            WHERE ce.id=%s
        '''
        cur = yield self.db.execute(sql, id)

        info = cur.fetchone()

        return info

    @coroutine
    def verify(self, id, mode):
        ''' 通过或拒绝员工
        :param id: 员工表id
        :param mode: APPLICATION_STATUS的key
        '''
        is_process = yield self.select({'id': id, 'status': APPLICATION_STATUS['process']})

        if not is_process:
            raise AppError(ERR_TIP['repeated_action']['msg'], ERR_TIP['repeated_action']['sts'])

        yield self.update(sets={'status': APPLICATION_STATUS[mode]}, conds={'id': id})

    @coroutine
    def get_employees(self, cid):
        ''' 获取员工列表
        :param cid: 公司id
        '''
        sql = '''
            SELECT ce.id, u.id AS uid, u.name, u.mobile, u.image_url,DATE_FORMAT(ce.create_time, %s) AS create_time, DATE_FORMAT(ce.update_time, %s) AS update_time, ce.status, ce.is_admin
            FROM company_employee ce
            JOIN user u ON ce.uid = u.id
            WHERE ce.cid = %s and ce.status != 5
        '''
        cur = yield self.db.execute(sql, [FULL_DATE_FORMAT, FULL_DATE_FORMAT, cid])
        data = cur.fetchall()

        return data

    @coroutine
    def get_employee_list(self, cid, is_admin=None, status=None):
        '''
        获取员工id列表，可通过指定is_admin, status参数过滤
        :param cid: 公司id
        :param is_admin: 0代表普通用户，1代表管理员
        :param status: 用户状态
        :return: list
        '''
        conds = {'cid': cid}
        if is_admin is not None:
            conds['is_admin'] = is_admin
        if status is not None:
            conds['status'] = status

        data = yield self.select(conds=conds, fields='uid')
        employee_list = [i['uid'] for i in data]
        return employee_list

    @coroutine
    def transfer_adimin(self, params):
        ''' 只有管理员才能转换管理员
        :param params: {'admin_id', 'cid', 'uids'}
        '''
        yield self.update(sets={'is_admin': 0}, conds={'uid': params['admin_id'], 'cid': params['cid']})

        yield self.update(sets={'is_admin': 1},
                          conds={'uid': params['uid'], 'cid': params['cid']})

    @coroutine
    def get_employee_list_detail(self, cid):

        sql = """
                SELECT ce.id, u.id AS uid, u.name, u.email, u.mobile, u.image_url,ce.status, ce.is_admin,DATE_FORMAT(ce.create_time, %s) AS create_time, DATE_FORMAT(ce.update_time, %s) AS update_time
                FROM user AS u JOIN company_employee AS ce ON ce.uid = u.id WHERE ce.cid = %s and ce.status != 5
              """
        cur = yield self.db.execute(sql, [FULL_DATE_FORMAT, FULL_DATE_FORMAT, cid])
        return cur.fetchall()

    @staticmethod
    def search_by_name(params):
        names = []
        sorted_data = dict()

        search_key = 'name' if params['employee_name'].isalpha() else 'mobile'
        for i in params['data']:
            key = i[search_key]
            sorted_data[key] = i
            names.append(key)

        name_find = fuzzyfinder(params['employee_name'], names)
        final_data = [sorted_data[key] for key in names if key in name_find]
        return final_data
