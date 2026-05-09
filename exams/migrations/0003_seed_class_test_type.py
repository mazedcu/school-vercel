from django.db import migrations

def seed_assessment_types(apps, schema_editor):
    AssessmentType = apps.get_model('exams', 'AssessmentType')
    types = ["Class Test", "Half Yearly", "Final Term", "Assignment", "Lab"]
    for t in types:
        AssessmentType.objects.get_or_create(name=t)

class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0002_gradesetting_subjectcomment'),
    ]

    operations = [
        migrations.RunPython(seed_assessment_types),
    ]
