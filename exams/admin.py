from django.contrib import admin
from .models import AssessmentType, SubjectWeighting, WeightingComponent, AssessmentRecord, StudentScore, GradeSetting, SubjectComment

class WeightingComponentInline(admin.TabularInline):
    model = WeightingComponent
    extra = 1

class SubjectWeightingAdmin(admin.ModelAdmin):
    inlines = [WeightingComponentInline]

admin.site.register(AssessmentType)
admin.site.register(SubjectWeighting, SubjectWeightingAdmin)
admin.site.register(AssessmentRecord)
admin.site.register(StudentScore)
admin.site.register(GradeSetting)
admin.site.register(SubjectComment)
