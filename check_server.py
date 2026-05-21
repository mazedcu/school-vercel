import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('104.248.226.234', username='root', password='114598Tonni')

def run_cmd(cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode().strip()

print('--- CPU ---')
print(run_cmd('lscpu | grep "^CPU(s):"'))

print('\n--- RAM ---')
print(run_cmd('free -m'))

print('\n--- Gunicorn Service ---')
print(run_cmd('cat /etc/systemd/system/gunicorn.service | grep ExecStart'))

print('\n--- Nginx Config ---')
print(run_cmd('grep -E "worker_processes|worker_connections" /etc/nginx/nginx.conf'))

print('\n--- Postgres Connections ---')
print(run_cmd('sudo -u postgres psql -c "SHOW max_connections;"'))

client.close()
