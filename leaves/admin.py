from django.contrib import admin
from .models import LeaveType, LeavePolicy, LeaveApplication


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(LeavePolicy)
class LeavePolicyAdmin(admin.ModelAdmin):
    list_display = ('leave_type', 'academic_year', 'allocated_days')
    list_filter = ('academic_year',)


@admin.register(LeaveApplication)
class LeaveApplicationAdmin(admin.ModelAdmin):
    list_display = ('applicant', 'leave_type', 'category', 'start_date', 'end_date', 'status', 'applied_at')
    list_filter = ('status', 'category', 'leave_type')
    search_fields = ('applicant__username', 'applicant__first_name', 'applicant__last_name')
    readonly_fields = ('applied_at',)
