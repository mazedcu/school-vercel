from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class TeacherDashboardTestCase(TestCase):
    def test_teacher_dashboard_loads(self):
        for role in (User.Role.TEACHER, User.Role.COORDINATOR):
            User.objects.create_user(username=f"u_{role}", password="pw-test-1", role=role)
            self.client.login(username=f"u_{role}", password="pw-test-1")
            self.assertEqual(self.client.get(reverse("teacher_dashboard")).status_code, 200, role)
