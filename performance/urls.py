from django.urls import path
from . import views

urlpatterns = [
    # Admin: Cycle management
    path('performance/', views.cycle_list, name='performance_cycle_list'),
    path('performance/cycle/new/', views.cycle_create, name='performance_cycle_create'),
    path('performance/cycle/<int:cycle_id>/', views.cycle_detail, name='performance_cycle_detail'),
    path('performance/cycle/<int:cycle_id>/activate/', views.cycle_activate, name='performance_cycle_activate'),
    path('performance/cycle/<int:cycle_id>/close/', views.cycle_close, name='performance_cycle_close'),

    # Admin: KPI builder
    path('performance/cycle/<int:cycle_id>/section/add/', views.kpi_section_add, name='performance_section_add'),
    path('performance/section/<int:section_id>/delete/', views.kpi_section_delete, name='performance_section_delete'),
    path('performance/section/<int:section_id>/kpi/add/', views.kpi_add, name='performance_kpi_add'),
    path('performance/kpi/<int:kpi_id>/delete/', views.kpi_delete, name='performance_kpi_delete'),

    # Admin: Evaluate
    path('performance/cycle/<int:cycle_id>/evaluate/<int:staff_id>/', views.evaluate_staff, name='performance_evaluate'),

    # Reports (admin + staff self)
    path('performance/cycle/<int:cycle_id>/report/<int:staff_id>/', views.report_html, name='performance_report_html'),
    path('performance/cycle/<int:cycle_id>/report/<int:staff_id>/pdf/', views.report_pdf, name='performance_report_pdf'),

    # Staff: my evaluations
    path('performance/my/', views.my_evaluations, name='performance_my_evaluations'),
]
