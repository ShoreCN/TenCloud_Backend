import traceback

from tornado.gen import coroutine
from handler.base import BaseHandler
from utils.decorator import is_login
from utils.context import catch


class MessageHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self, status):
        """
        @api {get} /api/messages/?(\d*)?page=\d&mode=\d 获取员工消息列表, mode值看下面的response
        @apiName MessageGetHandler
        @apiGroup Message

        @apiDescription /0未读,  /1已读, /全部。没有page,返回所有

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": [
                    {"id": 1, "content": "十全十美",
                    "url": "http",
                    "mode": "1加入企业，2企业改变信息",
                    "sub_mode": "0马上审核, 1重新提交, 2进入企业, 3马上查看"
                    "status": "0未读，1已读",
                    "tip": "cid:code"}
                ]
            }
        """
        with catch(self):
            params = {'owner': self.current_user['id']}

            if self.params.get('page'):
                params['page'] = int(self.params['page'])

            if self.params.get('mode'):
                params['mode'] = int(self.params['mode'])

            if status:
                params['status'] = int(status)

            data = yield self.message_service.fetch(params)

            self.success(data)


# 获取当前用户未读取的消息数量
class GetMessageNumHandler(BaseHandler):
    @is_login
    @coroutine
    def get(self):
        """
        @api {get} /api/messages/count?status=\d 获取员工消息数目
        @apiName GetMessageNumHandler
        @apiGroup Message

        @apiParam {status} 代表需要查询的消息状态 /0未读,  /1已读, 不传递代表查询所有类型的消息
        @apiDescription

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "status": 0,
                "msg": "success",
                "data": [
                    {
                        "num" : 0
                    }
                ]
            }
        """
        with catch(self):
            # 封装参数，用户id直接获取，status通过api参数传入
            params = {'owner': self.current_user['id']}
            if self.get_argument('status', None):
                params['status'] = int(self.get_argument('status'))

            # 调用service层数据库查询接口，取出指定参数对应的数据
            message_data = yield self.message_service.select(params)

            data = {
                'num': len(message_data)
            }
            self.success(data)
