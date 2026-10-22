import datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from academics.models import ClassGroup, Section, Subject
from attendance.models import Attendance
from dashboard.overview import admin_overview, school_now
from finance.models import Invoice, InvoiceLineItem
from leaves.models import LeaveApplication
from students.models import StudentProfile
from timetable.models import TimeSlot, TimetableEntry

PW = "pw-test-1"


class TeacherDashboardTestCase(TestCase):
    def test_teacher_dashboard_loads(self):
        for role in (User.Role.TEACHER, User.Role.COORDINATOR):
            User.objects.create_user(username=f"u_{role}", password=PW, role=role)
            self.client.login(username=f"u_{role}", password=PW)
            self.assertEqual(self.client.get(reverse("teacher_dashboard")).status_code, 200, role)


class AdminDashboardTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="adm", password=PW, role=User.Role.ADMIN, first_name="Hasan")
        self.today = school_now().date()
        self.weekday = self.today.strftime("%A").lower()

    def school(self):
        """Two sections with students, a teacher, and a class scheduled today."""
        grade = ClassGroup.objects.create(name="Y9")
        self.sec_a = Section.objects.create(name="A", class_group=grade, academic_year="2026")
        self.sec_b = Section.objects.create(name="B", class_group=grade, academic_year="2026")
        self.students = []
        for i, sec in enumerate([self.sec_a, self.sec_a, self.sec_b]):
            u = User.objects.create_user(username=f"s{i}", password=PW, role=User.Role.STUDENT)
            StudentProfile.objects.create(user=u, section=sec)
            self.students.append(u)
        self.teacher = User.objects.create_user(username="t", password=PW, role=User.Role.TEACHER)
        slot = TimeSlot.objects.create(day=self.weekday, start_time=datetime.time(0, 0), end_time=datetime.time(23, 59))
        TimetableEntry.objects.create(section=self.sec_a, subject=Subject.objects.create(name="Math", code="M"),
                                      teacher=self.teacher, time_slot=slot)

    def titles(self):
        return [i["title"] for i in admin_overview()["attention"]]

    def test_empty_school_renders_all_clear(self):
        self.client.login(username="adm", password=PW)
        r = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Good ")
        self.assertContains(r, "Nothing needs you right now.")
        self.assertContains(r, "No classes are scheduled today.")

    def test_unmarked_sections_flagged_only_until_marked(self):
        self.school()
        self.assertIn("2 sections haven’t taken attendance today", self.titles())
        Attendance.objects.create(user=self.students[0], section=self.sec_a, date=self.today, status="present")
        Attendance.objects.create(user=self.students[1], section=self.sec_a, date=self.today, status="absent")
        self.assertIn("1 section hasn’t taken attendance today", self.titles())
        Attendance.objects.create(user=self.students[2], section=self.sec_b, date=self.today, status="late")
        self.assertFalse(any("attendance today" in t for t in self.titles()))

        data = admin_overview()["students"]
        self.assertEqual((data["present"], data["late"], data["absent"], data["pct"]), (1, 1, 1, 67))
        self.assertEqual([a.user for a in data["absentees"]], [self.students[1]])

    def test_no_attendance_warning_on_non_school_day(self):
        self.school()
        TimeSlot.objects.all().delete()
        self.assertFalse(any("attendance" in t for t in self.titles()))

    def test_staff_absent_without_leave(self):
        self.school()
        Attendance.objects.create(user=self.teacher, date=self.today, status="absent")
        self.assertIn("1 staff member is absent without approved leave", self.titles())
        LeaveApplication.objects.create(applicant=self.teacher, category="emergency", start_date=self.today,
                                        reason="Sick child", status=LeaveApplication.Status.ADMIN_APPROVED)
        self.assertFalse(any("staff member" in t for t in self.titles()))
        self.assertEqual(admin_overview()["staff"]["on_leave"], 1)

    def test_overdue_fees_and_pending_leave(self):
        self.school()
        inv = Invoice.objects.create(student=self.students[0], due_date=self.today - datetime.timedelta(days=3))
        InvoiceLineItem.objects.create(invoice=inv, description="Tuition", amount=Decimal("4500"))
        inv.save()
        LeaveApplication.objects.create(applicant=self.teacher, category="advance", reason="x",
                                        start_date=self.today + datetime.timedelta(days=5),
                                        status=LeaveApplication.Status.COORDINATOR_APPROVED)
        titles = self.titles()
        self.assertIn("Tk 4,500 in fees is overdue", titles)
        self.assertIn("1 leave request is waiting for your approval", titles)

        self.client.login(username="adm", password=PW)
        r = self.client.get(reverse("admin_dashboard"))
        self.assertContains(r, "Tk 4,500 in fees is overdue")
        self.assertContains(r, reverse("admin_leave_review"))

    def test_only_admin_can_open(self):
        User.objects.create_user(username="tea", password=PW, role=User.Role.TEACHER)
        self.client.login(username="tea", password=PW)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 302)
