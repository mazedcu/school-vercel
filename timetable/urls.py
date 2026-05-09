from django.urls import path
from . import views

urlpatterns = [
    path('timetable_gen/', views.timetable_gen, name='timetable_gen'),
    path('view_timetable/', views.view_timetable, name='view_timetable'),
    path('my_timetable/', views.my_timetable, name='my_timetable'),
    path('download_timetable_pdf/<int:section_id>/', views.download_timetable_pdf, name='download_timetable_pdf'),
    path('download_teacher_timetable_pdf/', views.download_teacher_timetable_pdf, name='download_teacher_timetable_pdf'),
]
