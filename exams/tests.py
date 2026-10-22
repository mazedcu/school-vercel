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

    def test_students_and_parents_only_see_published_terms(self):
        config = AcademicPeriodConfig.objects.create(academic_year="2026", mode="term")
        t1 = ReportPeriod.objects.create(config=config, label="Term 1", sequence=1, is_published=True,
                                         start_date=self.d(2026, 1, 1), end_date=self.d(2026, 4, 30))
        t2 = ReportPeriod.objects.create(config=config, label="Term 2", sequence=2, is_published=False,
                                         start_date=self.d(2026, 5, 1), end_date=self.d(2026, 8, 31))
        self.mark(self.phy, self.quiz, 18, 20, self.d(2026, 3, 1))           # Term 1: 90%
        self.mark(self.phy, self.final, 40, 100, self.d(2026, 6, 1))         # Term 2 (unpublished): 40%
        self.SubjectComment.objects.create(student=self.student, subject=self.phy, section=self.sec,
                                           academic_year="2026", period=t2, comment="Secret term 2 remark")

        self.assertEqual(self.report(self.admin)[1]["Physics"]["score"], Decimal("55.0"))   # 0.3*90 + 0.7*40
        for viewer in (self.student, self.parent):
            r, g = self.report(viewer)
            self.assertEqual(g["Physics"]["score"], Decimal("90.0"))
            self.assertTrue(r["marks_limited"])

        self.client.login(username="s", password="pw-test-1")
        page = self.client.get(reverse("student_report"))
        self.assertContains(page, "Only marks from published terms are shown.")
        self.assertContains(page, "Provisional")
        self.assertNotContains(page, "Secret term 2 remark")

        t2.is_published = True
        t2.save()
        self.assertEqual(self.report(self.student)[1]["Physics"]["score"], Decimal("55.0"))

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
