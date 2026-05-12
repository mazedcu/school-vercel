"""
exams/services.py — Centralised business logic for exam grade calculations.

All grade functions previously duplicated between views.py live here.
Views should import from here — never duplicate this logic.
"""
import logging
from decimal import Decimal



from .models import (
    SubjectWeighting, StudentScore, GradeSetting,
    AssessmentType, AssessmentRecord
)

logger = logging.getLogger(__name__)


# ─── LETTER GRADE ─────────────────────────────────────────────────────────────

def get_letter_grade(score, grade_settings=None):
    """
    Return {'letter', 'remark', 'grade_point'} for a given percentage score.

    Args:
        score: Decimal or float percentage (0-100)
        grade_settings: Optional pre-fetched queryset/list of GradeSetting.
                        If None, fetches from DB (use pre-fetched list when
                        calling inside loops to avoid N+1).
    """
    if grade_settings is None:
        grade_settings = GradeSetting.objects.all()

    for g in grade_settings:
        if g.min_score <= score <= g.max_score:
            return {'letter': g.letter, 'remark': g.remark, 'grade_point': g.grade_point}
    return {'letter': '-', 'remark': '', 'grade_point': Decimal('0')}


# ─── WEIGHTED GRADE (overall report card) ────────────────────────────────────

def calculate_student_grade(student, subject, section):
    """
    Calculate weighted final grade (0-100) for a student in a subject
    using the teacher-configured SubjectWeighting for that section.

    Falls back to a simple unweighted average if no weighting is configured.

    Args:
        student: User instance (role=STUDENT)
        subject: Subject instance
        section: Section instance

    Returns:
        Decimal: Score as a percentage (0.0 – 100.0)
    """
    try:
        weighting = SubjectWeighting.objects.get(
            section=section, subject=subject, academic_year=section.academic_year
        )
    except SubjectWeighting.DoesNotExist:
        # Fallback: simple unweighted average across all assessments
        scores = StudentScore.objects.filter(
            student=student,
            assessment__subject=subject,
            assessment__section=section
        ).select_related('assessment')
        if not scores.exists():
            return Decimal('0')
        total_pct = Decimal('0')
        count = 0
        for s in scores:
            if s.assessment.total_marks > 0:
                total_pct += (s.marks_obtained / s.assessment.total_marks) * 100
                count += 1
        return round(total_pct / count, 1) if count > 0 else Decimal('0')

    total_weighted = Decimal('0')
    for comp in weighting.components.select_related('assessment_type').all():
        weight = comp.weight_percentage / Decimal('100')
        scores = StudentScore.objects.filter(
            student=student,
            assessment__subject=subject,
            assessment__section=section,
            assessment__assessment_type=comp.assessment_type
        ).select_related('assessment')
        if not scores.exists():
            continue
        total_pct = Decimal('0')
        count = 0
        for s in scores:
            if s.assessment.total_marks > 0:
                total_pct += (s.marks_obtained / s.assessment.total_marks) * 100
                count += 1
        if count > 0:
            avg = total_pct / count
            total_weighted += avg * weight
    return round(total_weighted, 1)


def get_grade_details(student, subject, section):
    """
    Return a per-assessment-type breakdown for the report card.

    Returns:
        list of dicts: [{'type', 'weight', 'avg_pct', 'weighted_score'}, ...]
    """
    details = []
    try:
        weighting = SubjectWeighting.objects.get(
            section=section, subject=subject, academic_year=section.academic_year
        )
    except SubjectWeighting.DoesNotExist:
        return details

    for comp in weighting.components.select_related('assessment_type').all():
        scores = StudentScore.objects.filter(
            student=student,
            assessment__subject=subject,
            assessment__section=section,
            assessment__assessment_type=comp.assessment_type
        ).select_related('assessment')

        total_pct = Decimal('0')
        count = 0
        for s in scores:
            if s.assessment.total_marks > 0:
                total_pct += (s.marks_obtained / s.assessment.total_marks) * 100
                count += 1
        avg = round(total_pct / count, 1) if count > 0 else Decimal('0')
        weighted = round(avg * comp.weight_percentage / Decimal('100'), 1)
        details.append({
            'type': comp.assessment_type.name,
            'weight': comp.weight_percentage,
            'avg_pct': avg,
            'weighted_score': weighted,
        })
    return details


# ─── PERIOD-BASED GRADE ───────────────────────────────────────────────────────

def calculate_period_grade(student, subject, section, period, period_weights, at_name_map=None):
    """
    Calculate weighted grade for a student within a specific reporting period.

    Args:
        student:        User instance
        subject:        Subject instance
        section:        Section instance
        period:         ReportPeriod instance
        period_weights: dict {assessment_type_id: weight_percentage}
        at_name_map:    Optional pre-fetched dict {id: name} for AssessmentType.
                        Pass this in loops to avoid N+1 queries.

    Returns:
        (Decimal score, list details)
    """
    details = []

    if not period_weights:
        # No weights configured — fall back to simple average
        scores = StudentScore.objects.filter(
            student=student,
            assessment__subject=subject,
            assessment__section=section,
            assessment__date_conducted__gte=period.start_date,
            assessment__date_conducted__lte=period.end_date,
        ).select_related('assessment')
        if not scores.exists():
            return Decimal('0'), details
        total_pct = Decimal('0')
        count = 0
        for s in scores:
            if s.assessment.total_marks > 0:
                total_pct += (s.marks_obtained / s.assessment.total_marks) * 100
                count += 1
        return (round(total_pct / count, 1) if count > 0 else Decimal('0')), details

    # Build name map if not provided (allows caller to pre-fetch and avoid N+1)
    if at_name_map is None:
        at_name_map = dict(AssessmentType.objects.filter(
            id__in=period_weights.keys()
        ).values_list('id', 'name'))

    total_weighted = Decimal('0')
    for at_id, weight_pct in period_weights.items():
        weight = weight_pct / Decimal('100')
        scores = StudentScore.objects.filter(
            student=student,
            assessment__subject=subject,
            assessment__section=section,
            assessment__assessment_type_id=at_id,
            assessment__date_conducted__gte=period.start_date,
            assessment__date_conducted__lte=period.end_date,
        ).select_related('assessment')

        at_name = at_name_map.get(at_id, '')

        if not scores.exists():
            details.append({
                'type': at_name,
                'weight': weight_pct,
                'avg_pct': Decimal('0'),
                'weighted_score': Decimal('0'),
            })
            continue

        total_pct = Decimal('0')
        count = 0
        for s in scores:
            if s.assessment.total_marks > 0:
                total_pct += (s.marks_obtained / s.assessment.total_marks) * 100
                count += 1

        avg = round(total_pct / count, 1) if count > 0 else Decimal('0')
        weighted = round(avg * weight, 1)
        total_weighted += weighted

        details.append({
            'type': at_name,
            'weight': weight_pct,
            'avg_pct': avg,
            'weighted_score': weighted,
        })

    return round(total_weighted, 1), details
