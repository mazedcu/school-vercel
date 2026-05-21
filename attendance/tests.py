import json
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from accounts.models import User
from academics.models import ClassGroup, Section
from students.models import StudentProfile, TeacherProfile
from attendance.models import Attendance

class AttendanceAPITestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.token = getattr(settings, 'ATTENDANCE_API_TOKEN', 'opdev_default_secret')
        
        # Create academic structure
        self.class_group = ClassGroup.objects.create(name="Grade 10")
        self.section = Section.objects.create(
            name="A", class_group=self.class_group, academic_year="2025-26"
        )
        
        # Create student with biometric ID
        self.student_user = User.objects.create_user(
            username="bio_student", password="password", role=User.Role.STUDENT
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user, section=self.section, biometric_id="101"
        )
        
        # Create teacher with biometric ID
        self.teacher_user = User.objects.create_user(
            username="bio_teacher", password="password", role=User.Role.TEACHER
        )
        self.teacher_profile = TeacherProfile.objects.create(
            user=self.teacher_user, biometric_id="T202"
        )

    def test_sync_attendance_success(self):
        """Test successful sync of student and teacher attendance logs."""
        url = reverse('api_sync_attendance')
        today = timezone.now().date().isoformat()
        
        payload = {
            "token": self.token,
            "logs": [
                {"biometric_id": "101", "timestamp": f"{today} 08:30:00"},
                {"biometric_id": "T202", "timestamp": f"{today} 08:45:00"}
            ]
        }
        
        response = self.client.post(
            url, data=json.dumps(payload), content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['processed'], 2)
        
        # Verify DB records
        self.assertTrue(Attendance.objects.filter(user=self.student_user, date=today).exists())
        self.assertTrue(Attendance.objects.filter(user=self.teacher_user, date=today).exists())

    def test_sync_attendance_unauthorized(self):
        """Test that invalid token returns 401."""
        url = reverse('api_sync_attendance')
        payload = {"token": "wrong_token", "logs": []}
        
        response = self.client.post(
            url, data=json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)

    def test_sync_attendance_duplicate_ignored(self):
        """Test that multiple logs for the same user on the same day only create one record."""
        url = reverse('api_sync_attendance')
        today = timezone.now().date().isoformat()
        
        payload = {
            "token": self.token,
            "logs": [
                {"biometric_id": "101", "timestamp": f"{today} 08:30:00"},
                {"biometric_id": "101", "timestamp": f"{today} 16:30:00"}
            ]
        }
        
        response = self.client.post(
            url, data=json.dumps(payload), content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['processed'], 1) # Only the first one creates a record
        self.assertEqual(Attendance.objects.filter(user=self.student_user, date=today).count(), 1)

    def test_sync_attendance_invalid_id(self):
        """Test that logs with unknown biometric IDs are reported as errors but don't crash."""
        url = reverse('api_sync_attendance')
        today = timezone.now().date().isoformat()
        
        payload = {
            "token": self.token,
            "logs": [
                {"biometric_id": "999", "timestamp": f"{today} 09:00:00"}
            ]
        }
        
        response = self.client.post(
            url, data=json.dumps(payload), content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['processed'], 0)
        self.assertIn("No user found for Biometric ID 999", data['errors'][0])


class AttendanceNotApplicableTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="admin", password="password", role=User.Role.ADMIN
        )
        self.student_user = User.objects.create_user(
            username="student1", password="password", role=User.Role.STUDENT
        )
        self.class_group = ClassGroup.objects.create(name="Grade 10")
        self.section = Section.objects.create(
            name="A", class_group=self.class_group, academic_year="2025-26"
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user, section=self.section
        )

    def test_student_report_excludes_na(self):
        """Test that the student attendance report excludes 'na' days from total_days."""
        today = timezone.now().date()
        # Mark 1 day present, 1 day 'na'
        Attendance.objects.create(
            user=self.student_user, section=self.section, date=today, status=Attendance.Status.PRESENT
        )
        import datetime
        another_day = today - datetime.timedelta(days=1)
        Attendance.objects.create(
            user=self.student_user, section=self.section, date=another_day, status=Attendance.Status.NOT_APPLICABLE
        )
        
        self.client.login(username="admin", password="password")
        url = reverse('student_attendance_report', kwargs={'student_id': self.student_user.id})
        response = self.client.get(f"{url}?month={today.year}-{today.month:02d}")
        self.assertEqual(response.status_code, 200)
        
        import calendar
        num_days = calendar.monthrange(today.year, today.month)[1]
        
        # total_days should be num_days - 1
        self.assertEqual(response.context['total_days'], num_days - 1)
        self.assertEqual(response.context['present_count'], 1)

    def test_attendance_report_excludes_na_from_total(self):
        """Test that monthly attendance summary report does not increment total days for 'na'."""
        today = timezone.now().date()
        Attendance.objects.create(
            user=self.student_user, section=self.section, date=today, status=Attendance.Status.NOT_APPLICABLE
        )
        
        self.client.login(username="admin", password="password")
        url = reverse('attendance_report')
        response = self.client.get(f"{url}?section={self.section.id}&month={today.year}-{today.month:02d}")
        self.assertEqual(response.status_code, 200)
        
        # Verify that total is 0 in the stats because the only marked day is N/A
        stats = response.context['report_data'][0] # first student profile
        self.assertEqual(stats['total'], 0)
        self.assertEqual(stats['na'], 1)

