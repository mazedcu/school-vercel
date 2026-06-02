import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('104.248.226.234', username='root', password='114598Tonni')

cmd = """cd /root/school-vercel && source venv/bin/activate && python manage.py shell -c "
from academics.models import Section
from exams.models import AcademicPeriodConfig, ReportPeriod

print('=== SECTIONS ===')
for s in Section.objects.all()[:10]:
    print(f'  Section: {s.class_group.name} - {s.name}, academic_year=[{s.academic_year}]')

print()
print('=== PERIOD CONFIGS ===')
for c in AcademicPeriodConfig.objects.all():
    print(f'  Config: academic_year=[{c.academic_year}], mode={c.mode}')
    for p in c.periods.order_by('sequence'):
        print(f'    Period: id={p.id}, label={p.label}, seq={p.sequence}')
"
"""

stdin, stdout, stderr = client.exec_command(cmd)
print(stdout.read().decode().strip())
err = stderr.read().decode().strip()
if err:
    print("STDERR:", err)
client.close()
