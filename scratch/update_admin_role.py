import os
import django
from django.contrib.auth import get_user_model

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_project.settings')
django.setup()

User = get_user_model()
username = 'admin2'

try:
    u = User.objects.get(username=username)
    u.role = User.Role.ADMIN
    u.is_staff = True
    u.is_superuser = True
    u.save()
    print(f"User {username} role updated to ADMIN and superuser status verified.")
except User.DoesNotExist:
    print(f"User {username} not found.")
except Exception as e:
    print(f"Error: {e}")
