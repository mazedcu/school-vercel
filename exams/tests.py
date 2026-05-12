from django.test import TestCase
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
