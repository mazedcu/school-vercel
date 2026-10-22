"""
exams/services.py — Centralised business logic for exam grade calculations.

All grade and report-card numbers come from here, so every page (report cards,
dashboards, profiles) shows the same result. Views should import from here —
never duplicate this logic.

Rules:
- A subject's grade only counts the assessment types that have marks so far.
  Their weights are scaled up to 100%, and the grade is flagged `provisional`
  until every weighted type has marks. (Previously a missing final exam counted
  as zero, so a 90% quiz score showed as 27%.)
- A subject with no marks at all has score None ("No marks yet") and is left
  out of the overall average.
- Letter grades are chosen by minimum score only (highest band whose minimum is
  met), so there are no gaps between bands such as 89.5 between 80–89 and 90–100.
- Students and parents only see marks from published report periods, when the
  academic year has report periods configured.
- If a student has enrolled subjects, only those appear on their report.
"""
import logging
from decimal import Decimal

from django.db.models import Q

from accounts.models import User
from academics.models import Subject
from students.models import StudentProfile
from .models import (
    AcademicPeriodConfig, AssessmentType, GradeSetting, StudentScore, SubjectWeighting,
)

logger = logging.getLogger(__name__)

HUNDRED = Decimal('100')
NO_GRADE = {'letter': '-', 'remark': '', 'grade_point': Decimal('0')}
RESTRICTED_VIEWERS = (User.Role.STUDENT, User.Role.PARENT)


# ─── LETTER GRADE ─────────────────────────────────────────────────────────────

def get_letter_grade(score, grade_settings=None):
    """
    Return {'letter', 'remark', 'grade_point'} for a percentage score.

    The grade is the highest band whose minimum score the student reached, so
    bands never leave gaps. `score=None` (no marks) returns '-'.
    Pass a pre-fetched `grade_settings` list inside loops to avoid extra queries.
    """
    if score is None:
        return dict(NO_GRADE)
    if grade_settings is None:
        grade_settings = GradeSetting.objects.all()
    for g in sorted(grade_settings, key=lambda g: g.min_score, reverse=True):
        if score >= g.min_score:
            return {'letter': g.letter, 'remark': g.remark, 'grade_point': g.grade_point}
    return dict(NO_GRADE)


# ─── CORE CALCULATION ─────────────────────────────────────────────────────────

def _average_pct(scores):
    """Mean percentage of a StudentScore queryset, or None if there are no usable marks."""
    total, count = Decimal('0'), 0
    for s in scores:
        if s.assessment.total_marks > 0:
            total += (s.marks_obtained / s.assessment.total_marks) * HUNDRED
            count += 1
    return (total / count) if count else None


def subject_result(student, subject, section, weights=None, at_names=None, marks_filter=None):
    """
    Weighted result for one student in one subject.

    weights:      {assessment_type_id: weight_percentage}; None/empty = simple average.
    marks_filter: optional Q on StudentScore (e.g. a date range or published periods).

    Returns {'score': Decimal|None, 'provisional': bool, 'details': [...]}.
    Each detail is {'type', 'weight', 'avg_pct' (None if no marks), 'weighted_score'}.
    """
    scores = StudentScore.objects.filter(
        student=student, assessment__subject=subject, assessment__section=section,
    ).select_related('assessment')
    if marks_filter is not None:
        scores = scores.filter(marks_filter)

    if not weights:
        avg = _average_pct(scores)
        return {'score': None if avg is None else round(avg, 1), 'provisional': False, 'details': []}

    if at_names is None:
        at_names = dict(AssessmentType.objects.filter(id__in=weights.keys()).values_list('id', 'name'))

    details, weighted_sum, weight_with_marks, missing = [], Decimal('0'), Decimal('0'), False
    for at_id, weight in weights.items():
        avg = _average_pct(scores.filter(assessment__assessment_type_id=at_id))
        if avg is None:
            missing = True
        else:
            weighted_sum += avg * weight
            weight_with_marks += weight
        details.append({
            'type': at_names.get(at_id, ''),
            'weight': weight,
            'avg_pct': None if avg is None else round(avg, 1),
            'weighted_score': None if avg is None else round(avg * weight / HUNDRED, 1),
        })

    if not weight_with_marks:
        return {'score': None, 'provisional': False, 'details': details}
    # Scale to the weights that have marks, so a missing exam isn't counted as zero.
    return {
        'score': round(weighted_sum / weight_with_marks, 1),
        'provisional': missing,
        'details': details,
    }


def _year_weights(subject, section):
    try:
        w = SubjectWeighting.objects.get(section=section, subject=subject, academic_year=section.academic_year)
    except SubjectWeighting.DoesNotExist:
        return None, None
    comps = list(w.components.select_related('assessment_type'))
    return ({c.assessment_type_id: c.weight_percentage for c in comps},
            {c.assessment_type_id: c.assessment_type.name for c in comps})


# ─── BACKWARDS-COMPATIBLE HELPERS ─────────────────────────────────────────────

def calculate_student_grade(student, subject, section, marks_filter=None):
    """Full-year weighted score (Decimal), or None if the student has no marks in the subject."""
    weights, names = _year_weights(subject, section)
    return subject_result(student, subject, section, weights, names, marks_filter)['score']


def get_grade_details(student, subject, section, marks_filter=None):
    """Per-assessment-type breakdown for the full-year report card."""
    weights, names = _year_weights(subject, section)
    if not weights:
        return []
    return subject_result(student, subject, section, weights, names, marks_filter)['details']


def period_marks_filter(period):
    return Q(assessment__date_conducted__gte=period.start_date,
             assessment__date_conducted__lte=period.end_date)


def calculate_period_grade(student, subject, section, period, period_weights, at_name_map=None):
    """Weighted score for one report period. Returns (score or None, details)."""
    r = subject_result(student, subject, section, period_weights, at_name_map, period_marks_filter(period))
    return r['score'], r['details']


# ─── REPORT CARD ASSEMBLY ─────────────────────────────────────────────────────

def _period_config(section):
    config = AcademicPeriodConfig.objects.filter(academic_year=section.academic_year).first()
    if not config:
        config = AcademicPeriodConfig.objects.filter(academic_year__icontains=section.academic_year).first()
    return config


def visible_marks_filter(section, viewer):
    """
    Q limiting which marks `viewer` may see, or None for no limit.

    Students and parents only see marks dated inside published report periods
    when the section's academic year has report periods set up.
    """
    if viewer is None or viewer.role not in RESTRICTED_VIEWERS:
        return None
    config = _period_config(section)
    if not config:
        return None
    q = Q(pk__in=[])
    for p in config.periods.filter(is_published=True):
        q |= period_marks_filter(p)
    return q


def report_subjects(profile, section, assessment_filter=None):
    """Subjects assessed in the section; limited to the student's enrolled subjects if any are set."""
    subjects = Subject.objects.filter(assessmentrecord__section=section)
    if assessment_filter is not None:
        subjects = subjects.filter(assessment_filter)
    enrolled = list(profile.subjects.values_list('id', flat=True)) if profile else []
    if enrolled:
        subjects = subjects.filter(id__in=enrolled)
    return subjects.distinct().order_by('name')


def summarise(grades, grade_settings):
    """Overall average across subjects that have marks."""
    scored = [g['score'] for g in grades if g['score'] is not None]
    overall = round(sum(scored) / len(scored), 1) if scored else None
    return {
        'overall_avg': overall,
        'overall_letter': get_letter_grade(overall, grade_settings),
        'provisional': any(g['provisional'] for g in grades),
    }


def year_report(student, viewer=None, with_details=False):
    """
    Full-year grades for a student, as `viewer` is allowed to see them.

    Returns {'profile', 'section', 'grades', 'overall_avg', 'overall_letter',
             'provisional', 'marks_limited', 'grade_settings'}.
    Each grade: {'subject', 'score', 'provisional', 'letter', 'remark', 'grade_point', 'details'}.
    """
    profile = StudentProfile.objects.filter(user=student).select_related('section').first()
    section = profile.section if profile else None
    grade_settings = list(GradeSetting.objects.all())
    grades = []
    marks_filter = None

    if section:
        marks_filter = visible_marks_filter(section, viewer)
        for subj in report_subjects(profile, section):
            weights, names = _year_weights(subj, section)
            r = subject_result(student, subj, section, weights, names, marks_filter)
            letter = get_letter_grade(r['score'], grade_settings)
            grades.append({
                'subject': subj,
                'score': r['score'],
                'provisional': r['provisional'],
                'letter': letter['letter'],
                'remark': letter['remark'],
                'grade_point': letter['grade_point'],
                'details': r['details'] if with_details else [],
            })

    return {
        'profile': profile,
        'section': section,
        'grades': grades,
        'marks_limited': marks_filter is not None,
        'grade_settings': grade_settings,
        **summarise(grades, grade_settings),
    }
