import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('104.248.226.234', username='root', password='114598Tonni')

stdin, stdout, stderr = client.exec_command('cd /root/school-vercel && git reset --hard && git clean -fd && git pull origin main')
print(stdout.read().decode().strip())
print(stderr.read().decode().strip())

client.close()
