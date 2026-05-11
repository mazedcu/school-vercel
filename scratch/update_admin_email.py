import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_project.settings')
django.setup()

from accounts.models import User
count = User.objects.filter(role=User.Role.ADMIN).update(email='mazedcu@gmail.com')
print(f"Updated {count} admin user(s) to mazedcu@gmail.com")
