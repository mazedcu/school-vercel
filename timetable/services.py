from django.core.exceptions import ValidationError
from .models import TimetableEntry

def generate_timetable_entry(section, subject, teacher, time_slot, room=''):
    """
    Attempts to create a timetable entry, managing conflicts.
    Returns (success_boolean, message)
    """
    entry = TimetableEntry(
        section=section,
        subject=subject,
        teacher=teacher,
        time_slot=time_slot,
        room=room or ''
    )
    
    try:
        # The clean() method in TimetableEntry handles conflict detection:
        # 1. Teacher cannot be double-booked
        # 2. Section cannot be double-booked (handled by UniqueConstraint)
        # 3. Room cannot be double-booked
        entry.full_clean()
        entry.save()
        return True, "Timetable entry created successfully."
    except ValidationError as e:
        # Format the validation error into a human-readable message
        error_messages = []
        for field, messages in e.message_dict.items():
            error_messages.extend(messages)
        return False, "Conflict Detected: " + " ".join(error_messages)
