__author__ = 'Jon'

import traceback
import json

from tornado.gen import coroutine
from handler.base import BaseHandler
from utils.general import get_in_formats
from utils.decorator import is_login
from setting import settings
from handler.user import user
from constant import PROJECT_STATUS

class ProjectHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self):
        """
        @api {get} /api/projects 获取项目列表
        @apiName ProjectHandler
        @apiGroup Project

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "message": "success",
                "data": [
                {
                    "id": int,
                    "name": str,
                    "description": str,
                    "repos_name": str,
                    "repos_url": str,
                    "update_time": str,
                    "status": str,
                }
                    ...
                ]
            }
        """
        try:
            result = yield self.project_service.select(ct=False)

            self.success(result)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ProjectNewHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/project/new 创建新项目
        @apiName ProjectNewHandler
        @apiGroup Project

        @apiParam {String} name 名称
        @apiParam {String} image_name 镜像名字 (必需小写字母，分隔符可选)
        @apiParam {String} description 描述
        @apiParam {String} repos_name 仓库名称
        @apiParam {String} repos_url 仓库url
        @apiParam {String} http_url 项目在github的http地址
        @apiParam {Number} mode 类型
        @apiParam {Number} image_source 镜像来源
        @apiParam {String} version 用于导入镜像或下载镜像的版本

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": {
                    "id": int,
                    "update_time": str
                }
            }
        """

        try:
            is_duplicate_url = yield self.project_service.select(conds=['repos_url=%s'], params=[self.params['repos_url']], one=True)

            if is_duplicate_url:
                self.error('仓库url重复')
                return

            result = yield self.project_service.add(params=self.params)

            if self.params['image_source']:
                arg = {'name': self.params['name'], 'version': self.params['version'], 'log': ''}
                yield self.project_service.insert_log(arg)

            self.success(result)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ProjectDelHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/project/del 项目删除
        @apiName ProjectDelHandler
        @apiGroup Project

        @apiParam {number[]} id 项目id

        @apiUse Success
        """
        try:
            ids = self.params['id']

            yield self.project_service.delete(conds=[get_in_formats('id', ids)], params=ids)

            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ProjectDetailHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, id):
        """
        @api {get} /api/project/(\d+) 项目详情
        @apiName ProjectDetailHandler
        @apiGroup Project

        @apiParam {Number} id 项目id

        @apiSuccessExample {json} Success-Response
            HTTP/1.1 200 OK
            {
                "status": 0,
                "message": "success",
                "data": [
                {
                    "description": str,
                    "repos_name": str,
                    "repos_url": str,
                    "http_url": str,
                    "image_name": str,
                    "id": 2,
                    "name": str,
                    "create_time": str,
                    "update_time": str,
                    "status": str,
                    "mode": str,
                    "deploy_ips": str,
                }
                    ...
                ]
            }
        """
        try:
            result = yield self.project_service.select(conds=['id=%s'], params=[id])

            self.success(result)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ProjectUpdateHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/project/update 更新项目
        @apiName ProjectUpdateHandler
        @apiGroup Project

        @apiParam {String} name 名称
        @apiParam {String} description 描述
        @apiParam {String} repos_name 仓库名字
        @apiParam {String} repos_url 仓库地址
        @apiParam {String} http_url 项目在github的仓库地址
        @apiParam {String} image_name 镜像名字
        @apiParam {String} mode 项目类型

        @apiUse Success
        """
        try:

            sets = ['name=%s', 'description=%s', 'repos_name=%s', 'repos_url=%s', 'http_url=%s', 'mode=%s', 'image_name=%s']
            conds = ['id=%s']
            params = [
                    self.params['name'],
                    self.params['description'],
                    self.params['repos_name'],
                    self.params['repos_url'],
                    self.params['http_url'],
                    self.params['mode'],
                    self.params['image_name'],
                    self.params['id']
                    ]

            yield self.project_service.update(sets=sets, conds=conds, params=params)
            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ProjectDeploymentHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/project/deployment 部署镜像
        @apiName ProjectDeploymentHandler
        @apiGroup Project

        @apiParam {String} image_name 镜像名称
        @apiParam {String} container_name 容器名字
        @apiParam {map[String]map[String]String} ips 公共ip
        @apiParam {String} project_id 项目id

        @apiParamExample {json} Request-Example:
            {
                "image_name": "infohub:0.0.1",
                "container_name": "infohub",
                "project_id": "1",
                "ips": [
                    {"public_ip": "192.168.56.10"},
                    {"public_ip": "192.168.56.11"},
                    ...
                ]
            }

        @apiSuccessExample {json} Success-Response
            HTTP/1.1 200 OK
            {
                "192.168.56.10":{
                    "output": String[],
                    "err":  String[]
                }
                "192.168.56.11":{
                    "output": String[],
                    "err": String[]
                }
            }
        """
        try:
            params = {'id': self.params['project_id'], 'status': PROJECT_STATUS['deploying']}
            yield self.project_service.update_status(params)

            self.params["infos"] = []
            for ip in self.params['ips']:
                login_info = yield self.server_service.fetch_ssh_login_info(ip)
                self.params['infos'].append(login_info)

            log = yield self.project_service.deployment(self.params)
            status = PROJECT_STATUS['deploy_success']
            if log['has_err']:
                status = PROJECT_STATUS['deploy_failure']

            arg = [json.dumps(self.params['ips']), self.params['container_name'], self.params['project_id'], status]
            yield self.project_service.update(
                                            sets=['deploy_ips=%s', 'container_name=%s', 'status=%s'],
                                            conds=['id=%s'], params=arg)
            self.success(log['log'])
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ProjectContainersListHanler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/project/containers/list 项目容器列表
        @apiName ProjectContainersList
        @apiGroup Project

        @apiParam {String} container_list 容器列表
        @apiParam {String} container_name 容器名字

        @apiSuccessExample {json} Success-Response
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": [
                    [
                        "1a050e4d7e43", # container id
                         "harbor-jobservice", # container name
                        "Up 3 weeks", # status
                        "2017-05-18 14:06:50" # created_time
                        "server_id" # server_id
                    ],
                    ...
                ]
            }
        """
        try:
            data = []
            for ip in json.loads(self.params['container_list']):
                server_id = yield self.server_service.fetch_server_id(ip['public_ip'])
                login_info = yield self.server_service.fetch_ssh_login_info(ip)
                ip.update(login_info)
                ip.update({'container_name': self.params['container_name']})
                info = yield self.project_service.list_containers(ip)
                if not info:
                    continue
                one_ip = []
                for i in info:
                    i[3] = i[3].split('+')[0].strip()
                    i.append(server_id)
                    one_ip.extend(i)
                data.append(one_ip)
            self.success(data)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ProjectImageCreationHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/project/image/creation 构建仓库镜像
        @apiName ProjectImageCreationHandler
        @apiGroup Project

        @apiParam {String} prj_name 项目名字
        @apiParam {String} repos_url 仓库地址
        @apiParam {String} branch_name 分支名字
        @apiParam {String} version 版本号
        @apiParam {String} image_name 镜像名字

        @apiUse Success
        """
        try:
            params = {'name': self.params, 'status': PROJECT_STATUS['building']}
            yield self.project_service.update_status(params)

            login_info = yield self.server_service.fetch_ssh_login_info({'public_ip': settings['ip_for_image_creation']})
            self.params.update(login_info)
            out, err = yield self.project_service.create_image(self.params)
            log = {"out": out, "err": err}
            arg = {'name': self.params['prj_name'], 'version': self.params['version'], 'log': json.dumps(log)}
            yield self.project_service.insert_log(arg)

            params['status'] = PROJECT_STATUS['build_success']
            if err:
                params['status'] = PROJECT_STATUS['build_failure']
            yield self.project_service.update_status(params)

            self.success(out)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ProjectImageLogHandler(BaseHandler):
    @coroutine
    def get(self, prj_name, version):
        """
        @api {get} /api/project/([\w\W]+)/image/([\w\W]+)/log 获取相关项目的某一版本的构建日志
        @apiName ProjectImageLogHandler
        @apiGroup Project

        @apiParam {String} prj_name 项目名字
        @apiParam {String} version 版本

        @apiSuccessExample Success-Response:
            HTTP/1.1 200 OK
            {
                "status":0,
                "msg": "success",
                "data": {
                    "log": {
                        "err": String[],
                        "out": String[],
                    }
                    "update_time": String,
                }
            }
        """
        try:
            out = yield self.project_versions_service.select(
                                                            fields='log', conds=['name=%s', 'version=%s'],
                                                            params=[prj_name, version], ct=False, one=True)
            data = {"log": json.loads(out['log']), "update_time": out['update_time']}
            self.success(data)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ProjectVersionsHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, prj_name):
        """
        @api {get} /api/project/([\w\W]+)/versions 获取相关项目的所有版本
        @apiName ProjectVersionsHandler
        @apiGroup Project

        @apiParam {String} prj_name 项目名字
        @apiSuccessExample Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": [
                    {"id": int, "version": str, "update_time": str},
                    ...
                ]
            }
        """
        try:
            data = yield self.project_versions_service.select(fields='id, version', conds=['name=%s'], params=prj_name, ct=False, extra='order by update_time desc')
            self.success(data)
        except:
            self.error()
            self.log.error(traceback.format_exc())

class ProjectImageFindHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, prj_name):
        """
        @api {get} /api/project/([\w\W]+)/image 获取某一项目的所有镜像信息
        @apiName ProjectImageFindHandler
        @apiGroup Project

        @apiParam {String} prj_name 项目名称

        @apiSuccessExample Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": [
                    ["{Tag}", "{CreatedAt}"],
                    ...
                ]
            }
        """
        try:
            self.params.update({"prj_name": prj_name})
            login_info = yield self.server_service.fetch_ssh_login_info({'public_ip': settings['ip_for_image_creation']})
            self.params.update(login_info)
            data, err = yield self.project_service.find_image(self.params)
            if err:
                self.error(err)
                return
            self.success(data)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ProjectImageUpload(user.FileUploadMixin):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/project/image/upload 镜像上传
        @apiName ProjectImageUpload
        @apiGroup Project


        @apiUse Success
        """
        try:
            filename = yield self.handle_file_upload()
            yield self.project_service.upload_image(filename)
            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())


class ProjectImageCloudDownload(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/project/image/cloud/download 云端下载导入
        @apiName ProjectImageDownload
        @apiGroup Project

        @apiParam {String} image_url 镜像下载地址

        @apiUse Success
        """
        try:
            yield self.project_service.cloud_download(self.params['image_url'])
            yield self.project_service.upload_image(self.params['image_url'].split('\\')[-1])
            self.success()
        except:
            self.error()
            self.log.error(traceback.format_exc())

