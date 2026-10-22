import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import role_required
from accounts.models import User
from academics.models import Section, Subject
from students.models import StudentProfile
from timetable.grid import DAY_ORDER, build_grid, sorted_slots, time_label
from timetable.models import TEACHING_ROLES, TimeSlot, TimetableEntry
from timetable.pdf_utils import generate_section_timetable_pdf, generate_teacher_timetable_pdf
from timetable.services import save_timetable_entry, validation_message

logger = logging.getLogger(__name__)

DAY_FULL_NAMES = dict(TimeSlot.DAY_CHOICES)


def _section_entries(section):
    return TimetableEntry.objects.filter(section=section).select_related(
        'subject', 'teacher', 'time_slot'
    )


def _teacher_name(user):
    return user.get_full_name() or user.username


def _section_name(section):
    return f"{section.class_group.name} – {section.name}"


def _cell_json(entry):
    return {
        'entry_id': entry.id,
        'subject_id': entry.subject_id,
        'subject': entry.subject.name,
        'teacher_id': entry.teacher_id,
        'teacher': _teacher_name(entry.teacher),
        'room': entry.room,
    }


# ── Setup: routine grid editor (admin) ─────────────────────────────────────────

def _add_periods(request):
    """Create the same list of periods on every ticked day."""
    days = [d for d in request.POST.getlist('days') if d in DAY_FULL_NAMES]
    pairs = [
        (s.strip(), e.strip())
        for s, e in zip(request.POST.getlist('start_time'), request.POST.getlist('end_time'))
        if s.strip() or e.strip()
    ]
    if not days or not pairs:
        messages.error(request, "Tick at least one day and enter at least one period.")
        return

    created, existing, errors = 0, 0, []
    for day in days:
        for start, end in pairs:
            if not (start and end):
                errors.append(f"{DAY_FULL_NAMES[day]}: each period needs a start and an end time.")
                continue
            if TimeSlot.objects.filter(day=day, start_time=start, end_time=end).exists():
                existing += 1
                continue
            slot = TimeSlot(day=day, start_time=start, end_time=end)
            try:
                slot.full_clean()
                slot.save()
                created += 1
            except ValidationError as e:
                errors.append(f"{DAY_FULL_NAMES[day]} {start}–{end}: {validation_message(e)}")

    if created:
        messages.success(request, f"{created} period(s) added.")
    if existing:
        messages.info(request, f"{existing} period(s) already existed and were skipped.")
    for err in errors:
        messages.error(request, err)


@login_required
@role_required(User.Role.ADMIN)
def timetable_gen(request):
    sections = Section.objects.select_related('class_group').order_by('class_group__name', 'name')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_periods':
            _add_periods(request)
        elif action == 'delete_slot':
            slot = get_object_or_404(TimeSlot, pk=request.POST.get('slot_id'))
            removed = slot.timetableentry_set.count()
            slot.delete()
            msg = f"Period {slot} deleted."
            if removed:
                msg += f" {removed} scheduled class(es) in it were removed too."
            messages.success(request, msg)
        url = reverse('timetable_gen')
        if request.POST.get('section'):
            url += f"?section={request.POST['section']}"
        return redirect(url)

    selected = None
    section_id = request.GET.get('section')
    if section_id:
        selected = sections.filter(id=section_id).first()
    if selected is None:
        selected = sections.first()

    slots = list(sorted_slots())
    day_headers, grid_rows = build_grid(_section_entries(selected) if selected else [], slots)

    slots_by_day = []
    for day in DAY_ORDER:
        day_slots = [s for s in slots if s.day == day]
        if day_slots:
            slots_by_day.append({'label': DAY_FULL_NAMES[day], 'slots': day_slots})

    context = {
        'sections': sections,
        'selected_section': selected,
        'day_headers': day_headers,
        'grid_rows': grid_rows,
        'subjects': Subject.objects.order_by('name'),
        'teachers': User.objects.filter(role__in=TEACHING_ROLES, is_active=True)
                                .order_by('first_name', 'last_name', 'username'),
        'slots_by_day': slots_by_day,
        'day_choices': [(d, DAY_FULL_NAMES[d]) for d in DAY_ORDER],
        'scheduled_count': sum(1 for row in grid_rows for c in row['cells'] if c['entry']),
    }
    return render(request, 'dashboard/timetable_gen.html', context)


@login_required
@role_required(User.Role.ADMIN)
@require_GET
def timetable_slot_info(request):
    """Who and what is already busy during this period, in other sections."""
    slot = get_object_or_404(TimeSlot, pk=request.GET.get('slot'))
    section_id = request.GET.get('section')
    busy = TimetableEntry.objects.filter(
        time_slot__day=slot.day,
        time_slot__start_time__lt=slot.end_time,
        time_slot__end_time__gt=slot.start_time,
    ).exclude(section_id=section_id).select_related('section__class_group', 'subject')

    busy_teachers, busy_rooms = {}, {}
    for e in busy:
        where = f"{_section_name(e.section)} ({e.subject.name})"
        busy_teachers[str(e.teacher_id)] = where
        if e.room:
            busy_rooms[e.room.lower()] = where
    return JsonResponse({
        'label': f"{DAY_FULL_NAMES[slot.day]}, {time_label(slot.start_time, slot.end_time)}",
        'busy_teachers': busy_teachers,
        'busy_rooms': busy_rooms,
    })


@login_required
@role_required(User.Role.ADMIN)
@require_POST
def timetable_save_entry(request):
    """Create or update the class in one cell of the grid."""
    try:
        section = Section.objects.get(pk=request.POST.get('section'))
        slot = TimeSlot.objects.get(pk=request.POST.get('slot'))
        subject = Subject.objects.get(pk=request.POST.get('subject'))
        teacher = User.objects.get(pk=request.POST.get('teacher'))
    except (Section.DoesNotExist, TimeSlot.DoesNotExist, Subject.DoesNotExist,
            User.DoesNotExist, ValueError):
        return JsonResponse({'ok': False, 'error': "Choose a subject and a teacher."}, status=400)

    entry = None
    entry_id = request.POST.get('entry')
    if entry_id:
        entry = TimetableEntry.objects.filter(pk=entry_id, section=section).first()
        if entry is None:
            return JsonResponse({'ok': False, 'error': "That class no longer exists. Reload the page."}, status=404)
    else:
        entry = TimetableEntry.objects.filter(section=section, time_slot=slot).first()

    entry, error = save_timetable_entry(
        section, subject, teacher, slot, room=request.POST.get('room', ''), entry=entry
    )
    if error:
        return JsonResponse({'ok': False, 'error': error}, status=409)
    return JsonResponse({'ok': True, 'cell': _cell_json(entry)})


@login_required
@role_required(User.Role.ADMIN)
@require_POST
def timetable_delete_entry(request):
    entry_id = request.POST.get('entry', '')
    if not entry_id.isdigit():
        return JsonResponse({'ok': False, 'error': "There is no class here to remove."}, status=400)
    TimetableEntry.objects.filter(pk=entry_id).delete()
    return JsonResponse({'ok': True})


# ── Read-only views ────────────────────────────────────────────────────────────

@login_required
def view_timetable(request):
    """Class-wise visual timetable grid view."""
    sections = Section.objects.select_related('class_group').all()
    selected_section_id = request.GET.get('section', '')
    selected_section = None
    grid_rows, day_headers = [], []

    if selected_section_id:
        selected_section = sections.filter(id=selected_section_id).first()
        if selected_section:
            day_headers, grid_rows = build_grid(_section_entries(selected_section))

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
    elif user.role not in [User.Role.ADMIN, User.Role.TEACHER, User.Role.COORDINATOR]:
        return redirect('dashboard_router')

    try:
        pdf_buffer = generate_section_timetable_pdf(section)
        filename = f"timetable_{section.class_group.name}_{section.name}.pdf".replace(' ', '_')

        response = HttpResponse(pdf_buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        logger.error("Failed to generate section timetable PDF: %s", e, exc_info=True)
        messages.error(request, "Failed to generate the timetable PDF. Please try again or contact the administrator.")
        return redirect('view_timetable')


@login_required
@role_required(User.Role.TEACHER, User.Role.COORDINATOR)
def download_teacher_timetable_pdf(request):
    try:
        pdf_buffer = generate_teacher_timetable_pdf(request.user)
        filename = f"timetable_{_teacher_name(request.user).replace(' ', '_')}.pdf"

        response = HttpResponse(pdf_buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        logger.error("Failed to generate teacher timetable PDF: %s", e, exc_info=True)
        messages.error(request, "Failed to generate the timetable PDF. Please try again or contact the administrator.")
        return redirect('dashboard_router')


@login_required
@role_required(User.Role.STUDENT)
def my_timetable(request):
    profile = StudentProfile.objects.filter(user=request.user).first()
    section = profile.section if profile else None
    grid_rows, day_headers = [], []

    if section:
        entries = list(_section_entries(section))
        if entries:
            day_headers, grid_rows = build_grid(entries)

    context = {'section': section, 'grid_rows': grid_rows, 'day_headers': day_headers}
    return render(request, 'dashboard/my_timetable.html', context)
