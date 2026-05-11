import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_project.settings')
django.setup()

from accounts.models import User
admins = User.objects.filter(role=User.Role.ADMIN)
for a in admins:
    print(f"Admin: {a.username} | Email: {a.email}")
    a.set_password('admin123')
    a.save()
    print(f"Password for {a.username} reset to 'admin123'")
