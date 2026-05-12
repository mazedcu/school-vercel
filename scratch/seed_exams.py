from exams.models import AssessmentType
names = ["Quiz", "Assignment", "Class Test", "CT", "Mid Term", "Final Term", "Half Yearly", "Lab"]
for name in names:
    obj, created = AssessmentType.objects.get_or_create(name=name)
    if created:
        print(f"Created: {name}")
    else:
        print(f"Exists: {name}")
