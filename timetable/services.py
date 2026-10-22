from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import TimetableEntry


def validation_message(error):
    """Flatten a ValidationError into one readable sentence."""
    if hasattr(error, 'message_dict'):
        parts = [m for msgs in error.message_dict.values() for m in msgs]
    else:
        parts = list(error.messages)
    return " ".join(parts)


def save_timetable_entry(section, subject, teacher, time_slot, room='', entry=None):
    """
    Create a timetable entry, or update `entry` in place, after clash checks.
    Returns (entry, None) on success or (None, error_message) on a clash.
    """
    entry = entry or TimetableEntry()
    entry.section = section
    entry.subject = subject
    entry.teacher = teacher
    entry.time_slot = time_slot
    entry.room = room or ''
    try:
        # full_clean runs TimetableEntry.clean(): section, teacher and room clash checks
        entry.full_clean()
        with transaction.atomic():
            entry.save()
    except ValidationError as e:
        return None, validation_message(e)
    except IntegrityError:
        return None, "This section already has a class in that period."
    return entry, None


def generate_timetable_entry(section, subject, teacher, time_slot, room=''):
    """Backwards-compatible wrapper: returns (success_boolean, message)."""
    entry, error = save_timetable_entry(section, subject, teacher, time_slot, room=room)
    if error:
        return False, "Conflict Detected: " + error
    return True, "Timetable entry created successfully."
