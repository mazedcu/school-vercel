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
@role_required(User.Role.ADMIN)
def timetable_gen(request):

    if request.method == 'POST':
        action = request.POST.get('action', 'add_entry')

        if action == 'add_slot':
            # ── Create a new TimeSlot ──────────────────────────────────────────
            day = request.POST.get('day', '').strip()
            start = request.POST.get('start_time', '').strip()
            end   = request.POST.get('end_time', '').strip()
            if day and start and end:
                try:
                    TimeSlot.objects.get_or_create(day=day, start_time=start, defaults={'end_time': end})
                    messages.success(request, f"Time slot {day} {start}-{end} added.")
                except Exception as e:
                    messages.error(request, f"Time slot error: {e}")
            else:
                messages.error(request, "All time slot fields are required.")

        elif action == 'delete_slot':
            # ── Delete a TimeSlot ──────────────────────────────────────────────
            slot_id = request.POST.get('slot_id')
            slot = get_object_or_404(TimeSlot, pk=slot_id)
            try:
                slot.delete()
                messages.success(request, "Time slot deleted.")
            except Exception as e:
                messages.error(request, f"Cannot delete: {e}")

        elif action == 'delete_entry':
            # ── Delete a TimetableEntry ────────────────────────────────────────
            entry_id = request.POST.get('entry_id')
            entry = get_object_or_404(TimetableEntry, pk=entry_id)
            entry.delete()
            messages.success(request, "Timetable entry deleted.")

        else:
            # ── Assign a TimetableEntry ───────────────────────────────────────
            section_id   = request.POST.get('section')
            subject_id   = request.POST.get('subject')
            teacher_id   = request.POST.get('teacher')
            time_slot_id = request.POST.get('time_slot')
            room         = request.POST.get('room', '').strip()
            try:
                section    = Section.objects.get(id=section_id)
                subject    = Subject.objects.get(id=subject_id)
                teacher    = User.objects.get(id=teacher_id)
                time_slot  = TimeSlot.objects.get(id=time_slot_id)
                success, msg = generate_timetable_entry(section, subject, teacher, time_slot, room=room)
                if success:
                    messages.success(request, msg)
                else:
                    messages.error(request, msg)
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")

        return redirect('timetable_gen')

    sections   = Section.objects.all()
    subjects   = Subject.objects.all()
    teachers   = User.objects.filter(role=User.Role.TEACHER)
    time_slots = TimeSlot.objects.all()
    entries    = TimetableEntry.objects.all().select_related(
        'section__class_group', 'subject', 'teacher', 'time_slot'
    ).order_by('time_slot__day', 'time_slot__start_time')

    DAY_CHOICES = [
        ("monday",    "Monday"),
        ("tuesday",   "Tuesday"),
        ("wednesday", "Wednesday"),
        ("thursday",  "Thursday"),
        ("friday",    "Friday"),
        ("saturday",  "Saturday"),
        ("sunday",    "Sunday"),
    ]

    context = {
        'sections':   sections,
        'subjects':   subjects,
        'teachers':   teachers,
        'time_slots': time_slots,
        'entries':    entries,
        'day_choices': DAY_CHOICES,
    }
    return render(request, 'dashboard/timetable_gen.html', context)

@login_required
def view_timetable(request):
    """Class-wise visual timetable grid view."""
    sections = Section.objects.all()
    selected_section_id = request.GET.get('section', '')
    selected_section = None
    grid_rows = []
    day_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    day_labels_map = {'monday': 'Mon', 'tuesday': 'Tue', 'wednesday': 'Wed',
                      'thursday': 'Thu', 'friday': 'Fri', 'saturday': 'Sat', 'sunday': 'Sun'}
    active_days = []
    day_headers = []

    if selected_section_id:
        selected_section = Section.objects.filter(id=selected_section_id).first()
        if selected_section:
            entries = TimetableEntry.objects.filter(section=selected_section).select_related(
                'subject', 'teacher', 'time_slot'
            )

            # Build lookup: (day, start_time, end_time) -> entry
            lookup = {}
            for e in entries:
                key = (e.time_slot.day, str(e.time_slot.start_time), str(e.time_slot.end_time))
                lookup[key] = e

            # Determine active days
            active_day_set = set(e.time_slot.day for e in entries)
            active_days = [d for d in day_order if d in active_day_set]
            if not active_days:
                active_days = day_order[:5]

            day_headers = [{'key': d, 'label': day_labels_map.get(d, d)} for d in active_days]

            # Get unique time slots
            unique_times = TimeSlot.objects.values_list('start_time', 'end_time').distinct().order_by('start_time')

            # Build grid rows
            for start_time, end_time in unique_times:
                time_label = f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
                cells = []
                for day in active_days:
                    entry = lookup.get((day, str(start_time), str(end_time)))
                    cells.append({
                        'entry': entry,
                        'subject': entry.subject.name if entry else '',
                        'teacher': (entry.teacher.get_full_name() or entry.teacher.username) if entry else '',
                        'room': entry.room if entry and entry.room else '',
                    })
                grid_rows.append({
                    'time': time_label,
                    'cells': cells,
                })

    context = {
        'sections': sections,
        'selected_section': selected_section,
        'selected_section_id': selected_section_id,
        'grid_rows': grid_rows,
        'day_headers': day_headers,
    }
    return render(request, 'dashboard/view_timetable.html', context)

@login_required
def download_timetable_pdf(request, section_id):
    """Download class-wise timetable as PDF. Available to admin and students of that section."""
    section = get_object_or_404(Section, pk=section_id)

    # Access control: admin can download any, students only their own section
    user = request.user
    if user.role == User.Role.STUDENT:
        profile = StudentProfile.objects.filter(user=user).first()
        if not profile or profile.section_id != section.id:
            messages.error(request, "You can only download your own class timetable.")
            return redirect('dashboard_router')
    elif user.role not in [User.Role.ADMIN, User.Role.TEACHER]:
        return redirect('dashboard_router')

    pdf_buffer = generate_section_timetable_pdf(section)
    filename = f"timetable_{section.class_group.name}_{section.name}.pdf".replace(' ', '_')

    response = HttpResponse(pdf_buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
@role_required(User.Role.TEACHER)
def download_teacher_timetable_pdf(request):

    pdf_buffer = generate_teacher_timetable_pdf(request.user)
    teacher_name = (request.user.get_full_name() or request.user.username).replace(' ', '_')
    filename = f"timetable_{teacher_name}.pdf"

    response = HttpResponse(pdf_buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
@role_required(User.Role.STUDENT)
def my_timetable(request):

    profile = StudentProfile.objects.filter(user=request.user).first()
    section = profile.section if profile else None
    grid_rows = []
    day_headers = []

    if section:
        day_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
        day_labels_map = {'monday': 'Mon', 'tuesday': 'Tue', 'wednesday': 'Wed',
                          'thursday': 'Thu', 'friday': 'Fri', 'saturday': 'Sat'}

        entries = TimetableEntry.objects.filter(section=section).select_related('subject', 'teacher', 'time_slot')
        lookup = {}
        for e in entries:
            lookup[(e.time_slot.day, str(e.time_slot.start_time), str(e.time_slot.end_time))] = e

        active_day_set = set(e.time_slot.day for e in entries)
        active_days = [d for d in day_order if d in active_day_set]
        if not active_days:
            active_days = day_order[:5]
        day_headers = [{'key': d, 'label': day_labels_map.get(d, d)} for d in active_days]

        unique_times = TimeSlot.objects.values_list('start_time', 'end_time').distinct().order_by('start_time')
        for start_time, end_time in unique_times:
            time_label = f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
            cells = []
            for day in active_days:
                entry = lookup.get((day, str(start_time), str(end_time)))
                cells.append({
                    'subject': entry.subject.name if entry else '',
                    'teacher': (entry.teacher.get_full_name() or entry.teacher.username) if entry else '',
                })
            grid_rows.append({'time': time_label, 'cells': cells})

    context = {'section': section, 'grid_rows': grid_rows, 'day_headers': day_headers}
    return render(request, 'dashboard/my_timetable.html', context)