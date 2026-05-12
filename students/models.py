from django.db import models
from django.conf import settings


class StudentProfile(models.Model):
    """Extended profile for a student user."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_profile', limit_choices_to={'role': 'student'})
    section = models.ForeignKey('academics.Section', on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    roll_number = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    guardian_name = models.CharField(max_length=100, blank=True)
    guardian_phone = models.CharField(max_length=15, blank=True)
    admission_date = models.DateField(auto_now_add=True)
    biometric_id = models.CharField(max_length=50, blank=True, null=True, unique=True, help_text="ID from attendance machine")
    photo = models.ImageField(upload_to='student_photos/', blank=True, null=True, verbose_name="Photo")

    def __str__(self):
        section_str = self.section if self.section else "Unassigned"
        return f"{self.user.get_full_name() or self.user.username} - {section_str}"


class ParentProfile(models.Model):
    """Links a parent user to one or more student users."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='parent_profile', limit_choices_to={'role': 'parent'})
    children = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='parents', limit_choices_to={'role': 'student'}, blank=True)

    def __str__(self):
        kids = ", ".join([c.get_full_name() or c.username for c in self.children.all()])
        return f"{self.user.get_full_name() or self.user.username} → {kids or 'No children'}"


class TeacherProfile(models.Model):
    """Extended profile for a teacher user."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='teacher_profile', limit_choices_to={'role': 'teacher'}
    )
    employee_id = models.CharField(max_length=30, blank=True, verbose_name="Employee ID")
    qualification = models.CharField(max_length=200, blank=True, verbose_name="Qualification")
    specialization = models.CharField(max_length=200, blank=True, verbose_name="Specialization")
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Date of Birth")
    date_of_joining = models.DateField(null=True, blank=True, verbose_name="Date of Joining")
    address = models.TextField(blank=True, verbose_name="Address")
    experience_years = models.PositiveIntegerField(default=0, verbose_name="Years of Experience")
    biometric_id = models.CharField(max_length=50, blank=True, null=True, unique=True, help_text="ID from attendance machine")
    photo = models.ImageField(upload_to='teacher_photos/', blank=True, null=True, verbose_name="Photo")

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} (Teacher)"
