"""
Small JSON API used by the Android app to show phone notifications.

The app calls /api/app/notifications/?since=<cursor> every ~15 minutes with the
user's login cookie. The first call (no `since`) only returns a cursor, so a
newly installed app doesn't notify about old results.
"""
import datetime
from collections import defaultdict

from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET

from accounts.models import User
from students.models import ParentProfile
from .ct_report import detect_ct_type
from .models import StudentScore

MAX_ITEMS_PER_STUDENT = 3


def _fmt(n):
    return f"{n:.2f}".rstrip('0').rstrip('.')


@require_GET
def app_notifications(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'not_logged_in'}, status=401)

    now = timezone.now()
    cursor = now.isoformat()
    # A '+' in the time-zone offset may arrive as a space if the URL wasn't encoded.
    since = parse_datetime((request.GET.get('since', '') or '').strip().replace(' ', '+'))
    if since is None:
        return JsonResponse({'cursor': cursor, 'items': []})
    if timezone.is_naive(since):
        since = timezone.make_aware(since, datetime.timezone.utc)

    user = request.user
    if user.role == User.Role.STUDENT:
        students, is_parent = [user], False
    elif user.role == User.Role.PARENT:
        profile = ParentProfile.objects.filter(user=user).first()
        students, is_parent = (list(profile.children.all()) if profile else []), True
    else:
        return JsonResponse({'cursor': cursor, 'items': []})

    ct_type = detect_ct_type()
    if not students or not ct_type:
        return JsonResponse({'cursor': cursor, 'items': []})

    scores = (StudentScore.objects
              .filter(student__in=students, assessment__assessment_type=ct_type, not_applicable=False,
                      updated_at__gt=since, updated_at__lte=now)
              .select_related('assessment__subject', 'student')
              .order_by('updated_at')[:200])
    by_student = defaultdict(list)
    for s in scores:
        by_student[s.student].append(s)

    items = []
    for student, results in by_student.items():
        latest = results[-1].assessment.date_conducted
        query = f"?view=month&month={latest:%Y-%m}"
        url = (reverse('student_ct_progress', args=[student.id]) if is_parent else reverse('my_ct_progress')) + query
        who = f"{student.first_name or student.username}: " if is_parent else ""
        if len(results) > MAX_ITEMS_PER_STUDENT:
            subjects = sorted({r.assessment.subject.name for r in results})
            items.append({
                'id': 900000 + student.id,
                'title': f"{who}{len(results)} new class test results",
                'body': ", ".join(subjects),
                'url': url,
            })
            continue
        for r in results:
            a = r.assessment
            pct = round(r.marks_obtained * 100 / a.total_marks) if a.total_marks else None
            items.append({
                'id': r.id,
                'title': f"{who}New class test result",
                'body': f"{a.subject.name} {a.title}: {_fmt(r.marks_obtained)}/{_fmt(a.total_marks)}"
                        + (f" ({pct}%)" if pct is not None else ""),
                'url': url,
            })
    return JsonResponse({'cursor': cursor, 'items': items})
