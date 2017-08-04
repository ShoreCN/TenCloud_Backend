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
# Git配置
#################################################################################################
settings['git_token'] = ''


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

##########################################
# 七牛
#######################################
settings['qiniu_bucket_name'] = ''
settings['qiniu_token_timeout'] = 3600
settings['qiniu_access_key'] = ''
settings['qiniu_secret_key'] = ''
