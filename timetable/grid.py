"""
Shared helpers for building timetable grids (days across, periods down).

The week starts on Saturday, as it does in Bangladesh; only days that have at
least one time slot are shown, so a Sunday–Thursday or Saturday–Thursday
school week both display correctly.
"""
from django.db.models import Case, IntegerField, Value, When

from timetable.models import TimeSlot

DAY_ORDER = ['saturday', 'sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday']
DAY_LABELS = {
    'saturday': 'Sat', 'sunday': 'Sun', 'monday': 'Mon', 'tuesday': 'Tue',
    'wednesday': 'Wed', 'thursday': 'Thu', 'friday': 'Fri',
}
DAY_INDEX = {d: i for i, d in enumerate(DAY_ORDER)}


def day_order_expr(field='day'):
    """Database expression that sorts day names in week order (not alphabetically)."""
    return Case(
        *[When(**{field: d}, then=Value(i)) for i, d in enumerate(DAY_ORDER)],
        default=Value(len(DAY_ORDER)),
        output_field=IntegerField(),
    )


def sorted_slots(qs=None):
    """TimeSlots ordered by week day, then start time."""
    qs = TimeSlot.objects.all() if qs is None else qs
    return qs.annotate(_day_idx=day_order_expr()).order_by('_day_idx', 'start_time')


def working_days(slots=None):
    """Days (in week order) that have at least one time slot."""
    if slots is None:
        days = set(TimeSlot.objects.values_list('day', flat=True))
    else:
        days = {s.day for s in slots}
    return [d for d in DAY_ORDER if d in days]


def time_label(start, end):
    return f"{start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}"


def build_grid(entries, slots=None):
    """
    Lay out timetable entries as rows of periods × columns of working days.

    Returns (day_headers, rows). Each row is {'time', 'start', 'end', 'cells'}; each
    cell is {'slot', 'entry', 'subject', 'teacher', 'room'}. `slot` is None where
    that day has no period at that time.
    """
    slots = list(sorted_slots() if slots is None else slots)
    days = working_days(slots)
    day_headers = [{'key': d, 'label': DAY_LABELS[d]} for d in days]

    slot_at = {(s.day, s.start_time, s.end_time): s for s in slots}
    entry_at = {e.time_slot_id: e for e in entries}
    times = sorted({(s.start_time, s.end_time) for s in slots})

    rows = []
    for start, end in times:
        cells = []
        for day in days:
            slot = slot_at.get((day, start, end))
            entry = entry_at.get(slot.id) if slot else None
            cells.append({
                'slot': slot,
                'entry': entry,
                'subject': entry.subject.name if entry else '',
                'teacher': (entry.teacher.get_full_name() or entry.teacher.username) if entry else '',
                'room': entry.room if entry else '',
            })
        rows.append({'time': time_label(start, end), 'start': start, 'end': end, 'cells': cells})
    return day_headers, rows
