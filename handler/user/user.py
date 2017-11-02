__author__ = 'Jon'

import traceback

from tornado.gen import Task, coroutine
from sdk import GeetestLib
import bcrypt
import json
from constant import AUTH_CODE, AUTH_CODE_ERROR_COUNT, AUTH_CODE_ERROR_COUNT_LIMIT, AUTH_FAILURE_TIP, AUTH_LOCK, \
    AUTH_LOCK_TIMEOUT, AUTH_LOCK_TIP, COOKIE_EXPIRES_DAYS, SMS_SENDING_LOCK, SMS_SENDING_LOCK_TIMEOUT, \
    SMS_SENDING_LOCK_TIP, SMS_TIMEOUT, CAPTCHA_TIMEOUT
from handler.base import BaseHandler
from setting import settings
from utils.datetool import seconds_to_human
from utils.decorator import is_login
from utils.general import gen_random_code, validate_auth_code, validate_mobile


class UserSMSHandler(BaseHandler):
    @coroutine
    def post(self, mobile):
        """
        @api {post} /api/user/sms/:mobile 发送验证码
        @apiName UserSMSHandler
        @apiGroup User

        @apiUse Success
        """
        try:
            # 参数认证
            validate_mobile(mobile)

            # 检查sms_sending_lock
            sms_sending_lock = SMS_SENDING_LOCK.format(mobile=mobile)

            has_lock = yield Task(self.redis.get, sms_sending_lock)
            if has_lock:
                self.error(SMS_SENDING_LOCK_TIP)
                return

            # 发送短信验证码
            auth_code = gen_random_code()

            yield Task(self.redis.setex, sms_sending_lock, SMS_SENDING_LOCK_TIMEOUT, '1')
            result = yield self.sms_service.send(mobile, auth_code)

            if result.get('err'):
                self.error(result.get('err'))
                return

            # 设置验证码有效期
            yield Task(self.redis.setex, AUTH_CODE.format(mobile=mobile, auth_code=auth_code), SMS_TIMEOUT, '1')

            self.log.info('mobile: {mobile}, auth_code: {auth_code}'.format(mobile=mobile, auth_code=auth_code))
            self.success()
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


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
        # 设置cookie
        self.set_secure_cookie('user_id', str(data['id']), expires_days=COOKIE_EXPIRES_DAYS)
        # 设置session
        yield self.set_session(data['id'], data)



class UserLoginHandler(NeedSMSMixin, UserBase):
    @coroutine
    def post(self):
        """
        @api {post} /api/user/login 用户登陆
        @apiName UserLoginHandler
        @apiGroup User

        @apiParam {String} geetest_challenge
        @apiParam {String} geetest_validate
        @apiParam {String} geetest_seccode
        @apiParam {String} mobile
        @apiParam {String} auth_code


        @apiUse Success
        """
        try:
            # 参数认证
            args = ['mobile', 'auth_code', 'geetest_challenge', 'geetest_validate', 'geetest_seccode']

            self.guarantee(*args)
            self.strip(*args)

            validate_mobile(self.params['mobile'])
            validate_auth_code(self.params['auth_code'])

            mobile, auth_code = self.params['mobile'], self.params['auth_code']

            is_ok = yield self.check(mobile, auth_code)
            if not is_ok: self.error('wrong auth code')

            valid = yield self.validate_captcha(
                                    challenge=self.params['geetest_challenge'],
                                    seccode=self.params['geetest_seccode'],
                                    validate=self.params['geetest_validate']
                                    )
            if not valid:
                self.error('fail to passing geetest')

            yield self.make_session(self.params['mobile'])
            yield self.clean()

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
        @api {get} /api/user/captcha 获取验证码
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
            yield Task(self.redis.setex, gt.GT_STATUS_SESSION_KEY, CAPTCHA_TIMEOUT, status)
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
            if self.params['password'] == '':
                self.error('empty password')

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
                self.error('wrong password, please check again')
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
        @apiParam {String} geetest_challenge
        @apiParam {String} geetest_validate
        @apiParam {String} geetest_seccode

        @apiUse Success
        """
        try:
            args = ['mobile', 'auth_code', 'password', 'geetest_challenge', 'geetest_validate', 'geetest_seccode']

            self.guarantee(*args)
            self.strip(*args)

            validate_mobile(self.params['mobile'])
            validate_auth_code(self.params['auth_code'])
            if self.params['password'] == '':
                self.error('empty password')

            mobile, auth_code = self.params['mobile'], self.params['auth_code']
            is_ok = yield self.check(mobile, auth_code)
            if not is_ok:
                self.error('wrong auth code')

            is_valid = yield self.validate_captcha(
                                    challenge=self.params['geetest_challenge'],
                                    seccode=self.params['geetest_seccode'],
                                    validate=self.params['geetest_validate']
                                    )
            if not is_valid:
                self.error('fail to passing geetest ')

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
    """
    @api {post} /api/user/password/reset 重置密码
    @apiName UserResetPasswordHandler
    @apiGroup User

    @apiParam {String} mobile
    @apiParam {String} password
    @apiParam {String} auth_code 验证码
    @apiParam {String} geetest_challenge
    @apiParam {String} geetest_validate
    @apiParam {String} geetest_seccode

    @apiUse Success
    """
    @is_login
    @coroutine
    def post(self):
        try:
            args = ['mobile', 'password','auth_code', 'geetest_challenge', 'geetest_validate', 'geetest_seccode']
            self.guarantee(*args)
            self.strip(*args)

            validate_mobile(self.params['mobile'])
            validate_auth_code(self.params['auth_code'])

            mobile, auth_code = self.params['mobile'], self.params['auth_code']
            is_ok = yield self.check(mobile, auth_code)
            if not is_ok:
                self.error('wrong auth code')

            is_valid = yield self.validate_captcha(
                challenge=self.params['geetest_challenge'],
                seccode=self.params['geetest_seccode'],
                validate=self.params['geetest_validate']
            )
            if not is_valid:
                self.error('fail to passing geetest ')

            hashed = bcrypt.hashpw(self.params['password'].encode('utf-8'), bcrypt.gensalt())

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