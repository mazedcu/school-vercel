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


class StudentDashboardTestCase(TestCase):
    def setUp(self):
        import datetime
        from academics.models import Subject
        from exams.models import AssessmentType, AssessmentRecord, StudentScore
        self.d = datetime.date
        grade = ClassGroup.objects.create(name="Y9")
        self.sec = Section.objects.create(name="A", class_group=grade, academic_year="2026")
        self.s = User.objects.create_user(username="stu", password=PW, role=User.Role.STUDENT, first_name="Rafi")
        StudentProfile.objects.create(user=self.s, section=self.sec, roll_number="7")
        math = Subject.objects.create(name="Math", code="M")
        ct, _ = AssessmentType.objects.get_or_create(name="Class Test")
        a = AssessmentRecord.objects.create(section=self.sec, subject=math, assessment_type=ct, title="CT 1",
                                            total_marks=Decimal(20), date_conducted=self.d(2026, 3, 1))
        StudentScore.objects.create(assessment=a, student=self.s, marks_obtained=Decimal(15))
        inv = Invoice.objects.create(student=self.s, due_date=self.d(2026, 3, 10), fee_month="March")
        InvoiceLineItem.objects.create(invoice=inv, description="Tuition", amount=Decimal("4500"))
        inv.save()
        from finance.models import Payment
        Payment.objects.create(invoice=inv, amount=Decimal("1500"))
        inv.save()

    def test_dashboard_shows_results_latest_marks_and_correct_fee_balance(self):
        self.client.login(username="stu", password=PW)
        r = self.client.get(reverse("student_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Rafi")
        self.assertContains(r, "Y9 – A, roll 7")
        self.assertContains(r, "Math: CT 1")             # latest marks
        self.assertContains(r, "75.0%")                  # Math result
        self.assertEqual(r.context["fees"]["outstanding"], Decimal("3000"))
        self.assertContains(r, "Balance <b style=\"color:var(--bad);\">Tk 3,000</b>", html=False)

    def test_student_without_section(self):
        lone = User.objects.create_user(username="lone", password=PW, role=User.Role.STUDENT)
        StudentProfile.objects.create(user=lone)
        self.client.login(username="lone", password=PW)
        self.assertContains(self.client.get(reverse("student_dashboard")), "Your class hasn't been set yet")


class AppDownloadTestCase(TestCase):
    ANDROID = "Mozilla/5.0 (Linux; Android 14; SM-A546E) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36"
    IN_APP = ANDROID + " RadonAcademyApp/1.1"
    DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
    IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"

    def test_download_page_is_public(self):
        r = self.client.get(reverse("app_page"), HTTP_USER_AGENT=self.ANDROID)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Download for Android")
        self.assertContains(r, "How to install")
        self.assertContains(self.client.get(reverse("app_page"), HTTP_USER_AGENT=self.IPHONE), "The app is for Android phones")
        self.assertContains(self.client.get(reverse("app_page"), HTTP_USER_AGENT=self.IN_APP), "already using the Radon Academy app")

    def test_download_serves_the_apk(self):
        from django.conf import settings
        r = self.client.get(reverse("app_download"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/vnd.android.package-archive")
        self.assertIn(f'filename="RadonAcademy-{settings.ANDROID_APP["version"]}.apk"', r["Content-Disposition"])
        body = b"".join(r.streaming_content)
        self.assertEqual(body[:2], b"PK")              # an APK is a zip file
        self.assertEqual(len(body), settings.ANDROID_APP["file"].stat().st_size)

    def test_banner_only_in_android_browsers(self):
        login = reverse("login")
        self.assertContains(self.client.get(login, HTTP_USER_AGENT=self.ANDROID), 'id="appBanner"')
        for ua in (self.IN_APP, self.DESKTOP, self.IPHONE):
            self.assertNotContains(self.client.get(login, HTTP_USER_AGENT=ua), 'id="appBanner"', msg_prefix=ua)
