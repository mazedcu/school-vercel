from django.contrib import admin
from .models import Attendance

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'section', 'date', 'status', 'marked_by')
    list_filter = ('status', 'date', 'section')
    search_fields = ('student__username',)
