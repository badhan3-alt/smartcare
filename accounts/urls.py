from django.urls import path
from . import views
from . import report_views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('verify-registration/', views.verify_registration_view, name='verify_registration'),
    path('login/', views.login_view, name='login'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('reset-password/', views.reset_password_view, name='reset_password'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('medical-history/', views.medical_history_view, name='medical_history'),
    path('reports/', report_views.reports_view, name='reports'),
    path('hospital/', report_views.hospital_dashboard_view, name='hospital_dashboard'),
    path('doctor/reports/', report_views.doctor_reports_view, name='doctor_reports'),
    path('consultations/<int:appointment_id>/reports/', report_views.consultation_reports_view, name='consultation_reports'),
    path('patients/<int:patient_id>/reports/', report_views.patient_reports_view, name='patient_reports'),
    path('reports/<int:report_id>/download/', report_views.report_download_view, name='report_download'),
    path('reports/<int:report_id>/delete/', report_views.report_delete_view, name='report_delete'),
]
