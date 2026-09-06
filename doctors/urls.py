from django.urls import path
from . import views

app_name = 'doctors'

urlpatterns = [
    path('', views.doctor_list_view, name='list'),
    path('<int:doctor_id>/', views.doctor_detail_view, name='detail'),
    path('dashboard/', views.doctor_dashboard_view, name='dashboard'),
    path('console/', views.doctor_queue_console_view, name='queue_console'),
    path('call/<int:appointment_id>/', views.doctor_call_patient_view, name='call_patient'),
    path('start/<int:appointment_id>/', views.doctor_start_consultation_view, name='start_consultation'),
    path('complete/<int:appointment_id>/', views.doctor_complete_consultation_view, name='complete_consultation'),
    path('no-show/<int:appointment_id>/', views.doctor_no_show_view, name='no_show'),
    path('schedule/', views.doctor_schedule_view, name='schedule'),
]

