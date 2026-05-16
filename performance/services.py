"""
performance/services.py — Business logic for the performance module.
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def calculate_final_score(evaluation):
    """
    Compute the weighted final score for a StaffEvaluation.
    final_score = Σ (kpi_score.score × kpi.max_weight) / 100
    Returns a Decimal rounded to 2dp, or None if no scores exist.
    """
    scores = evaluation.kpi_scores.select_related('kpi').all()
    if not scores.exists():
        return None

    total = Decimal('0')
    for ks in scores:
        contribution = (ks.score * ks.kpi.max_weight) / Decimal('100')
        total += contribution

    return round(total, 2)


def get_performance_grade(score):
    """
    Map a numeric score (0-100) to a grade label and colour.
    Returns dict: {letter, label, colour}
    """
    if score is None:
        return {'letter': '—', 'label': 'Not Evaluated', 'colour': 'grey'}
    score = Decimal(str(score))
    if score >= 90:
        return {'letter': 'A+', 'label': 'Outstanding', 'colour': 'green'}
    elif score >= 80:
        return {'letter': 'A', 'label': 'Excellent', 'colour': 'green'}
    elif score >= 70:
        return {'letter': 'B+', 'label': 'Very Good', 'colour': 'blue'}
    elif score >= 60:
        return {'letter': 'B', 'label': 'Good', 'colour': 'blue'}
    elif score >= 50:
        return {'letter': 'C', 'label': 'Satisfactory', 'colour': 'yellow'}
    else:
        return {'letter': 'D', 'label': 'Needs Improvement', 'colour': 'red'}


def validate_cycle_weights(cycle):
    """
    Check that KPI weights total exactly 100 for each role type that has KPIs.
    Returns a dict: {'teacher': Decimal, 'coordinator': Decimal}
    Missing role = 0 (no KPIs defined for that role).
    """
    from .models import KPISection
    errors = {}
    for role in [KPISection.RoleType.TEACHER, KPISection.RoleType.COORDINATOR]:
        total = cycle.total_weight_for_role(role)
        if total > 0 and total != Decimal('100'):
            errors[role] = total
    return errors


def get_staff_for_cycle(cycle):
    """
    Return queryset of User objects who should be evaluated in this cycle.
    Teachers → role_type='teacher', Coordinators (role='coordinator') → 'coordinator'.
    """
    from accounts.models import User

    teachers = User.objects.filter(
        role=User.Role.TEACHER
    ).select_related()

    coordinators = User.objects.filter(
        role=User.Role.COORDINATOR
    ).select_related()

    return teachers, coordinators


def save_evaluation_scores(evaluation, post_data):
    """
    Bulk-save KPI scores from POST data.
    Expected keys: score_<kpi_id>, comment_<kpi_id>
    Returns (saved_count, errors_list).
    """
    from .models import KPI, KPIScore
    from django.db import transaction

    kpis = KPI.objects.filter(section__cycle=evaluation.cycle, section__role_type=evaluation.role_type)
    errors = []
    saved = 0

    with transaction.atomic():
        for kpi in kpis:
            raw_score = post_data.get(f'score_{kpi.id}', '').strip()
            comment = post_data.get(f'comment_{kpi.id}', '').strip()

            try:
                score_val = Decimal(raw_score) if raw_score else Decimal('0')
                if score_val < 0 or score_val > 100:
                    errors.append(f"'{kpi.title}': score must be 0–100.")
                    score_val = Decimal('0')
            except Exception:
                errors.append(f"'{kpi.title}': invalid score value '{raw_score}'.")
                score_val = Decimal('0')

            KPIScore.objects.update_or_create(
                evaluation=evaluation,
                kpi=kpi,
                defaults={'score': score_val, 'comment': comment}
            )
            saved += 1

    return saved, errors
