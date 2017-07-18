__author__ = 'Jon'

import traceback
from handler.base import BaseHandler
from tornado.gen import coroutine


class RepositoryHandler(BaseHandler):
    @coroutine
    def get(self):
        """
        @api {get} /api/repos 获取repos, 现在默认git并且token保存在setting, 以后可以支持更多并且使用数据库
        @apiName RepositoryHandler
        @apiGroup Repository

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
             {
                "status": 0,
                "msg": "success",
                 "data":[
                     {"repos_name": str, "repos_url": str},
                     ...
                  ]
             }
        """
        try:
            result = yield self.repos_service.fetch_repos()

            self.success(result)
        except:
            self.error()
            self.log.error(traceback.format_exc())


class RepositoryBranchHandler(BaseHandler):
    @coroutine
    def get(self):
        """
        @api {get} /api/repos/branches?repos_name='' 获取仓库的分支
        @apiName RepositoryBranchHandler
        @apiGroup Repository

        @apiParam {String} repos_name 仓库名称

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": [
                    {"branch_name": str},
                    ...
                ]
            }
        """
        try:
            repos_name = self.get_argument('repos_name', '').strip()

            result = yield self.repos_service.fetch_branches(repos_name)

            self.success(result)
        except:
            self.error()
            self.log.error(traceback.format_exc())
