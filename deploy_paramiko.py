import paramiko
import sys

def deploy():
    host = '104.248.226.234'
    user = 'root'
    password = '114598Tonni'
    
    print(f"Connecting to {host}...")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(host, username=user, password=password, timeout=10)
        print("Connected successfully.")
        
        commands = [
            "cd /root/school-vercel && git pull origin main",
            "cd /root/school-vercel && source venv/bin/activate && pip install -r requirements.txt",
            "cd /root/school-vercel && source venv/bin/activate && python manage.py migrate --noinput",
            "cd /root/school-vercel && source venv/bin/activate && python manage.py collectstatic --noinput",
            "systemctl restart gunicorn"
        ]
        
        for cmd in commands:
            print(f"Executing: {cmd}")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            
            # Read output
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            
            if out:
                print(f"Output:\n{out}")
            if err:
                print(f"Error/Warning:\n{err}")
                
        print("Deployment completed successfully!")
        
    except Exception as e:
        print(f"Connection/Execution failed: {e}")
        sys.exit(1)
    finally:
        ssh.close()

if __name__ == '__main__':
    deploy()
