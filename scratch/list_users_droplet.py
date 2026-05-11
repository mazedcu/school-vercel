import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_project.settings')
django.setup()

from accounts.models import User
users = User.objects.all()
for u in users:
    print(f"User: {u.username} | Role: {u.role} | Email: {u.email}")
