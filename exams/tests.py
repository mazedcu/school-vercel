from django.test import TestCase
from django.urls import reverse
from decimal import Decimal
from accounts.models import User
from academics.models import ClassGroup, Section, Subject
from exams.models import AssessmentType, AssessmentRecord, StudentScore, GradeSetting, AcademicPeriodConfig, ReportPeriod, PeriodWeighting

class ExamsTestCase(TestCase):
    def setUp(self):
        # Create academic data
        self.class_group = ClassGroup.objects.create(name="Grade 10")
        self.section = Section.objects.create(
            name="A", class_group=self.class_group, academic_year="2025-26"
        )
        self.subject = Subject.objects.create(name="Math", code="MTH101")
        
        self.student = User.objects.create_user(
            username="exam_student", password="password", role=User.Role.STUDENT
        )
        
        # Create assessment types
        self.quiz = AssessmentType.objects.create(name="Quiz")
        self.final = AssessmentType.objects.create(name="Final Exam")
        
        # Create grade settings
        GradeSetting.objects.create(letter="A+", min_score=90.00, max_score=100.00, grade_point=5.0)
        GradeSetting.objects.create(letter="A", min_score=80.00, max_score=89.99, grade_point=4.0)
        GradeSetting.objects.create(letter="F", min_score=0.00, max_score=39.99, grade_point=0.0)

    def test_grade_boundaries(self):
        """Test that grade lookup logic (usually in views or services) would find correct grades."""
        # This test ensures models are working and data is consistent
        gs = GradeSetting.objects.filter(min_score__lte=95, max_score__gte=95).first()
        self.assertEqual(gs.letter, "A+")
        
        gs_fail = GradeSetting.objects.filter(min_score__lte=30, max_score__gte=30).first()
        self.assertEqual(gs_fail.letter, "F")

    def test_score_validation(self):
        """Test that marks obtained cannot exceed total marks."""
        assessment = AssessmentRecord.objects.create(
            section=self.section,
            subject=self.subject,
            assessment_type=self.quiz,
            title="Math Quiz 1",
            total_marks=Decimal('20.00'),
            date_conducted="2025-05-12"
        )
        
        # Valid score
        StudentScore.objects.create(
            assessment=assessment,
            student=self.student,
            marks_obtained=Decimal('15.00')
        )
        
        # Invalid score (should raise ValidationError)
        from django.core.exceptions import ValidationError
        score = StudentScore(
            assessment=assessment,
            student=self.student,
            marks_obtained=Decimal('25.00')
        )
        with self.assertRaises(ValidationError):
            score.full_clean()

    def test_period_reporting_setup(self):
        """Test the hierarchical period reporting configuration."""
        config = AcademicPeriodConfig.objects.create(
            academic_year="2025-26",
            mode=AcademicPeriodConfig.Mode.TERM
        )
        
        term1 = ReportPeriod.objects.create(
            config=config,
            label="1st Term",
            sequence=1,
            start_date="2025-01-01",
            end_date="2025-06-30"
        )
        
        # Add weights
        PeriodWeighting.objects.create(
            period=term1,
            assessment_type=self.quiz,
            weight_percentage=Decimal('30.00')
        )
        PeriodWeighting.objects.create(
            period=term1,
            assessment_type=self.final,
            weight_percentage=Decimal('70.00')
        )
        
        self.assertEqual(term1.weightings.count(), 2)
        total_weight = sum(w.weight_percentage for w in term1.weightings.all())
        self.assertEqual(total_weight, Decimal('100.00'))


class ReportAccessTestCase(TestCase):
    """Who may open a student's report card pages."""

    def setUp(self):
        from students.models import StudentProfile, ParentProfile
        import datetime

        self.student = User.objects.create_user(username="kid", password="pw-test-1", role=User.Role.STUDENT)
        self.other_student = User.objects.create_user(username="other_kid", password="pw-test-1", role=User.Role.STUDENT)
        StudentProfile.objects.create(user=self.student)
        StudentProfile.objects.create(user=self.other_student)

        self.parent = User.objects.create_user(username="parent", password="pw-test-1", role=User.Role.PARENT)
        ParentProfile.objects.create(user=self.parent).children.add(self.student)

        self.admin = User.objects.create_user(username="admin_user", password="pw-test-1", role=User.Role.ADMIN)

        config = AcademicPeriodConfig.objects.create(academic_year="2026")
        self.period = ReportPeriod.objects.create(
            config=config, label="Term 1", sequence=1, is_published=True,
            start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 6, 30),
        )

    def _urls_for(self, student):
        return [
            reverse("student_report_detail", args=[student.id]),
            reverse("period_report_select_student", args=[student.id]),
            reverse("period_report", args=[self.period.id, student.id]),
        ]

    def test_parent_can_view_own_child(self):
        self.client.login(username="parent", password="pw-test-1")
        for url in self._urls_for(self.student):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_parent_cannot_view_unrelated_student(self):
        self.client.login(username="parent", password="pw-test-1")
        for url in self._urls_for(self.other_student):
            self.assertRedirects(self.client.get(url), reverse("dashboard_router"), fetch_redirect_response=False, msg_prefix=url)

    def test_student_cannot_view_another_student(self):
        self.client.login(username="kid", password="pw-test-1")
        for url in self._urls_for(self.other_student):
            self.assertRedirects(self.client.get(url), reverse("dashboard_router"), fetch_redirect_response=False, msg_prefix=url)

    def test_admin_can_view_any_student(self):
        self.client.login(username="admin_user", password="pw-test-1")
        for url in self._urls_for(self.other_student):
            self.assertEqual(self.client.get(url).status_code, 200, url)


class TeacherAssessmentScopeTestCase(TestCase):
    """Teachers may only manage assessments for subjects they teach in that section."""

    def setUp(self):
        import datetime
        from students.models import StudentProfile
        from timetable.models import TimeSlot, TimetableEntry

        grade = ClassGroup.objects.create(name="Grade 9")
        self.sec_a = Section.objects.create(name="A", class_group=grade, academic_year="2026")
        self.sec_b = Section.objects.create(name="B", class_group=grade, academic_year="2026")
        self.math = Subject.objects.create(name="Math", code="M9")
        self.physics = Subject.objects.create(name="Physics", code="P9")
        self.qtype = AssessmentType.objects.create(name="Quiz")

        self.teacher = User.objects.create_user(username="t_math", password="pw-test-1", role=User.Role.TEACHER)
        self.admin = User.objects.create_user(username="adm", password="pw-test-1", role=User.Role.ADMIN)
        slot = TimeSlot.objects.create(day="sunday", start_time=datetime.time(9), end_time=datetime.time(10))
        # Teacher teaches Math in section A only.
        TimetableEntry.objects.create(section=self.sec_a, subject=self.math, teacher=self.teacher, time_slot=slot)

        self.student = User.objects.create_user(username="stu_b", password="pw-test-1", role=User.Role.STUDENT)
        StudentProfile.objects.create(user=self.student, section=self.sec_b)

        today = datetime.date(2026, 3, 1)
        self.own = AssessmentRecord.objects.create(
            section=self.sec_a, subject=self.math, assessment_type=self.qtype,
            title="Own", total_marks=Decimal("100"), date_conducted=today)
        self.other_section = AssessmentRecord.objects.create(
            section=self.sec_b, subject=self.math, assessment_type=self.qtype,
            title="Other section", total_marks=Decimal("100"), date_conducted=today)
        self.other_subject = AssessmentRecord.objects.create(
            section=self.sec_a, subject=self.physics, assessment_type=self.qtype,
            title="Other subject", total_marks=Decimal("100"), date_conducted=today)

    def login(self, username):
        self.client.login(username=username, password="pw-test-1")

    def test_teacher_can_enter_marks_for_own_class(self):
        self.login("t_math")
        self.assertEqual(self.client.get(reverse("enter_marks", args=[self.own.id])).status_code, 200)

    def test_teacher_cannot_enter_marks_for_other_classes(self):
        self.login("t_math")
        for a in (self.other_section, self.other_subject):
            r = self.client.get(reverse("enter_marks", args=[a.id]))
            self.assertRedirects(r, reverse("manage_assessments"), fetch_redirect_response=False)
        r = self.client.post(reverse("enter_marks", args=[self.other_section.id]), {f"marks_{self.student.id}": "90"})
        self.assertRedirects(r, reverse("manage_assessments"), fetch_redirect_response=False)
        self.assertFalse(StudentScore.objects.filter(assessment=self.other_section).exists())

    def test_teacher_cannot_delete_other_classes_assessment(self):
        self.login("t_math")
        self.client.post(reverse("delete_assessment", args=[self.other_subject.id]))
        self.assertTrue(AssessmentRecord.objects.filter(pk=self.other_subject.id).exists())
        self.client.post(reverse("delete_assessment", args=[self.own.id]))
        self.assertFalse(AssessmentRecord.objects.filter(pk=self.own.id).exists())

    def test_teacher_cannot_create_assessment_for_other_class(self):
        self.login("t_math")
        data = {"title": "Sneaky", "section": self.sec_b.id, "subject": self.math.id,
                "assessment_type": self.qtype.id, "total_marks": "50", "date_conducted": "2026-03-02"}
        self.client.post(reverse("manage_assessments"), data)
        self.assertFalse(AssessmentRecord.objects.filter(title="Sneaky").exists())
        data["section"] = self.sec_a.id
        self.client.post(reverse("manage_assessments"), data)
        self.assertTrue(AssessmentRecord.objects.filter(title="Sneaky").exists())

    def test_teacher_list_shows_only_own_assessments(self):
        self.login("t_math")
        r = self.client.get(reverse("manage_assessments"))
        self.assertEqual([a.id for a in r.context["recent_assessments"]], [self.own.id])
        self.assertEqual(list(r.context["sections"]), [self.sec_a])
        self.assertEqual(list(r.context["subjects"]), [self.math])

    def test_admin_sees_and_manages_everything(self):
        self.login("adm")
        r = self.client.get(reverse("manage_assessments"))
        self.assertEqual(len(r.context["recent_assessments"]), 3)
        self.assertEqual(self.client.get(reverse("enter_marks", args=[self.other_section.id])).status_code, 200)


class ReportCardRulesTestCase(TestCase):
    """The five report-card fixes: provisional scaling, no-marks, enrolment, grade gaps, publishing."""

    def setUp(self):
        import datetime
        from students.models import StudentProfile, ParentProfile
        from exams.models import SubjectWeighting, WeightingComponent, SubjectComment

        grade = ClassGroup.objects.create(name="AS")
        self.sec = Section.objects.create(name="A", class_group=grade, academic_year="2026")
        self.phy = Subject.objects.create(name="Physics", code="P")
        self.bio = Subject.objects.create(name="Biology", code="B")
        self.teacher = User.objects.create_user(username="t", password="pw-test-1", role=User.Role.TEACHER)
        self.student = User.objects.create_user(username="s", password="pw-test-1", role=User.Role.STUDENT)
        self.profile = StudentProfile.objects.create(user=self.student, section=self.sec)
        self.parent = User.objects.create_user(username="p", password="pw-test-1", role=User.Role.PARENT)
        ParentProfile.objects.create(user=self.parent).children.add(self.student)
        self.admin = User.objects.create_user(username="a", password="pw-test-1", role=User.Role.ADMIN)

        self.quiz = AssessmentType.objects.create(name="Quiz")
        self.final = AssessmentType.objects.create(name="Final")
        w = SubjectWeighting.objects.create(section=self.sec, subject=self.phy, teacher=self.teacher, academic_year="2026")
        WeightingComponent.objects.create(weighting_profile=w, assessment_type=self.quiz, weight_percentage=30)
        WeightingComponent.objects.create(weighting_profile=w, assessment_type=self.final, weight_percentage=70)
        for lo, hi, letter in [(90, 100, "A*"), (80, 89, "A"), (50, 79, "C"), (0, 49, "U")]:
            GradeSetting.objects.create(letter=letter, min_score=lo, max_score=hi)

        self.d = datetime.date
        self.SubjectComment = SubjectComment

    def mark(self, subject, atype, obtained, total, when):
        a = AssessmentRecord.objects.create(section=self.sec, subject=subject, assessment_type=atype,
                                            title=f"{atype.name} {when}", total_marks=Decimal(total), date_conducted=when)
        StudentScore.objects.create(assessment=a, student=self.student, marks_obtained=Decimal(obtained))
        return a

    def report(self, viewer=None):
        from exams.services import year_report
        r = year_report(self.student, viewer=viewer or self.admin)
        return r, {g["subject"].name: g for g in r["grades"]}

    def test_missing_final_is_not_counted_as_zero(self):
        self.mark(self.phy, self.quiz, 18, 20, self.d(2026, 3, 1))           # 90%
        r, g = self.report()
        self.assertEqual(g["Physics"]["score"], Decimal("90.0"))
        self.assertTrue(g["Physics"]["provisional"])
        self.assertEqual(g["Physics"]["letter"], "A*")
        self.mark(self.phy, self.final, 70, 100, self.d(2026, 6, 1))         # 0.3*90 + 0.7*70 = 76
        r, g = self.report()
        self.assertEqual(g["Physics"]["score"], Decimal("76.0"))
        self.assertFalse(g["Physics"]["provisional"])

    def test_subject_without_marks_shows_none_and_is_left_out_of_average(self):
        self.mark(self.phy, self.quiz, 16, 20, self.d(2026, 3, 1))           # Physics 80%
        AssessmentRecord.objects.create(section=self.sec, subject=self.bio, assessment_type=self.quiz,
                                        title="Bio quiz", total_marks=Decimal(20), date_conducted=self.d(2026, 3, 2))
        r, g = self.report()
        self.assertIsNone(g["Biology"]["score"])
        self.assertEqual(g["Biology"]["letter"], "-")
        self.assertEqual(r["overall_avg"], Decimal("80.0"))

    def test_only_enrolled_subjects_appear(self):
        self.mark(self.phy, self.quiz, 16, 20, self.d(2026, 3, 1))
        self.mark(self.bio, self.quiz, 10, 20, self.d(2026, 3, 1))
        self.assertEqual(set(self.report()[1]), {"Physics", "Biology"})      # no enrolment recorded: all subjects
        self.profile.subjects.set([self.phy])
        self.assertEqual(set(self.report()[1]), {"Physics"})

    def test_no_gap_between_grade_bands(self):
        from exams.services import get_letter_grade
        self.assertEqual(get_letter_grade(Decimal("89.5"))["letter"], "A")
        self.assertEqual(get_letter_grade(Decimal("49.9"))["letter"], "U")
        self.assertEqual(get_letter_grade(None)["letter"], "-")

    def test_students_and_parents_see_marks_as_soon_as_entered(self):
        """No publishing step: unpublished terms don't hide marks from students or parents."""
        config = AcademicPeriodConfig.objects.create(academic_year="2026", mode="term")
        t2 = ReportPeriod.objects.create(config=config, label="Term 2", sequence=2, is_published=False,
                                         start_date=self.d(2026, 5, 1), end_date=self.d(2026, 8, 31))
        self.mark(self.phy, self.quiz, 18, 20, self.d(2026, 3, 1))           # outside any term: 90%
        self.mark(self.phy, self.final, 40, 100, self.d(2026, 6, 1))         # in unpublished Term 2: 40%
        self.SubjectComment.objects.create(student=self.student, subject=self.phy, section=self.sec,
                                           academic_year="2026", period=t2, comment="Term 2 remark")

        for viewer in (self.admin, self.student, self.parent):
            r, g = self.report(viewer)
            self.assertEqual(g["Physics"]["score"], Decimal("55.0"))         # 0.3*90 + 0.7*40
            self.assertFalse(r["marks_limited"])

        self.client.login(username="s", password="pw-test-1")
        page = self.client.get(reverse("student_report"))
        self.assertContains(page, "55.0%")
        self.assertContains(page, "Term 2 remark")
        self.assertNotContains(page, "Only marks from published terms are shown.")
        self.client.login(username="p", password="pw-test-1")
        self.assertContains(self.client.get(reverse("parent_dashboard")), "55.0%")

    def test_report_pages_render_no_marks_and_provisional(self):
        self.mark(self.phy, self.quiz, 18, 20, self.d(2026, 3, 1))
        AssessmentRecord.objects.create(section=self.sec, subject=self.bio, assessment_type=self.quiz,
                                        title="Bio quiz", total_marks=Decimal(20), date_conducted=self.d(2026, 3, 2))
        self.client.login(username="a", password="pw-test-1")
        for url in [reverse("student_report_detail", args=[self.student.id]),
                    reverse("student_report_detail", args=[self.student.id]) + "?print=1",
                    reverse("student_profile_detail", args=[self.student.id])]:
            page = self.client.get(url)
            self.assertEqual(page.status_code, 200, url)
            self.assertContains(page, "No marks yet", msg_prefix=url)
            self.assertContains(page, "Provisional", msg_prefix=url)
            self.assertNotContains(page, "None%", msg_prefix=url)
        self.client.login(username="p", password="pw-test-1")
        self.assertContains(self.client.get(reverse("parent_dashboard")), "No marks yet")
        self.client.login(username="s", password="pw-test-1")
        self.assertContains(self.client.get(reverse("student_dashboard")), "No marks yet")


class ReportCardExtrasTestCase(TestCase):
    """Class average/highest, GPA, attendance, remarks and section printing."""

    def setUp(self):
        import datetime
        from students.models import StudentProfile
        from timetable.models import TimeSlot, TimetableEntry
        from attendance.models import Attendance

        self.d = datetime.date
        grade = ClassGroup.objects.create(name="Y9")
        self.sec = Section.objects.create(name="A", class_group=grade, academic_year="2026")
        self.math = Subject.objects.create(name="Math", code="M")
        self.quiz = AssessmentType.objects.create(name="Quiz")
        self.admin = User.objects.create_user(username="adm", password="pw-test-1", role=User.Role.ADMIN)
        self.teacher = User.objects.create_user(username="tea", password="pw-test-1", role=User.Role.TEACHER)
        self.other_teacher = User.objects.create_user(username="tea2", password="pw-test-1", role=User.Role.TEACHER)
        slot = TimeSlot.objects.create(day="sunday", start_time=datetime.time(9), end_time=datetime.time(10))
        TimetableEntry.objects.create(section=self.sec, subject=self.math, teacher=self.teacher, time_slot=slot)
        for lo, letter, gp in [(80, "A", 4), (60, "B", 3), (0, "F", 0)]:
            GradeSetting.objects.create(letter=letter, min_score=lo, max_score=100, grade_point=gp)

        self.students = []
        quiz = AssessmentRecord.objects.create(section=self.sec, subject=self.math, assessment_type=self.quiz,
                                               title="Q1", total_marks=Decimal(10), date_conducted=self.d(2026, 3, 1))
        for i, (roll, marks) in enumerate([("10", 9), ("2", 6), ("1", 7)]):
            u = User.objects.create_user(username=f"s{i}", password="pw-test-1", role=User.Role.STUDENT, first_name=f"S{i}")
            StudentProfile.objects.create(user=u, section=self.sec, roll_number=roll)
            StudentScore.objects.create(assessment=quiz, student=u, marks_obtained=Decimal(marks))
            self.students.append(u)
        for day, status in [(1, "present"), (2, "late"), (3, "absent"), (4, "present")]:
            Attendance.objects.create(user=self.students[0], section=self.sec, date=self.d(2026, 3, day), status=status)

    def card(self, student, viewer=None, period=None):
        from exams.services import report_card
        return report_card(student, viewer=viewer or self.admin, period=period)

    def test_class_average_highest_gpa_and_attendance(self):
        c = self.card(self.students[0])
        g = c["grades"][0]
        self.assertEqual((g["score"], g["class_avg"], g["class_high"]), (Decimal("90.0"), Decimal("73.3"), Decimal("90.0")))
        self.assertEqual(c["gpa"], Decimal("4.00"))
        self.assertEqual(c["attendance"], {"present": 2, "late": 1, "absent": 1, "total": 4, "pct": 75})

    def test_section_print_orders_by_roll_number_and_shows_everyone(self):
        self.client.login(username="tea", password="pw-test-1")
        r = self.client.get(reverse("print_section_report_cards"), {"section": self.sec.id})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([c["profile"].roll_number for c in r.context["cards"]], ["1", "2", "10"])
        self.assertContains(r, "3 report cards, one per page")
        self.client.login(username=self.students[0].username, password="pw-test-1")
        self.assertEqual(self.client.get(reverse("print_section_report_cards"), {"section": self.sec.id}).status_code, 302)

    def test_term_print_uses_only_that_terms_marks(self):
        config = AcademicPeriodConfig.objects.create(academic_year="2026", mode="term")
        t2 = ReportPeriod.objects.create(config=config, label="Term 2", sequence=2, is_published=True,
                                         start_date=self.d(2026, 5, 1), end_date=self.d(2026, 8, 31))
        c = self.card(self.students[0], period=t2)
        self.assertEqual(c["grades"], [])  # the March quiz is outside Term 2
        self.assertEqual(c["attendance"]["total"], 0)

    def test_remarks_permissions_and_display(self):
        url = reverse("save_report_remarks")
        s = self.students[0]
        # A teacher who teaches the section can write the class teacher's remark, not the principal's
        self.client.login(username="tea", password="pw-test-1")
        self.client.post(url, {"student": s.id, "class_teacher_remark": "Works hard.", "principal_remark": "Hacked"})
        # A teacher who doesn't teach the section can't write anything
        self.client.login(username="tea2", password="pw-test-1")
        self.client.post(url, {"student": s.id, "class_teacher_remark": "Overwritten"})
        # The admin can write the principal's remark
        self.client.login(username="adm", password="pw-test-1")
        self.client.post(url, {"student": s.id, "principal_remark": "Well done."})

        c = self.card(s)
        self.assertEqual(c["remarks"], {"class_teacher": "Works hard.", "principal": "Well done."})
        page = self.client.get(reverse("student_report_detail", args=[s.id]) + "?print=1")
        self.assertContains(page, "Works hard.")
        self.assertContains(page, "Well done.")
        self.assertContains(page, "Class average")


class CTProgressReportTestCase(TestCase):
    def setUp(self):
        import datetime
        from students.models import StudentProfile

        self.d = datetime.date
        grade = ClassGroup.objects.create(name="Y9")
        self.sec = Section.objects.create(name="A", class_group=grade, academic_year="2026")
        self.math = Subject.objects.create(name="Math", code="M")
        self.bio = Subject.objects.create(name="Biology", code="B")
        AssessmentType.objects.get_or_create(name="Practical")
        self.ct, _ = AssessmentType.objects.get_or_create(name="Class Test")
        self.teacher = User.objects.create_user(username="tea", password="pw-test-1", role=User.Role.TEACHER)
        GradeSetting.objects.create(letter="A", min_score=80, max_score=100)
        GradeSetting.objects.create(letter="F", min_score=0, max_score=79)

        self.a = User.objects.create_user(username="a", password="pw-test-1", role=User.Role.STUDENT, first_name="Amin")
        self.b = User.objects.create_user(username="b", password="pw-test-1", role=User.Role.STUDENT, first_name="Bina")
        self.gone = User.objects.create_user(username="g", password="pw-test-1", role=User.Role.STUDENT, is_active=False)
        self.pa = StudentProfile.objects.create(user=self.a, section=self.sec, roll_number="2")
        StudentProfile.objects.create(user=self.b, section=self.sec, roll_number="1")
        StudentProfile.objects.create(user=self.gone, section=self.sec, roll_number="3")

        self.ct1 = self.make_ct(self.math, "CT 1", self.d(2026, 2, 1))
        self.ct2 = self.make_ct(self.math, "CT 2", self.d(2026, 3, 1))
        self.bio1 = self.make_ct(self.bio, "CT 1", self.d(2026, 2, 5))
        self.new = self.make_ct(self.math, "CT 3", self.d(2026, 3, 20))   # no marks entered yet
        self.mark(self.ct1, self.a, 18)
        self.mark(self.ct1, self.b, 10)
        self.mark(self.ct2, self.b, 12)          # Amin missed CT 2
        self.mark(self.bio1, self.b, 16)
        self.mark(self.ct1, self.gone, 1)

    def make_ct(self, subject, title, when):
        return AssessmentRecord.objects.create(section=self.sec, subject=subject, assessment_type=self.ct,
                                               title=title, total_marks=Decimal(20), date_conducted=when)

    def mark(self, record, student, marks):
        StudentScore.objects.create(assessment=record, student=student, marks_obtained=Decimal(marks))

    def report(self):
        from exams.ct_report import ct_progress
        return ct_progress(self.sec, self.ct, self.d(2026, 1, 1), self.d(2026, 4, 30))

    def test_missing_marks_are_not_zero_and_unmarked_tests_are_skipped(self):
        r = self.report()
        amin = next(s for s in r["students"] if s["student"] == self.a)
        math = amin["by_subject"][self.math.id]
        self.assertEqual(math["pct"], Decimal("90.0"))        # 18/20, CT 2 not counted as zero
        self.assertEqual(math["missing"], 1)
        self.assertEqual([t["ct"].title for t in math["tests"]], ["CT 1", "CT 2"])  # CT 3 left out
        self.assertEqual(r["unmarked"], [self.new])

    def test_only_current_students_in_roll_order_and_enrolled_subjects(self):
        self.pa.subjects.set([self.math])
        r = self.report()
        self.assertEqual([s["student"] for s in r["students"]], [self.b, self.a])   # inactive student left out
        amin = next(s for s in r["students"] if s["student"] == self.a)
        self.assertNotIn(self.bio.id, amin["by_subject"])
        self.assertIsNone(amin["cells"][[x["subject"] for x in r["subjects"]].index(self.bio)])
        stats = {x["subject"].name: x for x in r["subjects"]}
        self.assertEqual(stats["Math"]["avg"], Decimal("72.5"))    # Amin 90, Bina 55
        self.assertEqual(stats["Math"]["high"], Decimal("90.0"))

    def test_class_test_type_detection_ignores_words_containing_ct(self):
        from exams.ct_report import detect_ct_type
        practical0 = AssessmentType.objects.get(name="Practical")
        self.assertEqual(detect_ct_type([practical0, self.ct]), self.ct)
        practical = AssessmentType.objects.get(name="Practical")
        project, _ = AssessmentType.objects.get_or_create(name="Project")
        self.assertIsNone(detect_ct_type([practical, project]))
        weekly, _ = AssessmentType.objects.get_or_create(name="Weekly CT")
        self.assertEqual(detect_ct_type([practical, weekly]), weekly)

    def test_print_uses_configured_term_and_both_layouts(self):
        config = AcademicPeriodConfig.objects.create(academic_year="2026", mode="term")
        term = ReportPeriod.objects.create(config=config, label="Term 1", sequence=1,
                                           start_date=self.d(2026, 1, 1), end_date=self.d(2026, 6, 30))
        self.client.login(username="tea", password="pw-test-1")
        url = reverse("ct_progress_report_print")
        r = self.client.get(url, {"section": self.sec.id, "period": term.id, "upto": "2026-02-15"})
        self.assertEqual((r.context["start"], r.context["end"]), (self.d(2026, 1, 1), self.d(2026, 2, 15)))
        self.assertContains(r, "absent / not entered")
        self.assertContains(r, "Term 1")
        r = self.client.get(url, {"section": self.sec.id, "period": term.id, "layout": "marksheet"})
        self.assertContains(r, "Class average")
        self.assertContains(r, "Some class tests were missed or not entered")
        r = self.client.get(url, {"section": self.sec.id, "month": 3, "year": 2026})   # no term chosen: old month mode
        self.assertEqual((r.context["start"], r.context["end"]), (self.d(2026, 1, 1), self.d(2026, 3, 31)))
        self.assertEqual(self.client.get(reverse("ct_progress_report")).status_code, 200)

    def test_students_cannot_open_it(self):
        self.client.login(username="a", password="pw-test-1")
        self.assertEqual(self.client.get(reverse("ct_progress_report")).status_code, 302)


class NotApplicableMarksTestCase(TestCase):
    """Marks entered as N/A are left out of results: not zero, not missing, not provisional."""

    def setUp(self):
        import datetime
        from students.models import StudentProfile
        from exams.models import SubjectWeighting, WeightingComponent

        self.d = datetime.date
        grade = ClassGroup.objects.create(name="Y9")
        self.sec = Section.objects.create(name="A", class_group=grade, academic_year="2026")
        self.phy = Subject.objects.create(name="Physics", code="P")
        self.art = Subject.objects.create(name="Art", code="A")
        self.quiz, _ = AssessmentType.objects.get_or_create(name="Class Test")
        self.final, _ = AssessmentType.objects.get_or_create(name="Final Term")
        self.admin = User.objects.create_user(username="adm", password="pw-test-1", role=User.Role.ADMIN)
        teacher = User.objects.create_user(username="t", password="pw-test-1", role=User.Role.TEACHER)
        self.s1 = User.objects.create_user(username="s1", password="pw-test-1", role=User.Role.STUDENT)
        self.s2 = User.objects.create_user(username="s2", password="pw-test-1", role=User.Role.STUDENT)
        StudentProfile.objects.create(user=self.s1, section=self.sec, roll_number="1")
        StudentProfile.objects.create(user=self.s2, section=self.sec, roll_number="2")
        w = SubjectWeighting.objects.create(section=self.sec, subject=self.phy, teacher=teacher, academic_year="2026")
        WeightingComponent.objects.create(weighting_profile=w, assessment_type=self.quiz, weight_percentage=30)
        WeightingComponent.objects.create(weighting_profile=w, assessment_type=self.final, weight_percentage=70)
        GradeSetting.objects.create(letter="A", min_score=80, max_score=100)
        GradeSetting.objects.create(letter="F", min_score=0, max_score=79)
        self.ct = self.record(self.phy, self.quiz, "CT 1", 20)
        self.exam = self.record(self.phy, self.final, "Final", 100)

    def record(self, subject, atype, title, total):
        return AssessmentRecord.objects.create(section=self.sec, subject=subject, assessment_type=atype, title=title,
                                               total_marks=Decimal(total), date_conducted=self.d(2026, 3, 1))

    def score(self, record, student, marks=0, na=False):
        StudentScore.objects.create(assessment=record, student=student, marks_obtained=Decimal(marks), not_applicable=na)

    def card(self, student):
        from exams.services import report_card
        return report_card(student, viewer=self.admin)

    def test_marks_entry_saves_and_clears_na(self):
        self.client.login(username="adm", password="pw-test-1")
        url = reverse("enter_marks", args=[self.ct.id])
        self.client.post(url, {f"marks_{self.s1.id}": "15", f"na_{self.s2.id}": "on", f"marks_{self.s2.id}": "9"})
        self.assertEqual(StudentScore.objects.get(student=self.s1).marks_obtained, Decimal("15"))
        na = StudentScore.objects.get(student=self.s2)
        self.assertTrue(na.not_applicable)
        self.assertEqual(na.marks_obtained, 0)

        page = self.client.get(url)
        self.assertEqual([s["na"] for s in page.context["students_marks"]], [False, True])
        self.assertContains(page, "1 of 2 entered, 1 N/A")

        # Unticking N/A with no mark returns the student to "not entered"
        self.client.post(url, {f"marks_{self.s1.id}": "15"})
        self.assertFalse(StudentScore.objects.filter(student=self.s2).exists())
        # Entering a mark after N/A replaces it
        self.score(self.ct, self.s2, na=True)
        self.client.post(url, {f"marks_{self.s2.id}": "12"})
        s2 = StudentScore.objects.get(student=self.s2)
        self.assertEqual((s2.not_applicable, s2.marks_obtained), (False, Decimal("12")))

    def test_na_exam_is_left_out_without_making_grade_provisional(self):
        self.score(self.ct, self.s1, 18)             # 90%
        self.score(self.exam, self.s1, na=True)      # final doesn't apply
        g = self.card(self.s1)["grades"][0]
        self.assertEqual(g["score"], Decimal("90.0"))
        self.assertFalse(g["provisional"])
        self.assertEqual([d["not_applicable"] for d in g["details"]], [False, True])

        self.score(self.ct, self.s2, 18)             # same quiz, final simply not entered
        g2 = self.card(self.s2)["grades"][0]
        self.assertEqual(g2["score"], Decimal("90.0"))
        self.assertTrue(g2["provisional"])

    def test_subject_all_na_shows_not_applicable_and_is_out_of_average(self):
        art_ct = self.record(self.art, self.quiz, "Art CT", 10)
        self.score(self.ct, self.s1, 16)             # Physics 80%
        self.score(art_ct, self.s1, na=True)
        self.score(art_ct, self.s2, 5)               # Art class average comes only from s2
        c = self.card(self.s1)
        art = next(g for g in c["grades"] if g["subject"] == self.art)
        self.assertIsNone(art["score"])
        self.assertTrue(art["not_applicable"])
        self.assertEqual(art["class_avg"], Decimal("50.0"))
        self.assertEqual(c["overall_avg"], Decimal("80.0"))
        self.client.login(username="adm", password="pw-test-1")
        self.assertContains(self.client.get(reverse("student_report_detail", args=[self.s1.id]) + "?print=1"),
                            "Not applicable")

    def test_ct_report_shows_na_and_ignores_it(self):
        from exams.ct_report import ct_progress
        ct2 = self.record(self.phy, self.quiz, "CT 2", 20)
        self.score(self.ct, self.s1, 10)
        self.score(ct2, self.s1, na=True)
        self.score(self.ct, self.s2, 20)
        self.score(ct2, self.s2, 16)
        r = ct_progress(self.sec, self.quiz, self.d(2026, 1, 1), self.d(2026, 12, 31))
        s1 = r["students"][0]["by_subject"][self.phy.id]
        self.assertEqual((s1["pct"], s1["missing"]), (Decimal("50.0"), 0))
        self.assertTrue(s1["tests"][1]["not_applicable"])
        self.assertEqual(s1["tests"][1]["class_avg"], Decimal("16.0"))   # CT 2 average ignores the N/A
        self.client.login(username="adm", password="pw-test-1")
        page = self.client.get(reverse("ct_progress_report_print"),
                               {"section": self.sec.id, "month": 3, "year": 2026, "ct_type": self.quiz.id})
        self.assertContains(page, "N/A")
