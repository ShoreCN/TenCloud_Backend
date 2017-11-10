import traceback

from tornado.gen import coroutine
from tornado.web import authenticated
from handler.base import BaseHandler
from utils.decorator import is_login
from utils.general import get_in_formats
from constant import MAX_PAGE_NUMBER


class FileListHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/file/list 文件分页
        @apiName FileListHandler
        @apiGroup File

        @apiParam {Number} file_id
        @apiParam {Number} now_page 当前页面
        @apiParam {Number} page_number 每页返回条数，小于100条

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "message": "success",
                "data": [
                        {
                            "id": int,
                            "filename": str,
                            "size": str,
                            "qiniu_id": str,
                            "owner": str,
                            "mime": str,
                            "hash": str,
                            "type": int, 0为文件，1为文件夹， 当为1时，部分字段为空
                            "pid": int,
                            "url": str,
                            "thumb":str,
                            "create_time": str,
                            "update_time": str,
                        }
                            ...
                    ]
            }
        """
        try:
            if self.params['page_number'] > MAX_PAGE_NUMBER:
                self.error(message='over limit page number')
                return
            data = yield self.file_service.seg_page(self.params)
            self.success(data)
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class FileTotalHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, file_id):
        """
        @api {get} /api/file/([\w\W]+)/pages 总页数
        @apiName FileTotal
        @apiGroup File

        @apiParam {Number} file_id

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "message": "successs",
                "data": int
            }
        """
        try:
            data = yield self.file_service.total_pages(file_id)
            self.success(data)
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class FileInfoHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, file_id):
        """
        @api {get} /api/file/([\w\W]+) 文件详细信息
        @apiName FileInfo
        @apiGroup File

        @apiParam {Number} file_id 文件id

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "message": "success",
                "data": {
                    "id": int,
                    "filename": str,
                    "size": str,
                    "qiniu_id": str,
                    "owner": str,
                    "mime": str,
                    "hash": str,
                    "type": int, 0为文件，1为文件夹， 当为1时，部分字段为空
                    "pid": int,
                    "url": str
                    "create_time": str,
                    "update_time": str,
                }
            }
        """
        try:
            data = yield self.file_service.select(conds=['id=%s'], params=[file_id], one=True)
            self.success(data)
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class FileUploadHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/file/upload 文件上传
        @apiName FileUpload
        @apiGroup File

        @apiParam {String} filename 文件名
        @apiParam {String} hash 文件hash
        @apiParam {Number} pid 上一级目录id
        @apiParamExample {json} Request-Example:
            {
                file_infos: [
                    {
                        "filename": str,
                        "hash": str,
                        "pid": int,
                    }
                    ...
                ]
            }

         @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK:
            {
                "status": 0,
                "message": "success",
                "data": [
                    {
                        "file_status": int 文件状态，0:未存在，1:已存在
                        "file_id": int,
                        "token": str, 当file_status为1时，为空字段
                    }
                        ...
                ]
            }
        """
        try:
            resp = []
            for arg in self.params['file_infos']:
                arg.update({'owner': self.current_user['id']})
                data = yield self.file_service.batch_upload(arg)
                resp.append(data)
            self.success(resp)
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class FileUpdateHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/file/update 更新七牛返回的文件信息
        @apiName FileUpdate
        @apiGroup File

        @apiParam {Number} status 当为0时，下述字段不为空；为1时，代表上传失败，删除记录，除file_id外，其余为空
        @apiParam {Number} file_id
        @apiParam {Number} size
        @apiParam {String} mime
        @apiParam {String} qiniu_id

        @apiUse Success
        """
        try:
            if self.params['status'] == 1:
                yield self.file_service.delete(conds=['id=%s'], params=[self.params['file_id']])
                self.success()
                return
            arg = [
                    self.params.get('size'),
                    self.params.get('qiniu_id'),
                    self.params.get('mime'),
                    self.params['file_id'],
                    self.current_user['id']
            ]
            yield self.file_service.update(
                                            sets=[
                                                    'size=%s',
                                                    'qiniu_id=%s',
                                                    'mime=%s',
                                            ],
                                            conds=['id=%s', 'owner=%s'],
                                            params=arg
                                        )
            self.success()
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class FileDownloadHandler(BaseHandler):
    @authenticated
    @coroutine
    def get(self, file_id):
        """
        @api {get} /api/file/download/([\w\W+]) 文件下载
        @apiName FileDownload
        @apiGroup File

        @apiParam {Number} file_id 文件id

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 302 OK
            {
              跳转到七牛下载页面
            }
        """
        try:
            url = yield self.file_service.private_download_url(qiniu_id=file_id)
            self.redirect(url=url, permanent=False, status=302)
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class FileDirCreateHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/file/dir/create 创建目录
        @apiName FileDirCreate
        @apiGroup File

        @apiParam {Number} pid 上一级目录id
        @apiParam {String} dir_name 目录名字

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "message": "success",
                "data": {
                    "id": int,
                    "filename": str,
                    "size": str,
                    "qiniu_id": str,
                    "owner": str,
                    "mime": str,
                    "hash": str,
                    "type": int, 0为文件，1为文件夹， 当为1时，部分字段为空
                    "pid": int,
                    "url: str,
                    "create_time": str,
                    "update_time": str,
                }
            }
        """
        try:
            arg = {
                'filename': self.params['dir_name'],
                'pid': self.params['pid'],
                'type': 1,
                'size': 0,
                'qiniu_id': '',
                'owner': self.current_user['id'],
                'mime': '',
                'hash': '',
            }
            data = yield self.file_service.add(arg)
            resp = yield self.file_service.select(conds=['id=%s'], params=[data['id']])
            self.success(resp)
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


class FileDeleteHandler(BaseHandler):
    @is_login
    @coroutine
    def post(self):
        """
        @api {post} /api/file/delete 文件删除
        @apiName FileDelete
        @apiGroup File

        @apiParam {Number} file_ids

        @apiSuccessExample {json} Success-Example:
            HTTP/1.1 200 OK
            {
                 "status": 0,
                "message": "success",
                "data": {
                    "file_ids": []int,
                }
            }
        """
        try:
            ids = get_in_formats(field='id', contents=self.params['file_ids'])
            files = yield self.file_service.select(
                                                    fields='id, owner',
                                                    conds=[ids],
                                                    params=self.params['file_ids'],
                                                    ct=False, ut=False
                                                    )
            correct_ids = []
            incorrect_ids = []
            for file in files:
                if file['owner'] == self.current_user['id']:
                    correct_ids.append(file['id'])
                    continue
                incorrect_ids.append(file['id'])

            if correct_ids:
                arg = get_in_formats(field='id', contents=correct_ids)
                yield self.file_service.delete(
                                            conds=[arg],
                                            params=correct_ids
                )
            if incorrect_ids:
                self.error(data={'file_ids': incorrect_ids})
                return
            self.success()
        except Exception as e:
            self.error(str(e))
            self.log.error(traceback.format_exc())


