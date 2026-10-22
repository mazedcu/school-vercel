from django.urls import path
from . import views

urlpatterns = [
    path('timetable_gen/', views.timetable_gen, name='timetable_gen'),
    path('timetable_gen/slot_info/', views.timetable_slot_info, name='timetable_slot_info'),
    path('timetable_gen/save/', views.timetable_save_entry, name='timetable_save_entry'),
    path('timetable_gen/delete/', views.timetable_delete_entry, name='timetable_delete_entry'),
    path('view_timetable/', views.view_timetable, name='view_timetable'),
    path('my_timetable/', views.my_timetable, name='my_timetable'),
    path('download_timetable_pdf/<int:section_id>/', views.download_timetable_pdf, name='download_timetable_pdf'),
    path('download_teacher_timetable_pdf/', views.download_teacher_timetable_pdf, name='download_teacher_timetable_pdf'),
]
