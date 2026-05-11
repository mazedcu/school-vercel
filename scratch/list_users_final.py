import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_project.settings')
django.setup()

from accounts.models import User
for u in User.objects.all():
    print(f"{u.username} | {u.email} | {u.role}")
