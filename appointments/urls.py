from django.urls import path
from . import views

app_name = 'appointments'

urlpatterns = [
    path('reception/', views.reception_dashboard_view, name='reception_dashboard'),
    path('reception/patients/', views.reception_patient_search_view, name='reception_patients'),
    path('reception/patients/register/', views.reception_register_patient_view, name='reception_register_patient'),
    path('reception/appointments/book/', views.reception_book_appointment_view, name='reception_book_appointment'),
    path('reception/check-in/<int:appointment_id>/', views.reception_checkin_view, name='reception_checkin'),
    path('reception/queue/<int:appointment_id>/<str:action>/', views.reception_queue_action_view, name='reception_queue_action'),
    path('dashboard/', views.patient_dashboard_view, name='patient_dashboard'),
    path('book/', views.book_appointment_view, name='book'),
    path('payment/<int:appointment_id>/', views.payment_view, name='payment'),
    path('queue/<int:appointment_id>/', views.queue_tracker_view, name='queue_tracker'),
    path('cancel/<int:appointment_id>/', views.cancel_appointment_view, name='cancel'),
    path('reschedule/<int:appointment_id>/', views.reschedule_appointment_view, name='reschedule'),
    path('feedback/<int:appointment_id>/', views.submit_feedback_view, name='feedback'),
    path('waitlist/', views.join_waitlist_view, name='waitlist'),
    path('prescription/<int:appointment_id>/pdf/', views.prescription_pdf_view, name='prescription_pdf'),
    path('invoice/<int:appointment_id>/pdf/', views.invoice_pdf_view, name='invoice_pdf'),
    path('telemedicine/<int:appointment_id>/', views.telemedicine_view, name='telemedicine'),
    path('api/queue-status/<int:appointment_id>/', views.api_queue_status, name='api_queue_status'),
]
