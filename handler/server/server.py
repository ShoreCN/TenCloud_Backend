__author__ = 'Jon'

import traceback
import json
import re


from tornado.websocket import WebSocketHandler
from tornado.gen import coroutine, Task
from tornado.ioloop import PeriodicCallback, IOLoop
from handler.base import BaseHandler
from constant import DEPLOYING, DEPLOYED, DEPLOYED_FLAG, ALIYUN_REGION_NAME
from utils.general import validate_ip
from utils.security import Aes
from utils.decorator import is_login
from utils.ssh import SSH
from constant import MONITOR_CMD, OPERATE_STATUS, SERVER_OPERATE_STATUS


class ServerNewHandler(WebSocketHandler, BaseHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        self.write_message('open')

    def on_message(self, message):
        self.params = json.loads(message)

        # 参数认证
        try:
            args = ['cluster_id', 'name', 'public_ip', 'username', 'passwd']

            self.guarantee(*args)

            for i in args[1:]:
                self.params[i] = self.params[i].strip()

            validate_ip(self.params['public_ip'])
        except Exception as e:
            self.write_message(str(e))
            self.close()
            return

        IOLoop.current().spawn_callback(callback=self.handle_msg)  # on_message不能异步, 要实现异步需spawn_callback

    @coroutine
    def handle_msg(self):
        is_deploying = yield Task(self.redis.hget, DEPLOYING, self.params['public_ip'])

        is_deployed = yield Task(self.redis.hget, DEPLOYED, self.params['public_ip'])


        if is_deploying:
            self.write_message('%s 正在部署' % self.params['public_ip'])
            return

        if is_deployed:
            self.write_message('%s 之前已部署' % self.params['public_ip'])
            return

        # 保存到redis之前加密
        passwd = self.params['passwd']
        self.params['passwd'] = Aes.encrypt(passwd)

        yield Task(self.redis.hset, DEPLOYING, self.params['public_ip'], json.dumps(self.params))

        self.period = PeriodicCallback(self.check, 3000)  # 设置定时函数, 3秒
        self.period.start()

        self.params.update({'passwd': passwd})
        _, err = yield self.server_service.remote_ssh(self.params, cmd=MONITOR_CMD)

        err = [e for e in err if not re.search(r'symlink|resolve host', e)] # 忽略某些错误

        # 部署失败
        if err:
            self.write_message(str(err))
            self.period.stop()
            self.close()

            yield Task(self.redis.hdel, DEPLOYING, self.params['public_ip'])

    @coroutine
    def check(self):
        ''' 检查主机是否上报信息 '''
        result = yield Task(self.redis.hget, DEPLOYED, self.params['public_ip'])

        if result:
            self.write_message('success')
            self.period.stop()
            self.close()

    def on_close(self):
        if hasattr(self, 'period'):
            self.period.stop()


class RealtimeOutputHandler(WebSocketHandler, BaseHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        self.write_message('open')

    def on_message(self, message):
        try:
            ssh = SSH(hostname='localhost', port=2222, username='root', passwd='000000')
            self.ssh_out, self.ssh_err = ssh.exec_rt('top -b -n 5', self.write_message)
        except Exception as e:
            self.write_message(e)
        finally:
            ssh.close()

    def on_close(self):
        pass


class ServerReport(BaseHandler):
    @coroutine
    def post(self):
        """
        @api {post} /remote/server/report 监控上报
        @apiName ServerReport
        @apiGroup Server

        @apiParam {String} public_ip 公共ip
        @apiParam {Number} time 时间戳
        @apiParam {map[Number]Object} docker 容器
        @apiParam {Object} cpu CPU
        @apiParam {Object} memory Memory
        @apiParam {Object} disk Disk
        @apiParam {Object} net Net

        @apiUse Success
        """
        try:
            deploying_msg = yield Task(self.redis.hget, DEPLOYING, self.params['public_ip'])

            is_deployed = yield Task(self.redis.hget, DEPLOYED, self.params['public_ip'])

            if not deploying_msg and not is_deployed:
                raise ValueError('%s not in deploying/deployed' % self.params['public_ip'])

            if deploying_msg:
                data = json.loads(deploying_msg)
                self.params.update({
                    'name': data['name'],
                    'cluster_id': data['cluster_id']
                })

                yield self.server_service.add_server(self.params)
                yield self.server_service.save_server_account({'username': data['username'],
                                                               'passwd': data['passwd'],
                                                               'public_ip': data['public_ip']})
                yield Task(self.redis.hdel, DEPLOYING, self.params['public_ip'])
                yield Task(self.redis.hset, DEPLOYED, self.params['public_ip'], DEPLOYED_FLAG)

            yield self.server_service.save_report(self.params)

            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerMigrationHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/server/migration 主机迁移
        @apiName ServerMigrationHandler
        @apiGroup Server

        @apiParam {Number} cluster_id 集群id
        @apiParam {Number[]} id 主机ID

        @apiUse Success
        """
        try:
            yield self.server_service.migrate_server(self.params)

            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerDelHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/server/del 主机删除
        @apiName ServerDelHandler
        @apiGroup Server

        @apiParam {Number[]} id 主机ID

        @apiUse Success
        """
        try:
            yield self.server_service.delete_server(self.params)

            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerDetailHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, id):
        """
        @api {get} /api/server/(\d+) 主机详情
        @apiName ServerDetailHandler
        @apiGroup Server

        @apiParam {Number} id 主机ID

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
            "status": 0,
            "msg": "success",
            "data": {
                "basic_info": {
                    "id": int,
                    "name": str,
                    "cluster_id": int,
                    "cluster_name": str,
                    "address": str,
                    "public_ip": str,
                    "machine_status": str,
                    "business_status": str,
                    "region_id": str,
                    "instance_id": str
                },
                "system_info": {
                    "config": {
                        "cpu": int,
                        "memory": str,
                        "os_name": str,
                        "os_type": str
                    }
                },
                "business_info": {
                    "provider": str,
                    "contract": {
                        "create_time": str,
                        "expired_time": str,
                        "charge_type": str
                    }
                }
            }
            }
        """
        try:
            data = yield self.server_service.get_detail(id)

            result = dict()

            result['basic_info'] = {
                'id': data['id'],
                'name': data['name'],
                'cluster_id': data['cluster_id'],
                'cluster_name': data['cluster_name'],
                'address': data['region_name'],
                'public_ip': data['public_ip'],
                'machine_status': data['machine_status'],
                'business_status': data['business_status'],
                'region_id': data['region_id'],
                'instance_id': data['instance_id'],
                'created_time': data['server_created_time']
            }

            result['system_info'] = {
                'config': {
                    'cpu': data['cpu'],
                    'memory': data['memory'],
                    'os_name': data['os_name'],
                    'os_type': data['os_type']
                }
            }

            result['business_info'] = {
                'provider': data['provider'],
                'contract': {
                    'create_time': data['create_time'],
                    'expired_time': data['expired_time'],
                    'charge_type': data['charge_type']
                }
            }

            self.success(result)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerPerformanceHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/server/performance 主机性能
        @apiName ServerPerformanceHandler
        @apiGroup Server

        @apiParam {Number} id 主机ID
        @apiParam {Number} start_time 起始时间
        @apiParam {Number} end_time 终止时间
        @apiParam {Number} type 0: 机器详情 1: 正常 2: 按时平均 3: 按天平均
        @apiParam {Number} now_page 当前页面
        @apiParam {Number} page_number 每页返回条数， 小于100条

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": {
                    "cpu": [
                        [1496390702, {"percent": int}],
                        ...
                    ],
                    "memory": [
                        [1496390702, {"total": int, "available": int, "free": int, "percent": int}],
                        ...
                    ],
                    "disk": [
                        [1496390702, {"total": int, "free": int, "percent": int}],
                        ...
                    ],
                    "net": [
                        [1496390702, {"input": int, "output": int}]
                        ...
                    ]
                }
            }
        :return:
        """
        try:
            data = yield self.server_service.get_performance(self.params)
            self.success(data)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerUpdateHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/server/update 主机信息更新
        @apiName ServerUpdateHandler
        @apiGroup Server

        @apiParam {Number} id 主机id
        @apiParam {String} name 主机名字

        @apiUse Success
        """
        try:
            yield self.server_service.update_server(self.params)

            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerStopHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, id):
        """
        @api {get} /api/server/stop/(\d+) 停止主机
        @apiName ServerStopHandler
        @apiGroup Server

        @apiParam {Number} id 主机id

        @apiUse Success

        """
        try:
            data = yield self.server_operation_service.add(params={
                                                            'user_id': self.current_user['id'],
                                                            'object_id': id,
                                                            'operation': SERVER_OPERATE_STATUS['start'],
                                                            'operation_status': OPERATE_STATUS['fail'],
                                                        })
            yield self.server_service.stop_server(id)
            yield self.server_operation_service.update(
                                                        sets=['operation_status=%s'],
                                                        conds=['id=%s'],
                                                        params=[OPERATE_STATUS['success'], data['id']]
                                                    )
            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerStartHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, id):
        """
        @api {get} /api/server/start/(\d+) 开启主机
        @apiName ServerStartHandler
        @apiGroup Server

        @apiParam {Number} id 主机id

        @apiUse Success
        """
        try:
            data = yield self.server_operation_service.add(params={
                                                            'user_id': self.current_user['id'],
                                                            'object_id': id,
                                                            'operation': SERVER_OPERATE_STATUS['start'],
                                                            'operation_status': OPERATE_STATUS['fail'],
                                                        })
            yield self.server_service.start_server(id)
            yield self.server_operation_service.update(
                                                        sets=['operation_status=%s'],
                                                        conds=['id=%s'],
                                                        params=[OPERATE_STATUS['success'], data['id']]
                                                    )
            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())

class ServerRebootHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, id):
        """
        @api {get} /api/server/reboot/(\d+) 重启主机
        @apiName ServerRebootHandler
        @apiGroup Server

        @apiParam {Number} id 主机id

        @apiUse Success
        """
        try:
            data = yield self.server_operation_service.add(params={
                                                            'user_id': self.current_user['id'],
                                                            'object_id': id,
                                                            'operation': SERVER_OPERATE_STATUS['reboot'],
                                                            'operation_status': OPERATE_STATUS['fail'],
                                                        })
            yield self.server_service.reboot_server(id)
            yield self.server_operation_service.update(
                                                        sets=['operation_status=%s'],
                                                        conds=['id=%s'],
                                                        params=[OPERATE_STATUS['success'], data['id']]
                                                    )
            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerStatusHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, instance_id):
        """
        @api {get} /api/server/([\w\W]+)/status 查询实例状态
        @apiName ServerStatusHandler
        @apiGroup Server

        @apiParam {Number} instance_id 实例id

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": "Running"
            }
        """
        try:
            data = yield self.server_service.get_instance_status(instance_id)

            self.success(data)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerContainerPerformanceHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/server/container/performance 获取主机里面的各个docker容器使用情况
        @apiName ServerContainerPerformanceHandler
        @apiGroup Server

        @apiParam {Number} server_id 主机id
        @apiParam {String} container_name 容器名字
        @apiParam {Number} start_time 起始时间
        @apiParam {Number} end_time 终止时间

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": {
                    "cpu": [
                         {},
                         ...
                    ],
                    "memory": [
                        {},
                        ...
                    ],
                    "disk": [
                        {},
                        ...
                    ],
                    "net":
                }
            }
        """
        try:
            data = yield self.server_service.get_docker_performance(self.params)
            self.success(data)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerContainersHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, id):
        """
        @api {get} /api/server/containers/(\d+) 获取主机里面的docker容器列表
        @apiName ServerContainersHandler
        @apiGroup Server

        @apiParam {Number} id 主机id

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": [
                    [
                        "1a050e4d7e43", # container id
                         "harbor-jobservice", # container name
                        "Up 3 weeks", # status
                        "2017-05-18 14:06:50 +0800 CST\n" # created_time
                    ],
                    ...
                ]
            }
        """
        try:
            data = yield self.server_service.get_containers({"server_id": str(id)})

            self.success(data)
        except:
            self.success()
            self.log.error(traceback.format_exc())


class ServerContainersInfoHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, server_id, container_id):
        """
        @api {get} /api/server/([\w\W]+)/container/([\w\W]+) 获取主机容器信息
        @apiName ServerContainersInfoHandler
        @apiGroup Server

        @apiParam {Number} server_id 服务器id
        @apiParam {Number} container_id 容器id

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": {
                     ...
                }
            }
        """
        try:
            params = yield self.server_service.fetch_ssh_login_info({'server_id': server_id})
            server_name = yield self.server_service.select(fields='name', conds=['id=%s'], params=[server_id], ct=False, ut=False, one=True)
            params.update({'container_id': container_id, 'server_name': server_name['name']})
            data, err = yield self.server_service.get_container_info(params)
            if err:
                self.error(err)
            else:
                self.success(data)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerContainerStartHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/server/container/start 启动容器
        @apiName ServerContainerStartHandler
        @apiGroup Server

        @apiParam {Number} server_id 主机id
        @apiParam {String} container_id 容器id

        @apiUse Success
        """
        try:
            yield self.server_service.start_container(self.params)

            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerContainerStopHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/server/container/stop 停止容器
        @apiName ServerContainerStopHandler
        @apiGroup Server

        @apiParam {Number} server_id 主机id
        @apiParam {String} container_id 容器id

        @apiUse Success
        """
        try:
            yield self.server_service.stop_container(self.params)

            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ServerContainerDelHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/server/container/del 删除容器
        @apiName ServerContainerDelHandler
        @apiGroup Server

        @apiParam {Number} server_id 主机id
        @apiParam {String} container_id 容器id

        @apiUse Success
        """
        try:
            yield self.server_service.del_container(self.params)

            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())

class ServerOperationHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, server_id):
        """
        @api {get} /api/server/([\w\W]+)/operation 主机操作记录
        @apiName ServerOperationHandler
        @apiGroup Server

        @apiParam {Number} server_id 主机id

        @apiSuccessExample {json} Success-Response:
         HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": [
                    {
                        "created_time": str,
                        "operation" : int 0:开机, 1:关机, 2:重启
                        "operation_status": int 0:成功, 1:失败
                        "user": str
                    }
                    ...
                ]
            }
        """
        try:
            data = yield self.server_operation_service.get_server_operation(server_id)
            self.success(data)
        except:
            self.error()
            self.log.error(traceback.format_exc())
