from qiniu import Auth, urlsafe_base64_encode
from tornado.gen import coroutine
from tornado.concurrent import run_on_executor
from service.base import BaseService
from constant import QINIU_POLICY, FULL_DATE_FORMAT, DISK_DOWNLOAD_URL, QINIU_THUMB
from setting import settings


class FileService(BaseService):
    table = 'filehub'
    fields = 'id, filename, size, qiniu_id, owner, mime, hash, type, pid, lord, form, dir'

    def __init__(self, ak, sk):
        super().__init__()
        self.qiniu = Auth(access_key=ak, secret_key=sk)

    @run_on_executor
    def upload_token(self, key):
        saveas = '{bucket}:{key}'.format(bucket=settings['qiniu_file_bucket'], key=key)
        saveas_key = urlsafe_base64_encode(saveas)
        policy = QINIU_POLICY.copy()
        policy['persistentOps'] = QINIU_THUMB + '|saveas/' + saveas_key
        token = self.qiniu.upload_token(bucket=settings['qiniu_file_bucket'],
                                        expires=settings['qiniu_token_timeout'],
                                        policy=policy
                                        )
        return token

    @run_on_executor
    def private_download_url(self, qiniu_id):
        url = settings['qiniu_file_bucket_url']+'/'+qiniu_id
        expires = settings['qiniu_token_timeout']
        download_url = self.qiniu.private_download_url(url=url, expires=expires)
        return download_url

    @coroutine
    def check_file_exist(self, hash):
        sql = """
              SELECT filename, size, qiniu_id, mime 
              FROM {table} 
              WHERE hash=%s and filename <> ''
              ORDER BY update_time LIMIT 1
              """.format(table=self.table)
        cur = yield self.db.execute(sql, [hash])
        return cur.fetchone()

    @coroutine
    def batch_upload(self, params):
        arg = {
            'filename': params['filename'],
            'size': 0,
            'qiniu_id': '',
            'owner': params['owner'],
            'mime': '',
            'hash': params['hash'],
            'type': 0,
            'pid': params['pid'],
            'lord': params['lord'],
            'form': params['form']
        }
        resp = {'file_status': 0, 'token': '', 'file_id': ''}
        data = yield self.check_file_exist(params['hash'])
        if data and arg['filename'] == data['filename']:
            resp['file_status'] = 1
            arg['size'] = data['size']
            arg['qiniu_id'] = data['qiniu_id']
            arg['mime'] = data['mime']
        else:
            resp['token'] = yield self.upload_token(params['hash'])
        add_result = yield self.add(arg)

        # 获取父节点的绝对路径,用来生成新增文件的完整路径
        pdata = yield self.select(conds={'id': params['pid']}, one=True)
        pdir = (pdata.get('dir') if pdata else '/0') + '/' + str(add_result['id'])
        yield self.update(sets={'dir': pdir}, conds={'id': add_result['id']})

        resp['file_id'] = add_result['id']
        return resp

    @coroutine
    def seg_page(self, params):
        sql = """
                SELECT f.id, f.filename, f.size, f.qiniu_id, u.name, f.mime, f.hash, f.type, f.pid, f.dir,
                CONCAT('{uri}', f.qiniu_id) as url, CONCAT('{uri}', f.hash) as thumb,
                DATE_FORMAT(f.create_time, %s) as create_time, DATE_FORMAT(f.update_time, %s) as update_time 
                FROM {filehub} as f, {user} as u
                WHERE f.pid = %s AND f.form = %s AND f.lord = %s AND f.owner = u.id
                ORDER BY f.create_time DESC
              """.format(filehub=self.table, user='user', uri=DISK_DOWNLOAD_URL)
        arg = [
                FULL_DATE_FORMAT,
                FULL_DATE_FORMAT,
                params['file_id'],
                params['form'],
                params['lord']
        ]
        cur = yield self.db.execute(sql, arg)
        data = cur.fetchall()
        return data

    @coroutine
    def total_pages(self, params):
        sql = "SELECT count(*) as number FROM {table} WHERE pid = %s AND form = %s AND lord=%s".format(table=self.table)
        cur = yield self.db.execute(sql, [params['pid'], params['form'], params['lord']])
        data = cur.fetchone()
        return data['number']
