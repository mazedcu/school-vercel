import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Attendance
from students.models import StudentProfile, TeacherProfile
from academics.models import Section
from accounts.models import User
from django.conf import settings
from datetime import datetime

@csrf_exempt
def sync_attendance(request):
    """
    Endpoint for attendance machine / gateway script to POST logs.
    Expects JSON: {
        "token": "YOUR_SECRET_TOKEN",
        "logs": [
            {"biometric_id": "101", "timestamp": "2024-05-12 08:30:00", "type": "in"},
            ...
        ]
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Token validated against settings (configured in settings.py with fail-loud in production)
    if data.get('token') != settings.ATTENDANCE_API_TOKEN:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    logs = data.get('logs', [])
    processed_count = 0
    errors = []

    for log in logs:
        bio_id = log.get('biometric_id')
        ts_str = log.get('timestamp') # Format: YYYY-MM-DD HH:MM:SS
        
        try:
            ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
            log_date = ts.date()
        except Exception as e:
            errors.append(f"Invalid timestamp for ID {bio_id}: {str(e)}")
            continue

        # Try to find student first, then teacher
        student_profile = StudentProfile.objects.filter(biometric_id=bio_id).first()
        user = None
        section = None

        if student_profile:
            user = student_profile.user
            section = student_profile.section
        else:
            teacher_profile = TeacherProfile.objects.filter(biometric_id=bio_id).first()
            if teacher_profile:
                user = teacher_profile.user
                # For teachers, section is irrelevant in the current Attendance model structure 
                # (though the model currently requires it. We'll need to handle this).
        
        if user:
            # Determine status (Simple logic: first scan of the day marks present)
            status = Attendance.Status.PRESENT
            
            # Check if attendance already marked for today
            existing = Attendance.objects.filter(user=user, date=log_date).exists()
            if not existing:
                Attendance.objects.create(
                    user=user,
                    section=section,
                    date=log_date,
                    status=status,
                    marked_by=None # Marked by system
                )
                processed_count += 1
        else:
            errors.append(f"No user found for Biometric ID {bio_id}")

    return JsonResponse({
        'status': 'success',
        'processed': processed_count,
        'errors': errors
    })
