__author__ = 'Jon'

'''
项目配置文件, 对外, 比如项目的启动端口/数据库配置/api域名配置
'''

settings = dict()


#################################################################################################
# tornado配置
#################################################################################################
settings['port'] = 8010
settings['debug'] = True
settings['cookie_secret'] = ''
settings['token_secret'] = ''
settings['login_url'] = '/#/login'


#################################################################################################
# MYSQL配置
#################################################################################################
settings['mysql_host'] = 'localhost'
settings['mysql_port'] = 3306
settings['mysql_database'] = 'ten_dashboard'
settings['mysql_user'] = 'root'
settings['mysql_password'] = '123456'
settings['mysql_charset'] = 'utf8mb4'


#################################################################################################
# REDIS配置
#################################################################################################
settings['redis_host'] = 'localhost'
settings['redis_port'] = 6379


#################################################################################################
# 阿里云配置
#################################################################################################
settings['aliyun_id'] = ''
settings['aliyun_secret'] = ''

#################################################################################################
# 腾讯云配置
#################################################################################################
settings['qcloud_id'] = ''
settings['qcloud_secret'] = ''

#################################################################################################
# 亚马逊云配置
#################################################################################################
settings['zcloud_id'] = ''
settings['zcloud_secret'] = ''

#################################################################################################
# Git配置
#################################################################################################
settings['git_client_id'] = ''
settings['git_client_secret'] = ''
settings['git_scope'] = 'repo,user:email'
settings['git_state'] = ''

#################################################################################################
# 构建部署配置
#################################################################################################
settings['ip_for_image_creation'] = ''
settings['deploy_username'] = ''
settings['deploy_password'] = ''


#################################################################################################
# 短信平台配置
#################################################################################################
settings['sms_account_sid'] = ''
settings['sms_auth_token']  = ''
settings['sms_from_number'] = ''


#################################################################################################
# 七牛
#################################################################################################
settings['qiniu_header_bucket'] = ''
settings['qiniu_header_bucket_url'] = ''
settings['qiniu_token_timeout'] = 3600
settings['qiniu_access_key'] = ''
settings['qiniu_secret_key'] = ''
settings['qiniu_file_bucket'] = ''
settings['qiniu_file_bucket_url'] = ''


#################################################################################################
# 上传文件
#################################################################################################
settings['store_path'] = ''


#################################################################################################
# 极验证
#################################################################################################
settings['gee_id']=''
settings['gee_key']=''

#################################################################################################
# 密钥配置
#################################################################################################
settings['aes_key'] = ''

#################################################################################################
# 域名配置
#################################################################################################
settings['server_protocol'] = 'https'
settings['server_host'] = 'c.10.com'
settings['server_url']  = '{p}://{h}'.format(p=settings['server_protocol'], h=settings['server_host'])