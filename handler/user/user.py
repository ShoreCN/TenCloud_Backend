__author__ = 'Jon'

import traceback

from tornado.gen import Task, coroutine
from sdk import GeetestLib
import bcrypt
import json
from constant import AUTH_CODE, AUTH_CODE_ERROR_COUNT, AUTH_CODE_ERROR_COUNT_LIMIT, AUTH_FAILURE_TIP, AUTH_LOCK, \
    AUTH_LOCK_TIMEOUT, AUTH_LOCK_TIP, COOKIE_EXPIRES_DAYS, SMS_FREQUENCE_LOCK, SMS_FREQUENCE_LOCK_TIMEOUT, \
    SMS_FREQUENCE_LOCK_TIP, SMS_TIMEOUT, SMS_SENT_COUNT, SMS_SENT_COUNT_LIMIT, SMS_SENT_COUNT_LIMIT_TIP, \
    SMS_SENT_COUNT_LIMIT_TIMEOUT, SMS_NEED_GEETEST_COUNT, ERROR_CODE
from handler.base import BaseHandler
from setting import settings
from utils.datetool import seconds_to_human
from utils.decorator import is_login
from utils.general import gen_random_code, validate_auth_code, validate_mobile, validate_user_password


class UserBase(BaseHandler):
    @coroutine
    def validate_captcha(self, challenge='', validate='', seccode=''):
        gt = GeetestLib(settings['gee_id'], settings['gee_key'])
        status = yield Task(self.redis.get, gt.GT_STATUS_SESSION_KEY)
        if int(status) == 1:
            result = gt.success_validate(challenge, validate, seccode)
        else:
            result = gt.failback_validate(challenge, validate, seccode)
        if not result:
            return False
        return True

    @coroutine
    def make_session(self, mobile):
        data = yield self.user_service.select(conds=['mobile=%s'], params=[mobile], one=True)
        if not data:
            yield self.user_service.add({'mobile': mobile})
            data = yield self.user_service.select(conds=['mobile=%s'], params=[mobile], one=True)
        # 设置cookie
        self.set_secure_cookie('user_id', str(data['id']), expires_days=COOKIE_EXPIRES_DAYS)
        # 设置session
        yield self.set_session(data['id'], data)


class NeedSMSMixin(BaseHandler):
    """ 需要手机验证码操作的基类
    """
    def initialize(self):
        self.auth_code_key = ''
        self.auth_lock_key = ''
        self.err_count_key = ''

    @coroutine
    def check(self, mobile, auth_code):
        # 检查auth_lock
        self.auth_lock_key = AUTH_LOCK.format(mobile=mobile)

        has_lock = yield Task(self.redis.get, self.auth_lock_key)
        if has_lock:
            self.error(AUTH_LOCK_TIP)
            return False

        # 认证
        self.auth_code_key = AUTH_CODE.format(mobile=mobile, auth_code=auth_code)
        self.err_count_key = AUTH_CODE_ERROR_COUNT.format(mobile=mobile)

        is_exist = yield Task(self.redis.get, self.auth_code_key)
        if not is_exist:
            err_count = yield Task(self.redis.get, self.err_count_key)
            err_count = int(err_count) if err_count else 0
            err_count += 1

            if err_count >= AUTH_CODE_ERROR_COUNT_LIMIT:
                yield Task(self.redis.setex, self.auth_lock_key, AUTH_LOCK_TIMEOUT, '1')
                yield Task(self.redis.delete, self.err_count_key)
                self.error(AUTH_LOCK_TIP)
            else:
                yield Task(self.redis.set, self.err_count_key, err_count)
                self.error(AUTH_FAILURE_TIP.format(count=err_count))

            return False

        return True

    @coroutine
    def clean(self):
        """ 清除auth_code && 登陆lock && 登陆错误次数
        """
        yield Task(self.redis.delete, self.auth_code_key, self.auth_lock_key, self.err_count_key)


class UserSMSHandler(UserBase):
    @coroutine
    def post(self):
        """
        @api {post} /api/user/sms 发送手机验证码
        @apiName UserSMSHandler
        @apiGroup User

        @apiParam {String} mobile
        @apiParam {String} geetest_challenge
        @apiParam {String} geetest_validate
        @apiParam {String} geetest_seccode

        @apiSuccessExample {json} Success-Response:
          HTTP/1.1 200 ok
            {
                "sms_count": int
            }
        """
        try:
            mobile = self.params['mobile']
            # 参数认证
            validate_mobile(mobile)

            # 检查手机一分钟只能发送一次锁
            sms_frequence_lock = SMS_FREQUENCE_LOCK.format(mobile=mobile)

            has_lock = yield Task(self.redis.get, sms_frequence_lock)
            if has_lock:
                self.error(status=ERROR_CODE['sms_too_frequency']['code'], message=ERROR_CODE['sms_too_frequency']['message'])
                return

            # 检查手机一天的发送次数
            sms_sent_count_key = SMS_SENT_COUNT.format(mobile=mobile)
            sms_sent_count = yield Task(self.redis.get, sms_sent_count_key)
            sms_sent_count = int(sms_sent_count) if sms_sent_count else 0

            data = {
                'sms_count': sms_sent_count,
            }

            if sms_sent_count >= SMS_SENT_COUNT_LIMIT:
                self.error(status=ERROR_CODE['sms_too_frequency']['code'], message=ERROR_CODE['sms_too_frequency']['message'], data=data)
                return

            if sms_sent_count >= SMS_NEED_GEETEST_COUNT:
                challenge = self.params.get('geetest_challenge', '')
                if not challenge:
                    self.error(status=ERROR_CODE['sms_over_three']['code'], message=ERROR_CODE['sms_over_three']['message'], data=data)
                    return
                valid = yield self.validate_captcha(
                    challenge=self.params['geetest_challenge'],
                    seccode=self.params['geetest_seccode'],
                    validate=self.params['geetest_validate']
                )
                if not valid:
                    self.error(status=ERROR_CODE['fail_in_geetest']['code'], message=ERROR_CODE['sms_over_three']['message'])
                    return

            # 发送短信验证码
            auth_code = gen_random_code()

            yield Task(self.redis.setex, sms_frequence_lock, SMS_FREQUENCE_LOCK_TIMEOUT, '1')
            result = yield self.sms_service.send(mobile, auth_code)

            if result.get('err'):
                self.error(result.get('err'))
                return

            # 增加手机发送次数
            if sms_sent_count == 0:
                yield Task(self.redis.setex, sms_sent_count_key, SMS_SENT_COUNT_LIMIT_TIMEOUT, '1')
            else:
                yield Task(self.redis.incr, sms_sent_count_key)

            # 设置验证码有效期
            yield Task(self.redis.setex, AUTH_CODE.format(mobile=mobile, auth_code=auth_code), SMS_TIMEOUT, '1')

            self.log.info('mobile: {mobile}, auth_code: {auth_code}'.format(mobile=mobile, auth_code=auth_code))

            self.success(data)
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class UserLoginHandler(NeedSMSMixin, UserBase):
    @coroutine
    def post(self):
        """
        @api {post} /api/user/login 验证码登陆
        @apiName UserLoginHandler
        @apiGroup User

        @apiParam {String} mobile
        @apiParam {String} auth_code


        @apiSuccessExample {json} Success-Response:
          HTTP/1.1 200 ok
            {
                "status": int,
                "message": str,
            }
        """
        try:
            # 参数认证
            args = ['mobile', 'auth_code']

            self.guarantee(*args)
            self.strip(*args)

            validate_mobile(self.params['mobile'])
            validate_auth_code(self.params['auth_code'])

            mobile, auth_code = self.params['mobile'], self.params['auth_code']

            is_ok = yield self.check(mobile, auth_code)
            if not is_ok:
                return

            yield self.make_session(self.params['mobile'])
            yield self.clean()

            is_exist = yield self.user_service.select(
                fields='password',
                conds=['mobile=%s'],
                params=[mobile],
                ct=False, ut=False, one=True
            )
            if not is_exist['password']:
                self.error(status=ERROR_CODE['no_registered']['code'], message=ERROR_CODE['no_registered']['message'])
                return

            self.success()
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class UserLogoutHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/user/logout 用户退出
        @apiName UserLogoutHandler
        @apiGroup User

        @apiUse Success
        """
        try:
            yield self.del_session(self.current_user['id'])
            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())



class UserDetailHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self):
        """
        @api {get} /api/user 获取用户详情
        @apiName UserDetailHandler
        @apiGroup User

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "message": "success",
                "data": {
                    "id": int,
                    "name": str,
                    "mobile": str,
                    "email": str,
                    "image_url": str,
                    "create_time": str,
                    "update_time": str,
                    "gender": int,
                    "birthday": int
                }
            }
        """
        try:
            self.success(self.current_user)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class UserUpdateHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/user/update 更新用户信息
        @apiName UserUpdateHandler
        @apiGroup User

        @apiParamExample {json} Request-Example:
            {
                "name": str,
                "email": str,
                "image_url": str,
                "mobile": str,
                "gender": int,
                "birthday": int
            }

        @apiUse Success
        """
        try:
            old = self.current_user

            new = {
                'id': old['id'],
                'name': self.params.get('name', '') or old.get('name', ''),
                'email': self.params.get('email' '') or old.get('email', ''),
                'image_url': settings['qiniu_header_bucket_url'] + self.params.get('image_url', '') \
                             if self.params.get('image_url', '') else old.get('image_url', ''),
                'mobile': self.params.get('mobile', '') or old.get('mobile', ''),
                'create_time': old['create_time'],
                'update_time': seconds_to_human(),
                "gender": self.params.get('gender') or int(old.get('gender', 3)),
                'birthday': self.params.get('birthday') or int(old.get('birthday', 0))
            }

            yield self.user_service.update(sets=['name=%s', 'email=%s', 'image_url=%s', 'mobile=%s', 'gender=%s', 'birthday=%s'],
                                           conds=['id=%s'],
                                           params=[new['name'], new['email'], new['image_url'], new['mobile'], new['gender'], new['birthday'], new['id']])

            yield self.set_session(new['id'], new)

            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class UserUploadToken(BaseHandler):
    @is_login
    @coroutine
    def get(self):
        """
        @api {get} /api/user/token 用户上传token
        @apiName UserUploadToken
        @apiGroup User

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "message": "success",
                "data": {
                    "token": str,
                    "timeout": int,
                }
            }
        """
        try:
            data = yield self.user_service.get_qiniu_token()
            self.success(data)
        except:
            self.error()
            self.log.error(traceback.format_exc())

    @is_login
    @coroutine
    def delete(self):
        """
        @api {delete} /api/user/token 用户删除token
        @apiName UserDeleteToekn
        @apiGroup User

        @apiUse Success
        """
        try:
            yield self.user_service.delete_token(self.current_user['id'])
            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class FileUploadMixin(BaseHandler):
    def get_file_info(self, param='file'):
        """
        :param param: 前端上传的参数名
        :return 文件名, 文件内容
        """
        if len(self.request.files) == 0:
            filename, content = self.get_argument(param), self.request.body
        else:
            filename, content = self.request.files[param][0]['filename'], self.request.files[param][0]['body']

        return filename, content

    @coroutine
    def handle_file_upload(self, new_name=None):
        filename, content = self.get_file_info()

        self.log.info('---FileUpload--- filename: %s, new_name: %s, content_len: %s' % (filename, new_name, len(content)))

        filename = yield self.user_service.save_file(new_name or filename, content)

        return filename


class GetCaptchaHandler(BaseHandler):
    @coroutine
    def get(self):
        """
        @api {get} /api/user/captcha 极验证验证码预处理
        @apiName GetCaptChaHandler
        @apiGroup User

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "message": "success",
                "data": {
                    "success": int,
                    "gt": str,
                    "challenge": str,
                    "new_captcha": boolean
                }
            }
        """
        try:
            gt = GeetestLib(settings['gee_id'], settings['gee_key'])
            status = gt.pre_process()
            if not status:
                status = 2
            yield Task(self.redis.set, gt.GT_STATUS_SESSION_KEY, status)
            response_str = json.loads(gt.get_response_str())
            self.success(response_str)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class PasswordLoginHandler(UserBase):
    @coroutine
    def post(self):
        """
        @api {post} /api/user/login/password 密码登入
        @apiName PasswordLoginHandler
        @apiGroup User

        @apiParam {String} mobile 手机号码
        @apiParam {String} password 密码

        @apiUse Success
        """
        try:
            args = ['mobile', 'password']

            self.guarantee(*args)
            self.strip(*args)

            validate_mobile(self.params['mobile'])
            validate_user_password(self.params['password'])

            password = self.params['password'].encode('utf-8')
            hashed = yield self.user_service.select(
                                                            fields='password',
                                                            conds=['mobile=%s'],
                                                            params=[self.params['mobile']],
                                                            ct=False, ut=False, one=True
            )
            if bcrypt.checkpw(password, hashed['password'].encode('utf-8')):
                yield self.make_session(self.params['mobile'])
                self.success()
            else:
                self.error(status=ERROR_CODE['password_error']['code'], message=ERROR_CODE['password_error']['message'])
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class UserRegisterHandler(NeedSMSMixin, UserBase):
    @coroutine
    def post(self):
        """
        @api {post} /api/user/register 用户注册
        @apiName  UserRegisterHandler
        @apiGroup User

        @apiParam {Number} mobile 手机号码
        @apiParam {String} auth_code 验证码
        @apiParam {String} password 密码

        @apiUse Success
        """
        try:
            args = ['mobile', 'auth_code', 'password']

            self.guarantee(*args)
            self.strip(*args)

            validate_mobile(self.params['mobile'])
            validate_auth_code(self.params['auth_code'])
            validate_user_password(self.params['password'])

            data = yield self.user_service.select(
                                                    fields='id',
                                                    conds=['mobile=%s'],
                                                    params=[self.params['mobile']],
                                                    ct=False, ut=False, one=True
                                                )
            if data:
                self.error(status=ERROR_CODE['mobile_has_exist']['code'],message=ERROR_CODE['mobile_has_exist']['message'])
                return

            mobile, auth_code = self.params['mobile'], self.params['auth_code']
            is_ok = yield self.check(mobile, auth_code)
            if not is_ok:
                return

            arg = {
                'mobile': mobile,
                'password': bcrypt.hashpw(self.params['password'].encode('utf-8'), bcrypt.gensalt())
            }
            yield self.user_service.add(params=arg)

            yield self.make_session(self.params['mobile'])
            yield self.clean()
            self.success()
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class UserResetPasswordHandler(NeedSMSMixin, UserBase):
    @coroutine
    def post(self):
        """
           @api {post} /api/user/password/reset 重置密码
           @apiName UserResetPasswordHandler
           @apiGroup User

           @apiParam {String} mobile
           @apiParam {String} old_password
           @apiParam {String} new_password
           @apiParam {String} auth_code 验证码

           @apiUse Success
           """
        try:
            args = ['mobile', 'new_password', 'auth_code']
            self.guarantee(*args)
            self.strip(*args)

            validate_mobile(self.params['mobile'])
            validate_auth_code(self.params['auth_code'])
            validate_user_password(self.params['new_password'])

            mobile, auth_code = self.params['mobile'], self.params['auth_code']
            is_ok = yield self.check(mobile, auth_code)
            if not is_ok:
                return

            old_password = self.params.get('old_password', '')
            if old_password:
                old_password = old_password.encode('utf-8')
                hashed = yield self.user_service.select(
                    fields='password',
                    conds=['mobile=%s'],
                    params=[self.params['mobile']],
                    ct=False, ut=False, one=True
                )
                result = bcrypt.checkpw(old_password, hashed['password'].encode('utf-8'))
                if not result:
                    self.error(status=ERROR_CODE['password_error']['code'], message=ERROR_CODE['password_error']['message'])
                    return

            hashed = bcrypt.hashpw(self.params['new_password'].encode('utf-8'), bcrypt.gensalt())
            yield self.user_service.update(
                                            sets=['password=%s'],
                                            conds=['mobile=%s'],
                                            params=[hashed, self.params['mobile']]
            )
            yield self.make_session(self.params['mobile'])
            yield self.clean()
            self.success()
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class UserResetMobileHandler(NeedSMSMixin, UserBase):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/user/mobile/reset 重置手机号码
        @apiName UserResetMobileHandler
        @apiGroup User

        @apiParam {String} new_mobile
        @apiParam {String} auth_code
        @apiParam {String} password

        @apiUse Success
        """
        try:
            args = ['new_mobile', 'auth_code', 'password']

            self.guarantee(*args)
            self.strip(*args)

            validate_mobile(self.params['new_mobile'])
            validate_auth_code(self.params['auth_code'])
            validate_user_password(self.params['password'])

            mobile = self.params['new_mobile']
            auth_code = self.params['auth_code']
            password = self.params['password'].encode('utf-8')

            data = yield self.user_service.select(
                fields='id',
                conds=['mobile=%s'],
                params=[mobile],
                ct=False, ut=False, one=True
            )
            if data:
                self.error(status=ERROR_CODE['mobile_has_exist']['code'], message=ERROR_CODE['mobile_has_exist']['message'])
                return

            is_ok = yield self.check(mobile, auth_code)
            if not is_ok:
                return

            hashed = yield self.user_service.select(
                fields='password',
                conds=['id=%s'],
                params=[self.current_user['id']],
                ct=False, ut=False, one=True
            )
            result = bcrypt.checkpw(password, hashed['password'].encode('utf-8'))
            if not result:
                self.error(status=ERROR_CODE['password_error']['code'], message=ERROR_CODE['password']['message'])
                return

            yield self.user_service.update(sets=['mobile=%s'], conds=['id=%s'], params=[mobile, self.current_user['id']])
            self.clean()
            self.success()

        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


