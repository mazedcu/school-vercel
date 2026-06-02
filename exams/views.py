import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from accounts.decorators import role_required
from django.contrib import messages
from django.db.models import Count, Q, Avg
from django.utils import timezone
from decimal import Decimal
import datetime

from accounts.models import User
from academics.models import ClassGroup, Section, Subject
from students.models import StudentProfile
from timetable.models import TimetableEntry
from timetable.pdf_utils import generate_section_timetable_pdf
from exams.models import (
    AssessmentType, AssessmentRecord, StudentScore, GradeSetting,
    SubjectComment, SubjectWeighting, WeightingComponent,
    AcademicPeriodConfig, ReportPeriod, PeriodWeighting
)
from exams.services import (
    calculate_student_grade, get_grade_details,
    get_letter_grade, calculate_period_grade
)

logger = logging.getLogger(__name__)



@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def report_settings(request):

    if request.method == 'POST':
        section_id = request.POST.get('section')
        subject_id = request.POST.get('subject')
        try:
            section = Section.objects.get(id=section_id)
            subject = Subject.objects.get(id=subject_id)
        except (Section.DoesNotExist, Subject.DoesNotExist):
            messages.error(request, "Invalid section or subject.")
            return redirect('report_settings')

        profile, created = SubjectWeighting.objects.get_or_create(
            section=section, subject=subject, academic_year=section.academic_year,
            defaults={'teacher': request.user}
        )
        # Clear old components
        profile.components.all().delete()

        total_weight = Decimal('0')
        assessment_types = AssessmentType.objects.all()
        for at in assessment_types:
            w = request.POST.get(f'weight_{at.id}', '0')
            try:
                w = Decimal(w)
            except Exception:
                w = Decimal('0')
            if w > 0:
                WeightingComponent.objects.create(weighting_profile=profile, assessment_type=at, weight_percentage=w)
                total_weight += w

        if total_weight != Decimal('100'):
            messages.warning(request, f"Weights saved but total is {total_weight}%, not 100%. Please adjust.")
        else:
            messages.success(request, f"Weights for {subject.name} in {section} saved successfully (100%).")
        return redirect('report_settings')

    sections = Section.objects.all()
    subjects = Subject.objects.all()
    assessment_types = AssessmentType.objects.all()
    existing = SubjectWeighting.objects.all().select_related('section', 'subject').prefetch_related('components__assessment_type')

    context = {
        'sections': sections,
        'subjects': subjects,
        'assessment_types': assessment_types,
        'existing_weightings': existing,
    }
    return render(request, 'dashboard/report_settings.html', context)

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def manage_assessments(request):

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        section_id = request.POST.get('section')
        subject_id = request.POST.get('subject')
        assessment_type_id = request.POST.get('assessment_type')
        total_marks_str = request.POST.get('total_marks', '100').strip()
        date_conducted = request.POST.get('date_conducted', timezone.now().date().isoformat())

        # ── Validate total_marks before touching the DB ────────────────────
        try:
            total_marks = Decimal(total_marks_str)
            if total_marks <= 0:
                raise ValueError("Total marks must be greater than zero.")
        except Exception:
            messages.error(request, f"Invalid total marks value: '{total_marks_str}'. Must be a positive number.")
            return redirect('manage_assessments')

        if not title:
            messages.error(request, "Assessment title is required.")
            return redirect('manage_assessments')

        try:
            section = Section.objects.get(id=section_id)
            subject = Subject.objects.get(id=subject_id)
            assessment_type = AssessmentType.objects.get(id=assessment_type_id)
            record = AssessmentRecord.objects.create(
                section=section, subject=subject, assessment_type=assessment_type,
                title=title, total_marks=total_marks, date_conducted=date_conducted
            )
            messages.success(request, f"Assessment '{title}' created. Now enter marks.")
            return redirect(reverse('enter_marks', args=[record.id]))
        except (Section.DoesNotExist, Subject.DoesNotExist, AssessmentType.DoesNotExist):
            messages.error(request, "Invalid section, subject, or assessment type selected.")
        except Exception as e:
            logger.error("Failed to create assessment: %s", e, exc_info=True)
            messages.error(request, "An unexpected error occurred. Please try again.")
        return redirect('manage_assessments')

    sections = Section.objects.all()
    subjects = Subject.objects.all()
    assessment_types = AssessmentType.objects.all()
    try:
        recent = list(
            AssessmentRecord.objects.all()
            .select_related('section__class_group', 'subject', 'assessment_type')
            .order_by('-date_conducted')[:20]
        )
    except Exception as e:
        logger.error("Failed to load recent assessments (possible corrupt decimal data): %s", e, exc_info=True)
        recent = []
        messages.warning(request, "Some assessment records could not be loaded due to data issues. Please check and fix any assessments with invalid marks.")

    context = {
        'sections': sections,
        'subjects': subjects,
        'assessment_types': assessment_types,
        'recent_assessments': recent,
    }
    return render(request, 'dashboard/manage_assessments.html', context)

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def delete_assessment(request, assessment_id):
    if request.method == 'POST':
        try:
            assessment = get_object_or_404(AssessmentRecord, pk=assessment_id)
            title = assessment.title
            assessment.delete()
            messages.success(request, f"Assessment '{title}' has been deleted successfully.")
        except Exception as e:
            # Fallback: if fetching fails due to corrupt decimal data, delete by pk directly
            deleted, _ = AssessmentRecord.objects.filter(pk=assessment_id).delete()
            if deleted:
                messages.success(request, "Assessment deleted successfully.")
            else:
                logger.error("Failed to delete assessment %s: %s", assessment_id, e, exc_info=True)
                messages.error(request, "Could not delete the assessment.")
    return redirect('manage_assessments')

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def enter_marks(request, assessment_id):

    try:
        assessment = get_object_or_404(AssessmentRecord, pk=assessment_id)
    except Exception as e:
        logger.error("Failed to load assessment %s (possible corrupt data): %s", assessment_id, e, exc_info=True)
        messages.error(request, "This assessment record could not be loaded due to data issues.")
        return redirect('manage_assessments')
    profiles = StudentProfile.objects.filter(section=assessment.section).select_related('user')

    if request.method == 'POST':
        saved = 0
        errors = []
        for p in profiles:
            marks = request.POST.get(f'marks_{p.user.id}', '').strip()
            if not marks:
                continue
            try:
                m = Decimal(marks)
                if m < 0:
                    raise ValueError("Marks cannot be negative.")
                if m > assessment.total_marks:
                    raise ValueError(f"Marks ({m}) exceed total ({assessment.total_marks}).")
                StudentScore.objects.update_or_create(
                    assessment=assessment, student=p.user,
                    defaults={'marks_obtained': m}
                )
                saved += 1
            except ValueError as e:
                errors.append(f"{p.user.get_full_name() or p.user.username}: {e}")
            except Exception as e:
                logger.warning("Could not save mark for student %s: %s", p.user_id, e)
                errors.append(f"{p.user.get_full_name() or p.user.username}: Could not save.")
        if errors:
            for err in errors:
                messages.warning(request, err)
        if saved:
            messages.success(request, f"Marks saved for '{assessment.title}' ({saved} student(s)).")
        return redirect(reverse('enter_marks', args=[assessment_id]))

    students_marks = []
    for p in profiles:
        existing = StudentScore.objects.filter(assessment=assessment, student=p.user).first()
        try:
            # Guard against any corrupt stored decimal values
            marks_val = existing.marks_obtained if existing else ''
            if marks_val != '':
                marks_val = Decimal(str(marks_val))  # validate — raises if corrupt
        except Exception:
            logger.error(
                "Corrupt marks_obtained for student %s in assessment %s — resetting display.",
                p.user_id, assessment_id
            )
            marks_val = ''
        students_marks.append({
            'user': p.user,
            'roll': p.roll_number,
            'marks': marks_val,
        })

    context = {
        'assessment': assessment,
        'students_marks': students_marks,
    }
    return render(request, 'dashboard/enter_marks.html', context)

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def view_reports(request):
    """Admin/Teacher view: list students and link to their report cards."""

    section_id = request.GET.get('section', '')
    sections = Section.objects.all()
    students = []

    if section_id:
        profiles = StudentProfile.objects.filter(section_id=section_id).select_related('user', 'section')
    else:
        profiles = StudentProfile.objects.all().select_related('user', 'section')

    for p in profiles:
        students.append({
            'user': p.user,
            'profile': p,
        })

    context = {
        'sections': sections,
        'students': students,
        'selected_section': section_id,
    }
    return render(request, 'dashboard/view_reports.html', context)

@login_required
def student_report(request, student_id=None):
    """View a student's complete report card with weighted grades, letter grades, and comments."""
    viewer = request.user
    printable = request.GET.get('print', '') == '1'

    if student_id:
        student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    elif viewer.role == User.Role.STUDENT:
        student = viewer
    else:
        return redirect('view_reports')

    if viewer.role == User.Role.STUDENT and viewer != student:
        return redirect('dashboard_router')

    profile = StudentProfile.objects.filter(user=student).first()
    section = profile.section if profile else None
    grade_settings = GradeSetting.objects.all()

    grades = []
    overall_total = Decimal('0')
    subject_count = 0
    if section:
        subjects = Subject.objects.filter(assessmentrecord__section=section).distinct()
        for subj in subjects:
            score = calculate_student_grade(student, subj, section)
            letter = get_letter_grade(score, grade_settings)
            # Fetch ALL period comments for this subject
            period_comments = SubjectComment.objects.filter(
                student=student, subject=subj, section=section, academic_year=section.academic_year,
                period__isnull=False
            ).select_related('period').order_by('period__sequence')
            comments_list = [{'label': pc.period.label, 'comment': pc.comment} for pc in period_comments]
            grades.append({
                'subject': subj,
                'score': score,
                'letter': letter['letter'],
                'remark': letter['remark'],
                'grade_point': letter['grade_point'],
                'details': get_grade_details(student, subj, section),
                'comments': comments_list,
            })
            overall_total += score
            subject_count += 1

    overall_avg = round(overall_total / subject_count, 1) if subject_count > 0 else 0
    overall_letter = get_letter_grade(overall_avg, grade_settings)

    context = {
        'student': student,
        'profile': profile,
        'section': section,
        'grades': grades,
        'overall_avg': overall_avg,
        'overall_letter': overall_letter,
        'grade_settings': grade_settings,
    }

    if printable:
        return render(request, 'dashboard/report_card_print.html', context)
    return render(request, 'dashboard/student_report.html', context)

@login_required
@role_required(User.Role.ADMIN)
def grade_settings_view(request):
    """Admin: configure letter grade boundaries."""

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            letter = request.POST.get('letter', '').strip()
            min_s = request.POST.get('min_score', '0')
            max_s = request.POST.get('max_score', '100')
            gp = request.POST.get('grade_point', '0')
            remark = request.POST.get('remark', '').strip()
            try:
                GradeSetting.objects.create(
                    letter=letter, min_score=Decimal(min_s), max_score=Decimal(max_s),
                    grade_point=Decimal(gp), remark=remark
                )
                messages.success(request, f"Grade '{letter}' added.")
            except Exception as e:
                logger.error("Failed to create GradeSetting: %s", e, exc_info=True)
                messages.error(request, str(e))

        elif action == 'delete':
            grade_id = request.POST.get('grade_id')
            GradeSetting.objects.filter(id=grade_id).delete()
            messages.success(request, "Grade deleted.")

        return redirect('grade_settings')

    existing = GradeSetting.objects.all()
    context = {'grades': existing}
    return render(request, 'dashboard/grade_settings.html', context)

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def subject_comments_view(request):
    """Teacher: add comments for students per subject per period."""

    sections = Section.objects.all()
    subjects = Subject.objects.all()
    selected_section = None
    selected_subject = None
    selected_period = None
    available_periods = []
    students_comments = []

    # Build period list when section is selected
    section_id_param = request.GET.get('section') or request.POST.get('section_id')
    if section_id_param:
        sec = Section.objects.filter(id=section_id_param).first()
        if sec:
            config = AcademicPeriodConfig.objects.filter(academic_year=sec.academic_year).first()
            if config:
                available_periods = list(config.periods.order_by('sequence'))

    if request.method == 'POST':
        section_id = request.POST.get('section_id')
        subject_id = request.POST.get('subject_id')
        period_id = request.POST.get('period_id')
        section = Section.objects.filter(id=section_id).first()
        subject = Subject.objects.filter(id=subject_id).first()
        period = ReportPeriod.objects.filter(id=period_id).first() if period_id else None
        if section and subject and period:
            profiles = StudentProfile.objects.filter(section=section).select_related('user')
            for p in profiles:
                comment_text = request.POST.get(f'comment_{p.user.id}', '').strip()
                if comment_text:
                    SubjectComment.objects.update_or_create(
                        student=p.user, subject=subject, section=section,
                        academic_year=section.academic_year, period=period,
                        defaults={'comment': comment_text, 'commented_by': request.user}
                    )
            messages.success(request, f"Comments saved for {subject.name} — {period.label} in {section}.")
        elif not period:
            messages.error(request, "Please select a reporting period.")
        url = reverse('subject_comments') + f'?section={section_id}&subject={subject_id}&period={period_id or ""}'
        return redirect(url)

    if request.GET.get('section') and request.GET.get('subject') and request.GET.get('period'):
        selected_section = Section.objects.filter(id=request.GET['section']).first()
        selected_subject = Subject.objects.filter(id=request.GET['subject']).first()
        selected_period = ReportPeriod.objects.filter(id=request.GET['period']).first()
        if selected_section and selected_subject and selected_period:
            profiles = StudentProfile.objects.filter(section=selected_section).select_related('user')
            for p in profiles:
                existing = SubjectComment.objects.filter(
                    student=p.user, subject=selected_subject, section=selected_section,
                    academic_year=selected_section.academic_year, period=selected_period
                ).first()
                students_comments.append({
                    'user': p.user,
                    'roll': p.roll_number,
                    'comment': existing.comment if existing else '',
                })

    # Build JSON of all periods grouped by academic year for client-side JS
    import json
    all_configs = AcademicPeriodConfig.objects.prefetch_related('periods').all()
    periods_by_year = {}
    for cfg in all_configs:
        periods_by_year[cfg.academic_year] = [
            {'id': p.id, 'label': p.label}
            for p in cfg.periods.order_by('sequence')
        ]

    context = {
        'sections': sections,
        'subjects': subjects,
        'selected_section': selected_section,
        'selected_subject': selected_subject,
        'selected_period': selected_period,
        'available_periods': available_periods,
        'students_comments': students_comments,
        'periods_json': json.dumps(periods_by_year),
    }
    return render(request, 'dashboard/subject_comments.html', context)

# Grade helpers are now in exams/services.py — imported at the top of this file.
# Legacy aliases kept temporarily to avoid breaking any external references.
_calculate_student_grade = calculate_student_grade
_get_grade_details = get_grade_details
_get_letter_grade = get_letter_grade


# ─── CT PROGRESS REPORT ──────────────────────────────────────────────────────

TERM_MONTHS = {
    1: list(range(7, 13)),   # First Term: July(7) to December(12)
    2: list(range(1, 7)),    # Second Term: January(1) to June(6)
}
MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]


@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def ct_progress_report(request):
    """Selection page: pick section, month, and year to generate CT progress report."""
    sections = Section.objects.select_related('class_group').all()
    now = timezone.now()

    # Determine current term
    current_month = now.month
    if current_month >= 7:
        current_term = 1
        current_year = now.year
    else:
        current_term = 2
        current_year = now.year

    # Build month options based on term
    month_options = []
    for term_num, months in TERM_MONTHS.items():
        for m in months:
            month_options.append({
                'value': m,
                'label': MONTH_NAMES[m],
                'term': term_num,
                'term_label': 'First Term' if term_num == 1 else 'Second Term',
            })

    context = {
        'sections': sections,
        'month_options': month_options,
        'current_month': current_month,
        'current_year': current_year,
    }
    return render(request, 'dashboard/ct_progress_select.html', context)


@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def ct_progress_report_print(request):
    """Generate and display print-ready CT progress report for a section."""
    section_id = request.GET.get('section')
    report_month = int(request.GET.get('month', 0))
    report_year = int(request.GET.get('year', timezone.now().year))

    if not section_id or not report_month:
        messages.error(request, "Please select a section and month.")
        return redirect('ct_progress_report')

    section = get_object_or_404(Section.objects.select_related('class_group'), id=section_id)

    # Determine term and date range
    if report_month >= 7:
        term = 1
        term_label = 'First Term'
        term_start = datetime.date(report_year, 7, 1)
        term_end = datetime.date(report_year, report_month, 28)  # Will be adjusted
    else:
        term = 2
        term_label = 'Second Term'
        term_start = datetime.date(report_year, 1, 1)
        term_end = datetime.date(report_year, report_month, 28)

    # Adjust term_end to last day of the selected month
    if report_month == 12:
        term_end = datetime.date(report_year, 12, 31)
    else:
        next_month = report_month + 1
        next_year = report_year
        if next_month > 12:
            next_month = 1
            next_year += 1
        term_end = datetime.date(next_year, next_month, 1) - datetime.timedelta(days=1)

    report_month_name = MONTH_NAMES[report_month]

    # Find the CT assessment type
    ct_type = AssessmentType.objects.filter(name__icontains='class test').first()
    if not ct_type:
        ct_type = AssessmentType.objects.filter(name__icontains='CT').first()
    if not ct_type:
        messages.error(request, "No 'Class Test' assessment type found. Please create one first.")
        return redirect('ct_progress_report')

    # Get all students in this section
    profiles = StudentProfile.objects.filter(section=section).select_related('user').order_by('roll_number', 'user__first_name')

    # Get all subjects that have CT assessments in this section within the date range
    ct_assessments = AssessmentRecord.objects.filter(
        section=section,
        assessment_type=ct_type,
        date_conducted__gte=term_start,
        date_conducted__lte=term_end,
    ).select_related('subject').order_by('subject__name', 'date_conducted')

    # Get unique subjects
    subjects = list(dict.fromkeys([a.subject for a in ct_assessments]))

    # Build assessment detail per subject
    subject_assessments = {}
    for subj in subjects:
        subj_cts = [a for a in ct_assessments if a.subject == subj]
        subject_assessments[subj.id] = subj_cts

    # Build student data
    grade_settings = GradeSetting.objects.all()

    # Pre-fetch ALL scores for these assessments in one query (fixes N+1)
    all_ct_ids = [a.id for cts in subject_assessments.values() for a in cts]
    all_student_ids = [p.user_id for p in profiles]
    all_scores_qs = StudentScore.objects.filter(
        assessment_id__in=all_ct_ids,
        student_id__in=all_student_ids,
    ).select_related('assessment')
    score_map = {}  # {(assessment_id, student_id): StudentScore}
    for s in all_scores_qs:
        score_map[(s.assessment_id, s.student_id)] = s

    students_data = []
    for profile in profiles:
        student = profile.user
        subject_scores = []
        total_pct = Decimal('0')
        subject_count = 0

        for subj in subjects:
            subj_cts = subject_assessments.get(subj.id, [])
            ct_details = []
            total_obtained = Decimal('0')
            total_max = Decimal('0')

            for ct in subj_cts:
                score = score_map.get((ct.id, student.id))
                obtained = score.marks_obtained if score else Decimal('0')
                ct_details.append({
                    'title': ct.title,
                    'date': ct.date_conducted,
                    'obtained': obtained,
                    'total': ct.total_marks,
                })
                total_obtained += obtained
                total_max += ct.total_marks

            if total_max > 0:
                pct = round((total_obtained / total_max) * 100, 1)
            else:
                pct = Decimal('0')

            letter = get_letter_grade(pct, grade_settings)
            subject_scores.append({
                'subject': subj,
                'details': ct_details,
                'total_obtained': total_obtained,
                'total_max': total_max,
                'percentage': pct,
                'grade': letter['letter'],
                'remark': letter['remark'],
            })
            total_pct += pct
            subject_count += 1

        overall_pct = round(total_pct / subject_count, 1) if subject_count > 0 else Decimal('0')
        overall_letter = get_letter_grade(overall_pct, grade_settings)

        students_data.append({
            'student': student,
            'profile': profile,
            'subjects': subject_scores,
            'overall_pct': overall_pct,
            'overall_grade': overall_letter['letter'],
            'overall_remark': overall_letter['remark'],
        })

    # Summary for the class
    class_avg = Decimal('0')
    if students_data:
        class_avg = round(sum(s['overall_pct'] for s in students_data) / len(students_data), 1)

    context = {
        'section': section,
        'term_label': term_label,
        'report_month_name': report_month_name,
        'report_year': report_year,
        'term_start': term_start,
        'term_end': term_end,
        'subjects': subjects,
        'students_data': students_data,
        'class_avg': class_avg,
        'ct_type': ct_type,
        'grade_settings': grade_settings,
    }
    return render(request, 'dashboard/ct_progress_print.html', context)


# ─── PERIOD-BASED REPORTING ──────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def period_setup(request):
    """Admin: configure reporting mode, period date ranges, and weights."""
    assessment_types = AssessmentType.objects.all()
    configs = AcademicPeriodConfig.objects.prefetch_related(
        'periods__weightings__assessment_type'
    ).all()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_config':
            academic_year = request.POST.get('academic_year', '').strip()
            mode = request.POST.get('mode')
            if not academic_year or not mode:
                messages.error(request, "Please fill in all fields.")
                return redirect('period_setup')

            if AcademicPeriodConfig.objects.filter(academic_year=academic_year).exists():
                messages.error(request, f"Configuration for {academic_year} already exists. Delete it first to recreate.")
                return redirect('period_setup')

            config = AcademicPeriodConfig.objects.create(
                academic_year=academic_year, mode=mode, created_by=request.user
            )

            if mode == AcademicPeriodConfig.Mode.QUARTERLY:
                period_count = 4
                default_labels = ['1st Quarter', '2nd Quarter', '3rd Quarter', '4th Quarter']
            else:
                period_count = 2
                default_labels = ['Mid-Term', 'Final-Term']

            for i in range(period_count):
                start_date = request.POST.get(f'start_date_{i+1}', '')
                end_date = request.POST.get(f'end_date_{i+1}', '')
                label = request.POST.get(f'label_{i+1}', default_labels[i]).strip() or default_labels[i]

                if not start_date or not end_date:
                    messages.error(request, "Please provide dates for all periods.")
                    config.delete()
                    return redirect('period_setup')

                ReportPeriod.objects.create(
                    config=config,
                    label=label,
                    sequence=i + 1,
                    start_date=start_date,
                    end_date=end_date,
                )

            messages.success(request, f"Reporting periods for {academic_year} created successfully!")

        elif action == 'save_weights':
            period_id = request.POST.get('period_id')
            period = get_object_or_404(ReportPeriod, id=period_id)
            period.weightings.filter(subject__isnull=True).delete()

            total_weight = Decimal('0')
            for at in assessment_types:
                w = request.POST.get(f'weight_{period_id}_{at.id}', '0')
                try:
                    w = Decimal(w)
                except Exception:
                    w = Decimal('0')
                if w > 0:
                    PeriodWeighting.objects.create(
                        period=period, assessment_type=at, weight_percentage=w
                    )
                    total_weight += w

            if total_weight != Decimal('100'):
                messages.warning(request, f"Default weights for '{period.label}' saved but total is {total_weight}%, not 100%.")
            else:
                messages.success(request, f"Default weights for '{period.label}' saved (100%). ✅")

        elif action == 'save_subject_weights':
            period_id = request.POST.get('period_id')
            subject_id = request.POST.get('subject_id')
            period = get_object_or_404(ReportPeriod, id=period_id)
            subject = get_object_or_404(Subject, id=subject_id)
            period.weightings.filter(subject=subject).delete()

            total_weight = Decimal('0')
            for at in assessment_types:
                w = request.POST.get(f'sw_{period_id}_0_{at.id}', '0')
                try:
                    w = Decimal(w)
                except Exception:
                    w = Decimal('0')
                if w > 0:
                    PeriodWeighting.objects.create(
                        period=period, assessment_type=at, subject=subject, weight_percentage=w
                    )
                    total_weight += w

            if total_weight == Decimal('0'):
                messages.success(request, f"Subject override for '{subject.name}' in '{period.label}' removed (using defaults).")
            elif total_weight != Decimal('100'):
                messages.warning(request, f"Weights for '{subject.name}' in '{period.label}' saved but total is {total_weight}%, not 100%.")
            else:
                messages.success(request, f"Weights for '{subject.name}' in '{period.label}' saved (100%). ✅")

        elif action == 'toggle_publish':
            period_id = request.POST.get('period_id')
            period = get_object_or_404(ReportPeriod, id=period_id)
            period.is_published = not period.is_published
            period.save()
            status = 'published' if period.is_published else 'unpublished'
            messages.success(request, f"'{period.label}' is now {status}.")

        elif action == 'delete_config':
            config_id = request.POST.get('config_id')
            AcademicPeriodConfig.objects.filter(id=config_id).delete()
            messages.success(request, "Configuration deleted.")

        return redirect('period_setup')

    subjects = Subject.objects.all()
    context = {
        'configs': configs,
        'assessment_types': assessment_types,
        'modes': AcademicPeriodConfig.Mode.choices,
        'subjects': subjects,
    }
    return render(request, 'dashboard/period_setup.html', context)


@login_required
def period_report_select(request, student_id=None):
    """Show available published periods for report generation."""
    viewer = request.user

    if student_id:
        student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    elif viewer.role == User.Role.STUDENT:
        student = viewer
    else:
        return redirect('view_reports')

    if viewer.role == User.Role.STUDENT and viewer != student:
        return redirect('dashboard_router')

    profile = StudentProfile.objects.filter(user=student).first()
    section = profile.section if profile else None

    configs = []
    if section:
        # Try exact match first
        config = AcademicPeriodConfig.objects.filter(academic_year=section.academic_year).first()
        # Fallback: try partial match (e.g. section="2026" matches config="2025-26")
        if not config:
            config = AcademicPeriodConfig.objects.filter(
                academic_year__icontains=section.academic_year
            ).first()
        if not config:
            # Last resort: show all configs so the user isn't stuck
            all_configs = AcademicPeriodConfig.objects.all()
            for c in all_configs:
                if viewer.role in [User.Role.ADMIN, User.Role.TEACHER]:
                    periods = c.periods.all()
                else:
                    periods = c.periods.filter(is_published=True)
                configs.append({'config': c, 'periods': periods})
        else:
            if viewer.role in [User.Role.ADMIN, User.Role.TEACHER]:
                periods = config.periods.all()
            else:
                periods = config.periods.filter(is_published=True)
            configs.append({'config': config, 'periods': periods})

    context = {
        'student': student,
        'profile': profile,
        'section': section,
        'configs': configs,
    }
    return render(request, 'dashboard/period_report_select.html', context)


@login_required
def period_report(request, period_id, student_id):
    """View a student's report card for a specific period."""
    viewer = request.user
    period = get_object_or_404(ReportPeriod.objects.select_related('config'), id=period_id)
    student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    printable = request.GET.get('print', '') == '1'

    if viewer.role == User.Role.STUDENT and viewer != student:
        return redirect('dashboard_router')
    if viewer.role == User.Role.PARENT:
        parent_profile = ParentProfile.objects.filter(user=viewer).first()
        if not parent_profile or student not in parent_profile.children.all():
            return redirect('dashboard_router')

    if viewer.role not in [User.Role.ADMIN, User.Role.TEACHER] and not period.is_published:
        messages.error(request, "This report period is not yet published.")
        return redirect('dashboard_router')

    profile = StudentProfile.objects.filter(user=student).first()
    section = profile.section if profile else None
    grade_settings = GradeSetting.objects.all()

    grades = []
    overall_total = Decimal('0')
    subject_count = 0

    if section:
        subjects = Subject.objects.filter(
            assessmentrecord__section=section,
            assessmentrecord__date_conducted__gte=period.start_date,
            assessmentrecord__date_conducted__lte=period.end_date,
        ).distinct()

        # Load all period weightings (defaults + subject-specific)
        all_weightings = period.weightings.select_related('assessment_type', 'subject').all()
        default_weights = {pw.assessment_type_id: pw.weight_percentage for pw in all_weightings if pw.subject is None}

        # Build per-subject override map: {subject_id: {at_id: weight}}
        subject_weight_overrides = {}
        for pw in all_weightings:
            if pw.subject_id:
                subject_weight_overrides.setdefault(pw.subject_id, {})[pw.assessment_type_id] = pw.weight_percentage

        # Pre-fetch all assessment type names to avoid N+1 inside loop
        all_at_ids = set()
        for wt in default_weights.keys():
            all_at_ids.add(wt)
        for overrides in subject_weight_overrides.values():
            all_at_ids.update(overrides.keys())
        at_name_map = dict(
            AssessmentType.objects.filter(id__in=all_at_ids).values_list('id', 'name')
        )

        for subj in subjects:
            # Use subject-specific weights if available, else defaults
            weights_for_subj = subject_weight_overrides.get(subj.id, default_weights)
            score, details = calculate_period_grade(
                student, subj, section, period, weights_for_subj, at_name_map=at_name_map
            )
            letter = get_letter_grade(score, grade_settings)
            comment_obj = SubjectComment.objects.filter(
                student=student, subject=subj, section=section, academic_year=section.academic_year, period=period
            ).first()
            grades.append({
                'subject': subj,
                'score': score,
                'letter': letter['letter'],
                'remark': letter['remark'],
                'grade_point': letter['grade_point'],
                'details': details,
                'comment': comment_obj.comment if comment_obj else '',
            })
            overall_total += score
            subject_count += 1

    overall_avg = round(overall_total / subject_count, 1) if subject_count > 0 else 0
    overall_letter = get_letter_grade(overall_avg, grade_settings)

    context = {
        'student': student,
        'profile': profile,
        'section': section,
        'period': period,
        'grades': grades,
        'overall_avg': overall_avg,
        'overall_letter': overall_letter,
        'grade_settings': grade_settings,
    }

    if printable:
        return render(request, 'dashboard/period_report_print.html', context)
    return render(request, 'dashboard/period_report.html', context)


# _calculate_period_grade is now in exams/services.py as calculate_period_grade.
# Alias kept for any external code that may reference it.
_calculate_period_grade = calculate_period_grade
