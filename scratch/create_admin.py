import os
import django
from django.contrib.auth import get_user_model

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_project.settings')
django.setup()

User = get_user_model()
username = 'admin2'
email = 'admin@example.com'
password = 'admin123'

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password, role=User.Role.ADMIN)
    print(f"Superuser {username} created successfully with ADMIN role.")
else:
    print(f"Superuser {username} already exists.")
