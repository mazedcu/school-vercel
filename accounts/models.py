from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin/Principal"
        COORDINATOR = "coordinator", "Coordinator"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"
        PARENT = "parent", "Parent"
        ACCOUNTS = "accounts", "Accounts"

    role = models.CharField(
        max_length=15,
        choices=Role.choices,
        default=Role.STUDENT,
        verbose_name="Role",
    )
    phone = models.CharField(max_length=15, blank=True, verbose_name="Phone Number")

    # Soft-delete / Recycle Bin
    is_deleted = models.BooleanField(default=False, verbose_name="In Recycle Bin")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Deleted At")
    
    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_accounts(self):
        return self.role == self.Role.ACCOUNTS

    def soft_delete(self):
        """Move user to recycle bin (soft delete)."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.is_active = False  # Prevent login while in bin
        self.save(update_fields=['is_deleted', 'deleted_at', 'is_active'])

    def restore(self):
        """Restore user from recycle bin."""
        self.is_deleted = False
        self.deleted_at = None
        self.is_active = True
        self.save(update_fields=['is_deleted', 'deleted_at', 'is_active'])

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
