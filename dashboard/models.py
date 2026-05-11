from django.db import models
from accounts.models import User

class Notice(models.Model):
    TARGET_CHOICES = [
        ('all', 'All Users'),
        ('teacher', 'Teachers Only'),
        ('student_parent', 'Students & Parents Only'),
    ]

    title = models.CharField(max_length=200)
    content = models.TextField()
    target_role = models.CharField(max_length=20, choices=TARGET_CHOICES, default='all')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_notices')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
