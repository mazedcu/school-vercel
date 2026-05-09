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

