"""
exams/services.py — Centralised business logic for exam grades and report cards.

All grade and report-card numbers come from here, so every page (report cards,
bulk printing, dashboards, profiles) shows the same result. Views should import
from here — never duplicate this logic.

Rules:
- A subject's grade only counts the assessment types that have marks so far.
  Their weights are scaled up to 100%, and the grade is flagged `provisional`
  until every weighted type has marks.
- A subject with no marks at all has score None ("No marks yet") and is left
  out of the overall average, GPA and class statistics.
- Letter grades are chosen by minimum score only (highest band whose minimum is
  met), so there are no gaps between bands.
- Students and parents see every mark as soon as it is entered (no publishing
  step for the full-year report card or dashboards).
- If a student has enrolled subjects, only those appear on their report.

Report cards are built a whole section at a time: one query loads the marks,
and grades, class statistics, attendance, comments and remarks are assembled
in Python. This keeps single cards and bulk printing fast.
"""
import logging
import re
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Q

from academics.models import Subject
from attendance.models import Attendance
from students.models import StudentProfile
from .models import (
    AcademicPeriodConfig, AssessmentType, GradeSetting, ReportRemark, StudentScore,
    SubjectComment, SubjectWeighting,
)

logger = logging.getLogger(__name__)

HUNDRED = Decimal('100')
NO_GRADE = {'letter': '-', 'remark': '', 'grade_point': Decimal('0')}


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

def _pct(obtained, total):
    return (obtained / total) * HUNDRED if total and total > 0 else None


def combine(pcts_by_type, weights=None, at_names=None, na_types=frozenset()):
    """
    Combine a student's percentages in one subject into a result.

    pcts_by_type: {assessment_type_id: [percentage, ...]}
    weights:      {assessment_type_id: weight_percentage}; None/empty = simple average.
    na_types:     assessment types marked "not applicable" for this student; a type
                  with only N/A entries is left out without making the grade provisional.

    Returns {'score': Decimal|None, 'provisional': bool, 'not_applicable': bool, 'details': [...]}.
    Each detail is {'type', 'weight', 'avg_pct' (None if no marks), 'weighted_score', 'not_applicable'}.
    `not_applicable` on the result means everything that would count was marked N/A.
    """
    if not weights:
        all_pcts = [p for pcts in pcts_by_type.values() for p in pcts]
        avg = sum(all_pcts) / len(all_pcts) if all_pcts else None
        return {'score': None if avg is None else round(avg, 1), 'provisional': False,
                'not_applicable': avg is None and bool(na_types), 'details': []}

    at_names = at_names or {}
    details, weighted_sum, weight_with_marks, missing = [], Decimal('0'), Decimal('0'), False
    all_na = True
    for at_id, weight in weights.items():
        pcts = pcts_by_type.get(at_id) or []
        avg = sum(pcts) / len(pcts) if pcts else None
        type_na = avg is None and at_id in na_types
        if avg is None:
            if not type_na:
                missing = True
                all_na = False
        else:
            all_na = False
            weighted_sum += avg * weight
            weight_with_marks += weight
        details.append({
            'type': at_names.get(at_id, ''),
            'weight': weight,
            'avg_pct': None if avg is None else round(avg, 1),
            'weighted_score': None if avg is None else round(avg * weight / HUNDRED, 1),
            'not_applicable': type_na,
        })

    if not weight_with_marks:
        return {'score': None, 'provisional': False, 'not_applicable': all_na and bool(na_types),
                'details': details}
    # Scale to the weights that have marks, so a missing exam isn't counted as zero.
    return {'score': round(weighted_sum / weight_with_marks, 1), 'provisional': missing,
            'not_applicable': False, 'details': details}


def _score_rows(qs):
    return qs.values_list('student_id', 'assessment__subject_id', 'assessment__assessment_type_id',
                          'marks_obtained', 'assessment__total_marks', 'not_applicable')


def subject_result(student, subject, section, weights=None, at_names=None, marks_filter=None):
    """Weighted result for one student in one subject (see `combine`)."""
    scores = StudentScore.objects.filter(student=student, assessment__subject=subject, assessment__section=section)
    if marks_filter is not None:
        scores = scores.filter(marks_filter)
    pcts, na_types = defaultdict(list), set()
    for _, _, at_id, obtained, total, na in _score_rows(scores):
        if na:
            na_types.add(at_id)
            continue
        p = _pct(obtained, total)
        if p is not None:
            pcts[at_id].append(p)
    if weights and at_names is None:
        at_names = dict(AssessmentType.objects.filter(id__in=weights.keys()).values_list('id', 'name'))
    return combine(pcts, weights, at_names, na_types)


# ─── WEIGHTS ──────────────────────────────────────────────────────────────────

def year_weights(section):
    """{subject_id: (weights, names)} from each subject's SubjectWeighting for the section's year."""
    out = {}
    for w in SubjectWeighting.objects.filter(section=section, academic_year=section.academic_year) \
                                     .prefetch_related('components__assessment_type'):
        comps = list(w.components.all())
        out[w.subject_id] = ({c.assessment_type_id: c.weight_percentage for c in comps},
                             {c.assessment_type_id: c.assessment_type.name for c in comps})
    return out


def period_weights(period):
    """{subject_id or None: (weights, names)} — None holds the period's default weights."""
    out, names = {}, {}
    for pw in period.weightings.select_related('assessment_type'):
        out.setdefault(pw.subject_id, {})[pw.assessment_type_id] = pw.weight_percentage
        names[pw.assessment_type_id] = pw.assessment_type.name
    return {k: (v, names) for k, v in out.items()}


def _year_weights(subject, section):
    return year_weights(section).get(subject.id, (None, None))


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


def calculate_period_grade(student, subject, section, period, period_weights_map, at_name_map=None):
    """Weighted score for one report period. Returns (score or None, details)."""
    r = subject_result(student, subject, section, period_weights_map, at_name_map, period_marks_filter(period))
    return r['score'], r['details']


# ─── VISIBILITY & SUBJECTS ────────────────────────────────────────────────────

def period_config(section):
    config = AcademicPeriodConfig.objects.filter(academic_year=section.academic_year).first()
    if not config:
        config = AcademicPeriodConfig.objects.filter(academic_year__icontains=section.academic_year).first()
    return config


def visible_marks_filter(section, viewer):
    """
    Q limiting which marks `viewer` may see, or None for no limit.

    Everyone sees every mark as soon as it is entered, so this returns None.
    Kept as the single place to add a publishing rule again if one is wanted.
    """
    return None


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
    """Overall average and GPA across subjects that have marks."""
    scored = [g for g in grades if g['score'] is not None]
    overall = round(sum(g['score'] for g in scored) / len(scored), 1) if scored else None
    uses_gpa = any(gs.grade_point for gs in grade_settings)
    gpa = None
    if uses_gpa and scored:
        gpa = round(sum(Decimal(g['grade_point']) for g in scored) / len(scored), 2)
    return {
        'overall_avg': overall,
        'overall_letter': get_letter_grade(overall, grade_settings),
        'gpa': gpa,
        'provisional': any(g['provisional'] for g in grades),
    }


def _natural_key(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', text or '')]


def section_profiles(section):
    """Active students in a section, ordered by roll number then name."""
    profiles = list(
        StudentProfile.objects.filter(section=section, user__is_active=True, user__is_deleted=False)
        .select_related('user').prefetch_related('subjects')
    )
    profiles.sort(key=lambda p: (p.roll_number == '' or p.roll_number is None, _natural_key(p.roll_number),
                                 (p.user.get_full_name() or p.user.username).lower()))
    return profiles


# ─── REPORT CARDS ─────────────────────────────────────────────────────────────

def build_report_cards(section, profiles, viewer=None, period=None):
    """
    Report cards for `profiles` (StudentProfile list, all in `section`).

    period=None builds the full-year card; otherwise the card for that report
    period. Class averages and highest marks are computed over every active
    student in the section, using the marks `viewer` is allowed to see.
    """
    grade_settings = list(GradeSetting.objects.all())
    year = section.academic_year

    if period is not None:
        marks_filter = period_marks_filter(period)
        marks_limited = False
        weights_map = period_weights(period)
        default_weights = weights_map.get(None, (None, None))
        weights_for = lambda subject_id: weights_map.get(subject_id, default_weights)  # noqa: E731
        assessed = Subject.objects.filter(
            assessmentrecord__section=section,
            assessmentrecord__date_conducted__gte=period.start_date,
            assessmentrecord__date_conducted__lte=period.end_date,
        )
    else:
        marks_filter = visible_marks_filter(section, viewer)
        marks_limited = marks_filter is not None
        weights_map = year_weights(section)
        weights_for = lambda subject_id: weights_map.get(subject_id, (None, None))  # noqa: E731
        assessed = Subject.objects.filter(assessmentrecord__section=section)
    assessed = list(assessed.distinct().order_by('name'))

    # All visible marks for the whole section in one query.
    everyone = section_profiles(section)
    student_ids = {p.user_id for p in everyone} | {p.user_id for p in profiles}
    scores = StudentScore.objects.filter(assessment__section=section, student_id__in=student_ids)
    if marks_filter is not None:
        scores = scores.filter(marks_filter)
    pcts = defaultdict(lambda: defaultdict(list))  # (student, subject) -> {type: [pct]}
    na = defaultdict(set)                           # (student, subject) -> {types marked N/A}
    for stu, subj, at_id, obtained, total, is_na in _score_rows(scores):
        if is_na:
            na[(stu, subj)].add(at_id)
            continue
        p = _pct(obtained, total)
        if p is not None:
            pcts[(stu, subj)][at_id].append(p)

    results = {}
    for stu in student_ids:
        for subj in assessed:
            w, n = weights_for(subj.id)
            results[(stu, subj.id)] = combine(pcts.get((stu, subj.id), {}), w, n, na.get((stu, subj.id), set()))

    # Class statistics per subject, over students who have marks in it
    stats = {}
    for subj in assessed:
        vals = [results[(p.user_id, subj.id)]['score'] for p in everyone
                if results[(p.user_id, subj.id)]['score'] is not None]
        stats[subj.id] = {
            'class_avg': round(sum(vals) / len(vals), 1) if vals else None,
            'class_high': max(vals) if vals else None,
            'class_count': len(vals),
        }

    ids = [p.user_id for p in profiles]

    # Teacher comments per subject
    comments = defaultdict(list)
    cq = SubjectComment.objects.filter(student_id__in=ids, section=section, academic_year=year)
    if period is not None:
        cq = cq.filter(period=period)
    else:
        cq = cq.filter(period__isnull=False)
        if marks_limited:
            cq = cq.filter(period__is_published=True)
    for c in cq.select_related('period').order_by('period__sequence'):
        comments[(c.student_id, c.subject_id)].append({'label': c.period.label, 'comment': c.comment})

    # Overall remarks
    remarks = {r.student_id: r for r in ReportRemark.objects.filter(
        student_id__in=ids, academic_year=year, period=period)}

    # Attendance in this section (and period, if any)
    aq = Attendance.objects.filter(user_id__in=ids, section=section) \
                           .exclude(status=Attendance.Status.NOT_APPLICABLE)
    if period is not None:
        aq = aq.filter(date__gte=period.start_date, date__lte=period.end_date)
    att = defaultdict(lambda: defaultdict(int))
    for uid, status, n in aq.values_list('user_id', 'status').annotate(n=Count('id')):
        att[uid][status] = n

    cards = []
    for profile in profiles:
        enrolled = {s.id for s in profile.subjects.all()}
        subjects = [s for s in assessed if not enrolled or s.id in enrolled]
        grades = []
        for subj in subjects:
            r = results[(profile.user_id, subj.id)]
            letter = get_letter_grade(r['score'], grade_settings)
            subj_comments = comments.get((profile.user_id, subj.id), [])
            grades.append({
                'subject': subj,
                'score': r['score'],
                'provisional': r['provisional'],
                'not_applicable': r['not_applicable'],
                'letter': letter['letter'],
                'remark': letter['remark'],
                'grade_point': letter['grade_point'],
                'details': r['details'],
                'comments': subj_comments,
                'comment': subj_comments[0]['comment'] if period is not None and subj_comments else '',
                **stats[subj.id],
            })

        a = att.get(profile.user_id, {})
        present, late, absent = (a.get(Attendance.Status.PRESENT, 0), a.get(Attendance.Status.LATE, 0),
                                 a.get(Attendance.Status.ABSENT, 0))
        total = present + late + absent
        remark = remarks.get(profile.user_id)
        cards.append({
            'student': profile.user,
            'profile': profile,
            'section': section,
            'period': period,
            'grades': grades,
            'grade_settings': grade_settings,
            'marks_limited': marks_limited,
            'attendance': {
                'present': present, 'late': late, 'absent': absent, 'total': total,
                'pct': round((present + late) * 100 / total) if total else None,
            },
            'remarks': {
                'class_teacher': remark.class_teacher_remark if remark else '',
                'principal': remark.principal_remark if remark else '',
            },
            **summarise(grades, grade_settings),
        })
    return cards


def report_card(student, viewer=None, period=None):
    """One student's report card (see build_report_cards); None if they have no section."""
    profile = StudentProfile.objects.filter(user=student).select_related('section') \
                                    .prefetch_related('subjects').first()
    if not profile or not profile.section:
        return None
    return build_report_cards(profile.section, [profile], viewer=viewer, period=period)[0]


def year_report(student, viewer=None, with_details=False):
    """
    Full-year grades for a student, as `viewer` is allowed to see them.
    Kept for dashboards and profiles; returns the report-card dict, or an
    empty one (no grades) if the student has no section.
    """
    card = report_card(student, viewer=viewer)
    if card is None:
        grade_settings = list(GradeSetting.objects.all())
        profile = StudentProfile.objects.filter(user=student).first()
        return {'profile': profile, 'section': None, 'grades': [], 'marks_limited': False,
                'grade_settings': grade_settings, **summarise([], grade_settings)}
    if not with_details:
        for g in card['grades']:
            g['details'] = []
    return card
