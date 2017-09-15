import json
import time
import statistics
import pymysql.cursors

db = pymysql.connect(host='192.168.56.10',
                     user='root',
                     password='hga1016xm.',
                     db='ten_dashboard',
                     charset='utf8mb4',
                     cursorclass=pymysql.cursors.DictCursor)


class server_log:

    table_hour = 'server_log_hour'
    table_day = 'server_log_day'

    def __init__(self):
        self.data = {}
        self.db = db
        self.ips = self.get_public_ip()
        self.end_time = int(time.time())
        # default one hour avg
        self.start_time = self.end_time - 3600

    def day_time(self):
        self.start_time = self.end_time - 86400
        return

    def get_public_ip(self):
        ips = []
        try:
            with self.db.cursor() as cur:
                sql = """
                    SELECT public_ip FROM server
                    """
                cur.execute(sql)
                ips = cur.fetchall()
        finally:
            self.db.close()
        return ips

    def get_data(self, ip, table):
        data = []
        try:
            with self.db.cursor() as cur:
                arg = [
                    ip,
                    self.start_time,
                    self.end_time,
                ]
                sql = """
                    SELECT content
                    FROM {table}
                    WHERE public_ip = %s AND created_time > %s
                        AND created_time < %s
                    """.format(table=table)
                cur.execute(sql, arg)
                data = cur.fetchall()
        finally:
            self.db.close()
        return data

    def cal_cpu(self, ip):
        data = []
        for x in self.get_data(ip=ip, table='cpu'):
            content = json.loads(x['content'])
            data.append(content['percent'])
        avg = statistics.mean(data)
        return {'percent': avg}

    def cal_disk(self, ip):
        total, free, percent = [], [], []
        for x in self.get_data(ip=ip, table='disk'):
            content = json.loads(x['content'])
            total.append(content['total'])
            free.append(content['free'])
            percent.append(content['percent'])
        total_avg = statistics.mean(total)
        free_avg = statistics.mean(free)
        percent_avg = statistics.mean(percent)
        return {'total': total_avg, 'free': free_avg, 'percent': percent_avg}

    def cal_memory(self, ip):
        total, free, percent, avaible = [], [], [], []
        for x in self.get_data(ip=ip, table='memory'):
            content = json.loads(x['content'])
            total.append(content['total'])
            free.append(content['free'])
            percent.append(content['percent'])
            avaible.append(content['availble'])
        total_avg = statistics.mean(total)
        free_avg = statistics.mean(free)
        percent_avg = statistics.mean(percent)
        avaible_avg = statistics.mean(avaible)
        return {
            'total': total_avg,
            'free': free_avg,
            'percent': percent_avg,
            'avaible': avaible_avg
        }

    def cal_net(self, ip):
        recv, send = [], []
        for x in self.get_data(ip=ip, table='net'):
            content = json.loads(x['content'])
            recv = content['recv_speed']
            send = content['send_speed']
        recv_avg = statistics.mean(recv)
        send_avg = statistics.mean(send)
        return {'recv_speed': recv_avg, 'send_speed': send_avg}

    def cal(self):
        cpu, disk, memory, net = {}, {}, {}, {}
        for ip in self.ips:
            cpu[ip] = self.cal_cpu(ip=ip)
            disk[ip] = self.cal_disk(ip=ip)
            memory[ip] = self.cal_memory(ip=ip)
            net[ip] = self.cal_net(ip=ip)
        self.data = {
            'cpu': cpu,
            'disk': disk,
            'memory': memory,
            'net': net
        }
        return

    def _save(self, ip, table):
        try:
            with self.db.cursor() as cursor:
                arg = [
                    ip,
                    self.start_time,
                    self.end_time,
                    self.data['cpu'],
                    self.data['disk'],
                    self.data['memory'],
                    self.data['net']
                ]
                sql = """
                        INSERT INTO {table} (
                            public_ip, start_time,
                            end_time, cpu_log,
                            disk_log, memory_log, net_log)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """.format(table=table)
                cursor.execute(sql, arg)
            self.db.commit()
        finally:
            self.db.close()

    def save_hour(self):
        for ip in self.ips:
            self._save(ip=ip, table=self.table_hour)

    def save_day(self):
        self.day_time()
        for ip in self.ips:
            self._save(ip=ip, table=self.table_day)


def main():
    server = server_log()
    print("#### start sync server performance log ####")
    print("#### start sync hour ####")
    server.save_hour()
    print("#### end sync hour ####")
    print("#### start sync day ####")
    server.save_day()
    print("#### end sync day ####")
    print("#### end sync server performance log ####")


if __name__ == '__main__':
    main()
