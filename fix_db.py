from decimal import Decimal
from exams.models import AssessmentRecord, StudentScore
from finance.models import Invoice, Payment

print("Fixing AssessmentRecord marks...")
for ar in AssessmentRecord.objects.all():
    if ar.total_marks is None or ar.total_marks < 0:
        ar.total_marks = Decimal('100.0')
        ar.save()

print("Fixing StudentScore marks...")
for ss in StudentScore.objects.all():
    if ss.marks_obtained is None or ss.marks_obtained < 0:
        ss.marks_obtained = Decimal('0.0')
        ss.save()
    if ss.assessment.total_marks > 0 and ss.marks_obtained > ss.assessment.total_marks:
        ss.marks_obtained = ss.assessment.total_marks
        ss.save()

print("Fixing Invoices...")
for inv in Invoice.objects.all():
    if inv.amount_due < 0:
        inv.amount_due = Decimal('0.0')
        inv.save()

print("Fixing Payments...")
for pay in Payment.objects.all():
    if pay.amount < 0:
        pay.amount = Decimal('0.0')
        pay.save()

print("Database sanitation complete.")
