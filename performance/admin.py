from django.contrib import admin
from .models import PerformanceCycle, KPISection, KPI, StaffEvaluation, KPIScore


class KPIInline(admin.TabularInline):
    model = KPI
    extra = 0


class KPISectionInline(admin.TabularInline):
    model = KPISection
    extra = 0


@admin.register(PerformanceCycle)
class PerformanceCycleAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'status', 'created_by']
    list_filter = ['status']
    inlines = [KPISectionInline]


@admin.register(KPISection)
class KPISectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'role_type', 'cycle', 'order']
    list_filter = ['role_type', 'cycle']
    inlines = [KPIInline]


@admin.register(KPI)
class KPIAdmin(admin.ModelAdmin):
    list_display = ['title', 'section', 'max_weight', 'data_source']
    list_filter = ['section__role_type', 'section__cycle']


class KPIScoreInline(admin.TabularInline):
    model = KPIScore
    extra = 0
    readonly_fields = ['kpi']


@admin.register(StaffEvaluation)
class StaffEvaluationAdmin(admin.ModelAdmin):
    list_display = ['staff', 'cycle', 'role_type', 'status', 'final_score', 'submitted_at']
    list_filter = ['cycle', 'status', 'role_type']
    inlines = [KPIScoreInline]
    readonly_fields = ['final_score', 'submitted_at']
