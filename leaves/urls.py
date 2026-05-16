from django.urls import path
from . import views

urlpatterns = [
    path('leave-policy/', views.leave_policy, name='leave_policy'),
    path('apply-leave/', views.apply_leave, name='apply_leave'),
    path('my-leaves/', views.my_leaves, name='my_leaves'),
    path('coordinator-review/', views.coordinator_review, name='coordinator_review'),
    path('admin-leave-review/', views.admin_leave_review, name='admin_leave_review'),
]
