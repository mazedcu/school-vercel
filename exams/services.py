from decimal import Decimal
from django.db.models import Sum, Avg
from .models import SubjectWeighting, StudentScore

def calculate_student_final_grade(student, subject, section, academic_year):
    """
    Calculates the final grade out of 100% for a student in a specific subject.
    Uses the highly customizable SubjectWeighting configured by the teacher.
    """
    try:
        weighting_profile = SubjectWeighting.objects.get(
            section=section,
            subject=subject,
            academic_year=academic_year
        )
    except SubjectWeighting.DoesNotExist:
        # If no custom weighting is set, return 0 or calculate unweighted average
        return Decimal('0.00')

    total_weighted_score = Decimal('0.00')

    # Iterate through each defined component (e.g., Quiz: 20%, Final: 80%)
    for component in weighting_profile.components.all():
        assessment_type = component.assessment_type
        weight = component.weight_percentage / Decimal('100.00')

        # Find all scores the student has for this assessment type in this subject
        scores = StudentScore.objects.filter(
            student=student,
            assessment__subject=subject,
            assessment__section=section,
            assessment__assessment_type=assessment_type
        )

        if not scores.exists():
            continue

        # Calculate average percentage for this assessment type
        total_percentage = Decimal('0.00')
        count = 0
        for score in scores:
            if score.assessment.total_marks > 0:
                percentage = (score.marks_obtained / score.assessment.total_marks) * Decimal('100.00')
                total_percentage += percentage
                count += 1
        
        if count > 0:
            average_percentage = total_percentage / Decimal(count)
            # Add to final weighted score
            total_weighted_score += average_percentage * weight

    return round(total_weighted_score, 2)
