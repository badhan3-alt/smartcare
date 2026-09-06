from django.urls import path
from . import views

app_name = 'appointments'

urlpatterns = [
    path('dashboard/', views.patient_dashboard_view, name='patient_dashboard'),
    path('book/', views.book_appointment_view, name='book'),
    path('payment/<int:appointment_id>/', views.payment_view, name='payment'),
    path('queue/<int:appointment_id>/', views.queue_tracker_view, name='queue_tracker'),
    path('cancel/<int:appointment_id>/', views.cancel_appointment_view, name='cancel'),
    path('reschedule/<int:appointment_id>/', views.reschedule_appointment_view, name='reschedule'),
    path('feedback/<int:appointment_id>/', views.submit_feedback_view, name='feedback'),
    path('api/queue-status/<int:appointment_id>/', views.api_queue_status, name='api_queue_status'),
]

