from django.urls import path
from . import views

urlpatterns = [
    path('idcards/', views.idcard_dashboard, name='idcard_dashboard'),
    path('idcards/student/<int:student_id>/pdf/', views.student_id_card_pdf, name='student_id_card_pdf'),
    path('idcards/teacher/<int:teacher_id>/pdf/', views.teacher_id_card_pdf, name='teacher_id_card_pdf'),
    path('idcards/section/<int:section_id>/pdf/', views.bulk_student_id_cards, name='bulk_student_id_cards'),
]
