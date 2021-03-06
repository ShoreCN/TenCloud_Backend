__author__ = 'Jon'

from tornado.gen import coroutine
from handler.base import BaseHandler
from setting import settings
from utils.decorator import is_login, require, auth
from utils.general import validate_mobile, validate_id_card
from utils.context import catch
from constant import ERR_TIP, MSG, APPLICATION_STATUS, MSG_MODE, DEFAULT_ENTRY_SETTING, MSG_SUB_MODE, RIGHT, \
                     USER_PERMISSION, COMPANY_PERMISSION, ADMIN_CHANGED, EMPLOYEE_TO_ADMIN, ADMIN_TO_EMPLOYEE


class CompanyHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, is_pass):
        """
        @api {get} /api/companies/list/(-?\d+) 公司列表
        @apiName CompanyHandler
        @apiGroup Company

        @apiParam {Number} is_pass 1拒绝, 2审核中, 3通过, 4创始人, 5待加入，6获取通过的，以及作为创始人的公司列表, 7获取所有和该用户相关的公司列表

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": [
                    {"cid": 1, "company_name": "十全", "create_time": "申请时间", "update_time": "审核时间", "status": "1拒绝, 2审核中, 3通过"}
                ]
            }        """
        with catch(self):
            is_pass = int(is_pass)
            if is_pass < 1 or is_pass > 8:
                self.error("arg error, check again")
                return

            params = {
                'uid': self.current_user['id'],
                'is_pass': is_pass
            }
            data = yield self.company_service.get_companies(params)

            self.success(data)


class CompanyDetailHandler(BaseHandler):
    @auth('staff')
    @coroutine
    def get(self, id):
        """
        @api {get} /api/company/(\d+) 公司详情
        @apiName CompanyDetailHandler
        @apiGroup Company

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": [
                    {"id": 1, "name": "十全", "create_time": "申请时间", "update_time": "审核时间", "contact": "联系人", "mobile": "手机号", "description": "公司简介"}
                ]
            }        """
        with catch(self):
            data = yield self.company_service.select({'id': int(id)})

            self.success(data)


class CompanyNewHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/company/new 创建公司
        @apiName CompanyNewHandler
        @apiGroup Company

        @apiParam {String} name 公司名称
        @apiParam {String} contact 联系人
        @apiParam {String} mobile 联系方式

        @apiErrorExample {json} Error-Response:
        HTTP/1.1 400
            {
                "status": 10000/10001,
                "message": 公司已存在/公司已存在并且是员工,
                "data": {}
            }
        """
        with catch(self):
            # 参数认证
            self.guarantee('name', 'contact', 'mobile')

            validate_mobile(self.params['mobile'])

            # 公司是否存在／是否已经公司员工
            company_info = yield self.company_service.select({'name': self.params['name']}, one=True)

            if company_info:
                err_key = 'company_exists'

                employee_info = yield self.company_employee_service.select({'cid': company_info['id'], 'uid': self.current_user['id']})

                if employee_info: err_key = 'is_employee'

                self.error(status=ERR_TIP[err_key]['sts'], message=ERR_TIP[err_key]['msg'])
                return

            # 创建公司
            self.params.pop('cid', None)
            self.params.pop('token', None)
            info = yield self.company_service.add(self.params)
            yield self.company_employee_service.add(dict(cid=info['id'], uid=self.current_user['id'], status=APPLICATION_STATUS['founder'], is_admin=1))
            data = {
                'cid': info['id']
            }

            # 生成默认邀请条件
            arg = {'cid': info['id'], 'setting': DEFAULT_ENTRY_SETTING, 'code': self.company_entry_setting_service.create_code(info['id'])}
            yield self.company_entry_setting_service.add(arg)

            self.success(data)


class CompanyUpdateHandler(BaseHandler):
    @require(RIGHT['modify_company_info'])
    @coroutine
    def post(self):
        """
        @api {post} /api/company/update 更新公司
        @apiName CompanyUpdateHandler
        @apiGroup Company

        @apiUse cidHeader

        @apiParam {Number} cid 公司id
        @apiParam {String} name 公司名称
        @apiParam {String} contact 联系人
        @apiParam {String} mobile 联系方式
        @apiParam {String} image_url 企业logo

        @apiUse Success
        """
        with catch(self):
            # 参数认证
            self.guarantee('cid', 'name', 'contact', 'mobile')

            validate_mobile(self.params['mobile'])

            # 公司名字是否存在
            data = yield self.company_service.select(fields='id, name', ut=False, ct=False)
            names = [i['name'] for i in data if i['id'] != self.params['cid']]
            if self.params['name'] in names:
                err_key = 'company_name_repeat'
                self.error(status=ERR_TIP[err_key]['sts'], message=ERR_TIP[err_key]['msg'])
                return

            # 更新数据
            old = {}
            for i in data:
                if i['id'] == self.params['cid']:
                    old = i

            yield self.company_service.update(
                                                sets={
                                                    'name': self.params['name'],
                                                    'contact': self.params['contact'],
                                                    'mobile': self.params['mobile'],
                                                    'image_url': settings['qiniu_header_bucket_url'] + self.params['image_url']
                                                },
                                                conds={'id': self.params['cid']},
                                              )
            # 修改名称才通知
            if self.params['name'] != old['name']:
                employee = yield self.company_employee_service.get_employee_list(self.params['cid'], status=[APPLICATION_STATUS['accept'], APPLICATION_STATUS['founder']])
                yield self.message_service.notify_change({
                    'owners': employee,
                    'cid': self.params['cid'],
                    'old_name': old['name'],
                    'new_name': self.params['name'],
                    'admin_name': self.get_current_name(),
                })
            self.success()


class CompanyEntrySettingHandler(BaseHandler):
    @require(RIGHT['invite_new_employee'])
    @coroutine
    def get(self, cid):
        """
        @api {get} /api/company/(\d+)/entry/setting 获取员工加入条件
        @apiName CompanyEntrySettingGetHandler
        @apiGroup Company

        @apiParam {Number} cid     公司id

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": {
                    "url": "https://c.10.com/#/invite?code=65d4a0f"
                }
            }

        @apiErrorExample {json} Error-Response:
        HTTP/1.1 400
            {
                "status": 1,
                "msg": "需要管理员权限",
                "data": {}
            }
        """
        with catch(self):
            cid = int(cid)
            data = yield self.company_entry_setting_service.get_setting(cid)

            self.success(data)

    @require(RIGHT['invite_new_employee'])
    @coroutine
    def post(self, cid):
        """
        @api {post} /api/company/(\d+)/entry/setting 设置员工加入条件
        @apiName CompanyEntrySettingPostHandler
        @apiGroup Company

        @apiUse cidHeader

        @apiParam {String} setting 配置mobile,name, 暂时移除id_card

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": {
                    "url": "https://c.10.com/#/invite?code=65d4a0f"
                }
            }

        @apiErrorExample {json} Error-Response:
        HTTP/1.1 400
            {
                "status": 1,
                "msg": "需要管理员权限",
                "data": {}
            }
        """
        with catch(self):
            cid = int(cid)
            self.params['cid'] = cid
            url = yield self.company_entry_setting_service.save_setting(self.params)

            self.success({'url': url})


class CompanyEntryUrlHandler(BaseHandler):
    @require(RIGHT['invite_new_employee'])
    @coroutine
    def get(self, cid):
        """
        @api {get} /api/company/(\d+)/entry/url 获取员工加入URL
        @apiName CompanyEntryUrlHandler
        @apiGroup Company

        @apiParam {String} cid     公司id

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": {
                    "url": "https://c.10.com/#/invite?code=65d4a0f"
                }
            }

        @apiErrorExample {json} Error-Response:
        HTTP/1.1 400
            {
                "status": 1,
                "msg": "需要管理员权限",
                "data": {}
            }
        """
        with catch(self):
            cid = int(cid)

            data = yield self.company_entry_setting_service.select(fields='code', conds={'cid': cid}, one=True)

            self.success({'url': self.company_entry_setting_service.produce_url(data['code'])})


class CompanyApplicationHandler(BaseHandler):
    @coroutine
    def get(self):
        """
        @api {get} /api/company/application 员工申请加入的初始条件
        @apiName CompanyApplicationGetHandler
        @apiGroup Company

        @apiParam {String} code

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": {
                    "cid": 1,
                    "company_name": "十全",
                    "contact": "13900000000",
                    "setting": "mobile,name"
                }
            }
        """
        with catch(self):
            if not self.params['code']:
                self.error('缺少code')
                return

            info = yield self.company_service.fetch_with_code(self.params['code'])

            self.success(info)

    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/company/application 员工申请提交
        @apiName CompanyApplicationPostHandler
        @apiGroup Company

        @apiParam {String} code
        @apiParam {String} mobile
        @apiParam {String} name 可选
        @apiParam {String} id_card 暂时移除

        @apiUse Success
        """
        with catch(self):
            self.guarantee('mobile')

            validate_mobile(self.params['mobile'])

            # 检验code
            info = yield self.company_service.fetch_with_code(self.params['code'])

            if not info:
                self.error('code不合法')
                return

            for f in info['setting'].split(','):
                # 临时屏蔽身份证
                if f == 'id_card':
                    continue
                self.guarantee(f)

            # 刷新用户数据
            sets = {}
            if self.params.get('name'):
                sets['name'] = self.params['name']
            # if self.params.get('id_card'):
            #     validate_id_card(self.params['id_card'])
            #     sets['id_card'] = self.params['id_card']
            if sets:
                yield self.user_service.update(sets=sets, conds={'id': self.current_user['id']})
                yield self.make_session(self.params['mobile'])

            # 加入员工
            app_data = {
                'cid': info['cid'],
                'uid': self.current_user['id']
            }
            yield self.company_employee_service.add_employee(app_data)

            # 组装通知的消息内容
            admin_data = {
                'content': MSG['application']['admin'].format(name=self.params.get('name', ''), mobile=self.params['mobile'], company_name=info['company_name']),
                'mode': MSG_MODE['application'],
                'sub_mode': MSG_SUB_MODE['verify'],
                'tip': '{}:{}'.format(info.get('cid', ''), self.params['code'])
            }
            # 给公司管理员发送消息
            admin = yield self.company_employee_service.select(fields='uid', conds={'cid': info['cid'], 'is_admin': 1})

            # 给具有审核员工权限的人发送消息,若没有存在审核权限的用户会返回一个空tuple，为防止报错，下面做一次转换
            has_send = []
            audit = yield self.user_permission_service.select({'cid': info['cid'], 'pid': RIGHT['audit_employee']})
            for i in admin + list(audit):
                if i['uid'] not in has_send:
                    has_send.append(i['uid'])
                    admin_data['owner'] = i['uid']
                    yield self.message_service.add(admin_data)

            self.success()


class CompanyApplicationVerifyMixin(BaseHandler):
    @coroutine
    def verify(self, mode):
        yield self.company_employee_service.limit_admin(self.params['id'])

        info = yield self.company_employee_service.get_app_info(self.params['id'])

        admin = yield self.company_employee_service.select(fields='uid', conds={'cid': info['cid'], 'is_admin': 1}, ct=False, ut=False)
        audit = yield self.user_permission_service.select(fields='uid', conds={'cid': info['cid'], 'pid': RIGHT['audit_employee']}, ct=False, ut=False)
        if {'uid': self.current_user['id']} not in (admin + list(audit)):
            raise ValueError('该用户无权限审核')

        yield self.company_employee_service.verify(self.params['id'], mode)

        # 通知用户
        yield self.message_service.notify_verify({
            'owner': info['uid'],
            'admin_name': self.get_current_name(),
            'company_name': info['company_name'],
            'mode': mode,
            'tip': '{}:{}'.format(info.get('cid', ''), info.get('code', ''))
        })


class CompanyApplicationAcceptHandler(CompanyApplicationVerifyMixin):
    @require(RIGHT['audit_employee'])
    @coroutine
    def post(self):
        """
        @api {post} /api/company/application/accept 接受员工申请
        @apiName CompanyApplicationAcceptHandler
        @apiGroup Company

        @apiUse cidHeader

        @apiParam {Number} id 员工表id

        @apiUse Success
        """
        with catch(self):
            yield self.verify('accept')

            self.success()


class CompanyApplicationRejectHandler(CompanyApplicationVerifyMixin):
    @require(RIGHT['audit_employee'])
    @coroutine
    def post(self):
        """
        @api {post} /api/company/application/reject 拒绝员工申请
        @apiName CompanyApplicationRejectHandler
        @apiGroup Company

        @apiUse cidHeader

        @apiParam {Number} id 员工表id

        @apiUse Success
        """
        with catch(self):
            yield self.verify('reject')

            self.success()


class CompanyEmployeeHandler(BaseHandler):
    @auth('staff')
    @coroutine
    def get(self, cid):
        """
        @api {get} /api/company/(\d+)/employees 获取员工列表
        @apiName CompanyEmployeeHandler
        @apiGroup Company

        @apiUse Success
        """
        with catch(self):
            cid = int(cid)

            employees = yield self.company_employee_service.get_employees(cid)

            # 先根据公司设置判断是否要显示身份证信息，然后根据是否有查看身份证的权限过滤显示结果,管理员不需要过滤身份证信息
            display_flag, employees = yield self.company_entry_setting_service.filter_by_setting(employees, cid)
            if display_flag:
                is_admin = yield self.company_employee_service.select({'cid': cid, 'uid': self.current_user['id'], 'is_admin': 1}, one=True)
                if not is_admin:
                    employees = yield self.user_permission_service.filter_id_card_info(employees, cid, self.current_user['id'])
            self.success(employees)


class CompanyEmployeeDismissionHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/company/employee/dismission 员工解除公司
        @apiName CompanyEmployeeHandler
        @apiGroup Company

        @apiParam {Number} id 列表id

        @apiUse Success
        """
        with catch(self):
            yield self.company_employee_service.check_staff(cid=self.params.get('cid'), uid=self.current_user['id'])

            data = yield self.company_employee_service.select({'id': self.params['id'], 'is_admin': 1, 'uid': self.current_user['id']}, one=True)

            if data:
                self.error('管理员不能解除公司，需要先进行管理员转移')
                return

            # 缓存公司信息
            app_info = yield self.company_employee_service.get_app_info(self.params['id'])

            # 解除员工和公司的关系
            yield self.company_employee_service.delete(conds={'id': self.params['id'], 'uid': self.current_user['id']})

            # 删除改用户权限
            arg = {
                'uid': self.current_user['id'],
                'cid': app_info['cid']
            }
            yield self.user_permission_service.delete(conds=arg)
            yield self.user_access_server_service.delete(conds=arg)
            yield self.user_access_project_service.delete(conds=arg)
            yield self.user_access_filehub_service.delete(conds=arg)
            company_user = USER_PERMISSION.format(cid=int(self.params.get('cid')), uid=int(self.current_user['id']))
            self.redis.hdel(COMPANY_PERMISSION, company_user)

            # 将此员工解除公司的消息通知给管理员
            content = MSG['leave']['demission'].format(name=self.get_current_name(),
                                                       mobile=self.current_user['mobile'],
                                                       company_name=app_info['company_name'])
            admin_info = yield self.company_employee_service.select(fields='uid', conds={'cid': app_info['cid'], 'is_admin': 1})
            for info in admin_info:
                yield self.message_service.add({
                    'owner': info['uid'],
                    'content': content,
                    'mode': MSG_MODE['leave']})

            self.success()

class CompanyAdminTransferHandler(BaseHandler):
    @auth('admin')
    @coroutine
    def post(self):
        """
        @api {post} /api/company/admin/transfer 转移管理员
        @apiName CompanyAdminTransferHandler
        @apiGroup Company

        @apiUse cidHeader

        @apiParam {Number} uid 新管理人员id
        @apiParam {Number} cid 公司id

        @apiUse Success
        """
        with catch(self):
            # 检查参数是否完整合法
            self.guarantee('uid', 'cid')

            self.params['admin_id'] = self.current_user['id']

            yield self.company_employee_service.transfer_adimin(self.params)

            # 管理员变更之后需要刷新用户权限变更标记
            company_user_src = USER_PERMISSION.format(cid=self.params.get('cid'), uid=self.current_user['id'])
            self.redis.hset(ADMIN_CHANGED, company_user_src, ADMIN_TO_EMPLOYEE)
            company_user_dst = USER_PERMISSION.format(cid=self.params.get('cid'), uid=self.params.get('uid'))
            self.redis.hset(ADMIN_CHANGED, company_user_dst, EMPLOYEE_TO_ADMIN)

            self.success()


class CompanyApplicationDismissionHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/company/application/dismission 管理员解除员工
        @apiName CompanyApplicationDismissionHandler
        @apiGroup Company

        @apiUse cidHeader

        @apiParam {Number} id 列表id

        @apiUse Success
        """
        with catch(self):
            # 只有管理员才有解雇员工的权限
            yield self.company_employee_service.check_admin(self.params.get('cid'), self.current_user['id'])


            yield self.company_employee_service.limit_admin(self.params['id'])

            user_info = yield self.company_employee_service.select(
                                                            fields='uid',
                                                            conds={'id': self.params['id']},
                                                            one=True
                                                            )
            if not user_info:
                self.error('非公司员工')
                return

            # 删除改用户权限
            arg = {
                'uid': user_info['uid'],
                'cid': self.params.get('cid')
            }
            yield self.user_permission_service.delete(conds=arg)
            yield self.user_access_server_service.delete(conds=arg)
            yield self.user_access_project_service.delete(conds=arg)
            yield self.user_access_filehub_service.delete(conds=arg)

            company_user = USER_PERMISSION.format(cid=int(self.params.get('cid')), uid=int(self.current_user['id']))
            self.redis.hdel(COMPANY_PERMISSION, company_user)

            yield self.company_employee_service.delete({'id': self.params['id']})

            self.success()


class CompanyApplicationWaitingHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/company/application/waiting 待加入公司
        @apiName CompanyApplicationWaitingHandler
        @apiGroup Company

        @apiParam {String} code
        """
        with catch(self):
            data = yield self.company_entry_setting_service.select(fields='cid', conds={'code': self.params['code']}, one=True)

            if not data:
                self.error('邀请码已失效')
                return

            conds = {'cid': data['cid'], 'uid': self.current_user['id']}
            sets  = {'status': APPLICATION_STATUS['waiting']}

            is_exist = yield self.company_employee_service.select(conds=conds, one=True)

            if not is_exist:
                sets.update(conds)
                yield self.company_employee_service.add(sets)
            elif is_exist['status'] == APPLICATION_STATUS['reject']:
                yield self.company_employee_service.update(sets=sets, conds=conds)
            elif is_exist['status'] != APPLICATION_STATUS['waiting']:
                self.error('请勿重复提交加入公司申请')
                return

            self.success()


class ComapnyEmployeeSearchHandler(BaseHandler):
    @auth('staff')
    @coroutine
    def post(self):
        """
        @api {post} /api/company/employee/search 员工搜索
        @apiName CompanyEmployeeSearchHandler
        @apiGroup Company

        @apiUse cidHeader
        @apiParam {String} employee_name 搜索名字or手机号码
        @apiParam {Number} status 是否通过 1拒绝, 2审核中, 3通过, 4创始人, 传空获取全部

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": {
                    "id": 1,
                    "name": "十全",
                    "image_url": "a.com",
                    "mobile": "1399999999"
                }
            }
        """
        with catch(self):
            # 先获取公司下的所有员工信息，然后再进行加工筛选
            cid = self.params.get('cid')
            data = yield self.company_employee_service.get_employee_list_detail(cid=cid)

            # 先根据公司设置判断是否要显示身份证信息，然后根据是否有查看身份证的权限过滤显示结果（管理员不依赖于权限，不过滤身份证信息）
            display_flag, data = yield self.company_entry_setting_service.filter_by_setting(data, cid)
            if display_flag:
                is_admin = yield self.company_employee_service.select({'cid': cid, 'uid': self.current_user['id'], 'is_admin': 1}, one=True)
                if not is_admin:
                    data = yield self.user_permission_service.filter_id_card_info(data, cid, self.current_user['id'])

            params = {
                'cid': self.params['cid'],
                'status': self.params.get('status'),
                'employee_name': self.params.get('employee_name'),
                'data': data

            }

            search_data = data
            if params.get('status'):
                if params['status'] == APPLICATION_STATUS['accept']:
                    search_data = [
                        i for i in data if
                        (i['status'] == params['status'] or i['status'] == APPLICATION_STATUS['founder'])
                    ]
                else:
                    search_data = [i for i in data if i['status'] == params['status']]
            if params.get('employee_name'):
                search_data = self.company_employee_service.search_by_name(params)

            search_data = sorted(search_data, key=lambda x: x['create_time'], reverse=False)
            self.success(search_data)


class CompanyEmployeeStatusHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self):
        """
        @api {get} /api/company/employee/status 查询员工状态
        @apiName CompanyEmployeeStatusHandler
        @apiGroup Company

        @apiParam {Number} id 公司ID

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": {
                    "status": 1,
                    "is_admin": 0
                }
            }
        """
        with catch(self):
            data = yield self.company_employee_service.select(
                        fields='status, is_admin', conds={'uid': self.current_user['id'], 'cid': self.params.get('id')},
                        ct=False, ut=False, one=True
            )

            self.success(data)
