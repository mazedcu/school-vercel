from django.contrib import admin
from .models import LessonPlan


@admin.register(LessonPlan)
class LessonPlanAdmin(admin.ModelAdmin):
    list_display = ['lesson_title', 'subject', 'section', 'teacher', 'date', 'status']
    list_filter = ['status', 'subject', 'date']
    search_fields = ['lesson_title', 'main_topic', 'teacher__username']
    readonly_fields = ['created_at', 'updated_at', 'reviewed_at']
