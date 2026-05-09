from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from django.contrib import messages
from django.db.models import Count, Q, Avg
from django.utils import timezone
from decimal import Decimal
import datetime

from accounts.models import User
from academics.models import ClassGroup, Section, Subject
from students.models import StudentProfile, ParentProfile
from timetable.models import TimeSlot, TimetableEntry
from timetable.services import generate_timetable_entry
from timetable.pdf_utils import generate_section_timetable_pdf, generate_teacher_timetable_pdf
from attendance.models import Attendance
from exams.models import AssessmentType, SubjectWeighting, WeightingComponent, AssessmentRecord, StudentScore, GradeSetting, SubjectComment
from finance.models import FeeStructure, Invoice, Payment



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
        total_marks = request.POST.get('total_marks', '100')
        date_conducted = request.POST.get('date_conducted', timezone.now().date().isoformat())

        try:
            section = Section.objects.get(id=section_id)
            subject = Subject.objects.get(id=subject_id)
            assessment_type = AssessmentType.objects.get(id=assessment_type_id)
            record = AssessmentRecord.objects.create(
                section=section, subject=subject, assessment_type=assessment_type,
                title=title, total_marks=Decimal(total_marks), date_conducted=date_conducted
            )
            messages.success(request, f"Assessment '{title}' created. Now enter marks.")
            return redirect(f'/enter_marks/{record.id}/')
        except Exception as e:
            messages.error(request, str(e))
        return redirect('manage_assessments')

    sections = Section.objects.all()
    subjects = Subject.objects.all()
    assessment_types = AssessmentType.objects.all()
    recent = AssessmentRecord.objects.all().select_related('section__class_group', 'subject', 'assessment_type').order_by('-date_conducted')[:20]

    context = {
        'sections': sections,
        'subjects': subjects,
        'assessment_types': assessment_types,
        'recent_assessments': recent,
    }
    return render(request, 'dashboard/manage_assessments.html', context)

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def enter_marks(request, assessment_id):

    assessment = get_object_or_404(AssessmentRecord, pk=assessment_id)
    profiles = StudentProfile.objects.filter(section=assessment.section).select_related('user')

    if request.method == 'POST':
        for p in profiles:
            marks = request.POST.get(f'marks_{p.user.id}', '')
            if marks:
                try:
                    m = Decimal(marks)
                    StudentScore.objects.update_or_create(
                        assessment=assessment, student=p.user,
                        defaults={'marks_obtained': m}
                    )
                except Exception:
                    pass
        messages.success(request, f"Marks saved for '{assessment.title}'.")
        return redirect(f'/enter_marks/{assessment_id}/')

    students_marks = []
    for p in profiles:
        existing = StudentScore.objects.filter(assessment=assessment, student=p.user).first()
        students_marks.append({
            'user': p.user,
            'roll': p.roll_number,
            'marks': existing.marks_obtained if existing else '',
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
            score = _calculate_student_grade(student, subj, section)
            letter = _get_letter_grade(score, grade_settings)
            comment_obj = SubjectComment.objects.filter(
                student=student, subject=subj, section=section, academic_year=section.academic_year
            ).first()
            grades.append({
                'subject': subj,
                'score': score,
                'letter': letter['letter'],
                'remark': letter['remark'],
                'grade_point': letter['grade_point'],
                'details': _get_grade_details(student, subj, section),
                'comment': comment_obj.comment if comment_obj else '',
            })
            overall_total += score
            subject_count += 1

    overall_avg = round(overall_total / subject_count, 1) if subject_count > 0 else 0
    overall_letter = _get_letter_grade(overall_avg, grade_settings)

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
    """Teacher: add comments for students per subject."""

    sections = Section.objects.all()
    subjects = Subject.objects.all()
    selected_section = None
    selected_subject = None
    students_comments = []

    if request.method == 'POST':
        section_id = request.POST.get('section_id')
        subject_id = request.POST.get('subject_id')
        section = Section.objects.filter(id=section_id).first()
        subject = Subject.objects.filter(id=subject_id).first()
        if section and subject:
            profiles = StudentProfile.objects.filter(section=section).select_related('user')
            for p in profiles:
                comment_text = request.POST.get(f'comment_{p.user.id}', '').strip()
                if comment_text:
                    SubjectComment.objects.update_or_create(
                        student=p.user, subject=subject, section=section, academic_year=section.academic_year,
                        defaults={'comment': comment_text, 'commented_by': request.user}
                    )
            messages.success(request, f"Comments saved for {subject.name} in {section}.")
        return redirect(f'/subject_comments/?section={section_id}&subject={subject_id}')

    if request.GET.get('section') and request.GET.get('subject'):
        selected_section = Section.objects.filter(id=request.GET['section']).first()
        selected_subject = Subject.objects.filter(id=request.GET['subject']).first()
        if selected_section and selected_subject:
            profiles = StudentProfile.objects.filter(section=selected_section).select_related('user')
            for p in profiles:
                existing = SubjectComment.objects.filter(
                    student=p.user, subject=selected_subject, section=selected_section,
                    academic_year=selected_section.academic_year
                ).first()
                students_comments.append({
                    'user': p.user,
                    'roll': p.roll_number,
                    'comment': existing.comment if existing else '',
                })

    context = {
        'sections': sections,
        'subjects': subjects,
        'selected_section': selected_section,
        'selected_subject': selected_subject,
        'students_comments': students_comments,
    }
    return render(request, 'dashboard/subject_comments.html', context)

def _calculate_student_grade(student, subject, section):
    """Calculate weighted final grade for a student in a subject."""
    try:
        weighting = SubjectWeighting.objects.get(
            section=section, subject=subject, academic_year=section.academic_year
        )
    except SubjectWeighting.DoesNotExist:
        # Fall back to simple average
        scores = StudentScore.objects.filter(student=student, assessment__subject=subject, assessment__section=section)
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
    for comp in weighting.components.all():
        weight = comp.weight_percentage / Decimal('100')
        scores = StudentScore.objects.filter(
            student=student,
            assessment__subject=subject,
            assessment__section=section,
            assessment__assessment_type=comp.assessment_type
        )
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

def _get_grade_details(student, subject, section):
    """Return breakdown by assessment type for report card."""
    details = []
    try:
        weighting = SubjectWeighting.objects.get(section=section, subject=subject, academic_year=section.academic_year)
    except SubjectWeighting.DoesNotExist:
        return details

    for comp in weighting.components.all():
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

def _get_letter_grade(score, grade_settings):
    """Return letter grade, remark, and grade point for a given score."""
    for g in grade_settings:
        if g.min_score <= score <= g.max_score:
            return {'letter': g.letter, 'remark': g.remark, 'grade_point': g.grade_point}
    return {'letter': '-', 'remark': '', 'grade_point': Decimal('0')}


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
                score = StudentScore.objects.filter(assessment=ct, student=student).first()
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

            letter = _get_letter_grade(pct, grade_settings)
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
        overall_letter = _get_letter_grade(overall_pct, grade_settings)

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