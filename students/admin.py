from django.contrib import admin
from .models import StudentProfile, ParentProfile

@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'section', 'roll_number', 'admission_date')
    list_filter = ('section',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'roll_number')

@admin.register(ParentProfile)
class ParentProfileAdmin(admin.ModelAdmin):
    list_display = ('user',)
    filter_horizontal = ('children',)
