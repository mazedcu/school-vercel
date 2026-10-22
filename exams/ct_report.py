"""
CT (class test) progress report: each student's class-test results per subject
over a date range, plus class statistics.

Rules:
- A missing mark (absent or not entered) is shown as such and left out of the
  student's totals; it never counts as zero.
- A class test with no marks entered for anyone is left out entirely and
  listed separately as "not marked yet".
- Only current (active) students in the section appear, ordered by roll number.
- Students only see subjects they are enrolled in, when enrolment is recorded.
"""
import datetime
import re
from collections import defaultdict
from decimal import Decimal

from .models import AssessmentRecord, AssessmentType, GradeSetting, StudentScore
from .services import get_letter_grade, section_profiles

HUNDRED = Decimal('100')

# Used only when no report periods are configured for the section's year.
FALLBACK_TERMS = {
    1: ('First Term', 7),   # July–December
    2: ('Second Term', 1),  # January–June
}


def detect_ct_type(types=None):
    """The assessment type that holds class tests, matched on whole words (not 'Practical')."""
    types = list(AssessmentType.objects.all() if types is None else types)
    by_name = {t.name.strip().lower(): t for t in types}
    for name in ('class test', 'class tests', 'ct', 'cts'):
        if name in by_name:
            return by_name[name]
    for t in types:
        if 'class test' in t.name.lower() or re.search(r'\bct\b', t.name, re.I):
            return t
    return None


def month_end(year, month):
    nxt = datetime.date(year + (month == 12), month % 12 + 1, 1)
    return nxt - datetime.timedelta(days=1)


def fallback_range(month, year):
    """Old fixed terms: July–December and January–June, from the term start to the end of `month`."""
    term = 1 if month >= 7 else 2
    label, start_month = FALLBACK_TERMS[term]
    return label, datetime.date(year, start_month, 1), month_end(year, month)


def _pct(obtained, total):
    return round(obtained * HUNDRED / total, 1) if total else None


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def ct_progress(section, ct_type, start, end):
    """Build the CT progress data for `section` between `start` and `end` (inclusive)."""
    grade_settings = list(GradeSetting.objects.all())
    profiles = section_profiles(section)

    all_cts = list(
        AssessmentRecord.objects.filter(section=section, assessment_type=ct_type,
                                        date_conducted__gte=start, date_conducted__lte=end)
        .select_related('subject').order_by('subject__name', 'date_conducted', 'id')
    )
    scores = {
        (sid, aid): obtained
        for aid, sid, obtained in StudentScore.objects.filter(
            assessment__in=all_cts, student__in=[p.user_id for p in profiles]
        ).values_list('assessment_id', 'student_id', 'marks_obtained')
    }
    marked_ids = set(StudentScore.objects.filter(assessment__in=all_cts).values_list('assessment_id', flat=True))
    cts = [a for a in all_cts if a.id in marked_ids and a.total_marks > 0]
    unmarked = [a for a in all_cts if a.id not in marked_ids]

    subjects, cts_by_subject = [], defaultdict(list)
    for a in cts:
        if a.subject not in subjects:
            subjects.append(a.subject)
        cts_by_subject[a.subject.id].append(a)

    students = []
    for p in profiles:
        enrolled = {s.id for s in p.subjects.all()}
        rows = []
        for subj in subjects:
            if enrolled and subj.id not in enrolled:
                continue
            tests, obtained, maximum, missing = [], Decimal('0'), Decimal('0'), 0
            for a in cts_by_subject[subj.id]:
                mark = scores.get((p.user_id, a.id))
                tests.append({'ct': a, 'obtained': mark, 'total': a.total_marks})
                if mark is None:
                    missing += 1
                else:
                    obtained += mark
                    maximum += a.total_marks
            pct = _pct(obtained, maximum)
            letter = get_letter_grade(pct, grade_settings)
            rows.append({
                'subject': subj, 'tests': tests, 'obtained': obtained, 'maximum': maximum,
                'pct': pct, 'missing': missing, 'grade': letter['letter'], 'remark': letter['remark'],
            })
        overall = _mean(r['pct'] for r in rows)
        letter = get_letter_grade(overall, grade_settings)
        students.append({
            'student': p.user, 'profile': p, 'rows': rows,
            'by_subject': {r['subject'].id: r for r in rows},
            'cells': [next((r for r in rows if r['subject'].id == subj.id), None) for subj in subjects],
            'overall': overall, 'overall_grade': letter['letter'], 'overall_remark': letter['remark'],
            'missing': sum(r['missing'] for r in rows),
        })

    subject_stats = {}
    for subj in subjects:
        pcts = [s['by_subject'][subj.id]['pct'] for s in students if subj.id in s['by_subject']]
        pcts = [v for v in pcts if v is not None]
        subject_stats[subj.id] = {'avg': _mean(pcts), 'high': max(pcts) if pcts else None}
    ct_avgs = {}
    for a in cts:
        marks = [scores[(s['student'].id, a.id)] for s in students if (s['student'].id, a.id) in scores]
        ct_avgs[a.id] = round(sum(marks) / len(marks), 1) if marks else None

    for s in students:
        for r in s['rows']:
            r['class_avg'] = subject_stats[r['subject'].id]['avg']
            r['class_high'] = subject_stats[r['subject'].id]['high']
            for t in r['tests']:
                t['class_avg'] = ct_avgs.get(t['ct'].id)

    overalls = [s['overall'] for s in students]
    return {
        'students': students,
        'subjects': [{'subject': s, **subject_stats[s.id], 'tests': cts_by_subject[s.id]} for s in subjects],
        'unmarked': unmarked,
        'class_avg': _mean(overalls),
        'class_high': max((o for o in overalls if o is not None), default=None),
        'any_missing': any(s['missing'] for s in students),
        'grade_settings': grade_settings,
    }
