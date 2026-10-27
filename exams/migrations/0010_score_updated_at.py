import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0009_score_not_applicable"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentscore",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
