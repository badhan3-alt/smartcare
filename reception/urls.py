from django.urls import path

from . import views

app_name = 'reception'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('', views.dashboard_view, name='dashboard'),
    path('appointments/', views.appointments_view, name='appointments'),
    path('waiting/', views.waiting_view, name='waiting'),
    path('completed/', views.completed_view, name='completed'),
    path('doctors/', views.doctors_view, name='doctors'),
    path('patients/', views.patient_search_view, name='patients'),
    path('patients/register/', views.register_patient_view, name='register_patient'),
    path('appointments/book/', views.book_appointment_view, name='book_appointment'),
    path('check-in/<int:appointment_id>/', views.checkin_view, name='checkin'),
    path('queue/<int:appointment_id>/<str:action>/', views.queue_action_view, name='queue_action'),
]
