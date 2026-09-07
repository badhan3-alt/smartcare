"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""


from django.contrib import admin
from django.urls import path, include
import core.views as core_views
import accounts.views as account_views
import doctors.views as doctor_views
import appointments.views as appointment_views
import ml_engine.views as ml_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Core
    path("", core_views.home_view, name="home"),
    path("core/", include("core.urls")),

    # Accounts & Authentication
    path("accounts/", include("accounts.urls")),
    path("login/", account_views.login_view, name="login"),
    path("register/", account_views.register_view, name="register"),
    path("verify-registration/", account_views.verify_registration_view, name="verify_registration"),
    path("forgot-password/", account_views.forgot_password_view, name="forgot_password"),
    path("reset-password/", account_views.reset_password_view, name="reset_password"),
    path("logout/", account_views.logout_view, name="logout"),
    path("dashboard/", account_views.dashboard_view, name="dashboard"),

    # Doctors
    path("doctors/", include("doctors.urls")),
    path("doctors-directory/", doctor_views.doctor_list_view, name="doctor_list"),
    path("doctor/<int:doctor_id>/", doctor_views.doctor_detail_view, name="doctor_detail"),
    path("doctor/dashboard/", doctor_views.doctor_dashboard_view, name="doctor_dashboard"),
    path("doctor/console/", doctor_views.doctor_queue_console_view, name="doctor_queue_console"),
    path("doctor/schedule/", doctor_views.doctor_schedule_view, name="doctor_schedule"),

    # Appointments & Queue Tracking
    path("appointments/", include("appointments.urls")),
    path("reception/", include("reception.urls")),
    path("patient/dashboard/", appointment_views.patient_dashboard_view, name="patient_dashboard"),
    path("patient/book/", appointment_views.book_appointment_view, name="book_appointment"),
    path("queue/<int:appointment_id>/", appointment_views.queue_tracker_view, name="queue_tracker"),

    # ML Engine & Analytics
    path("analytics/", include("ml_engine.urls")),
    path("admin-portal/dashboard/", ml_views.admin_dashboard_view, name="admin_dashboard"),
    path("admin-portal/receptionist-requests/", ml_views.receptionist_requests_view, name="admin_receptionist_requests"),
    path("admin-portal/receptionist-requests/<int:user_id>/approve/", ml_views.approve_receptionist_view, name="approve_receptionist"),
    path("admin-portal/receptionist-requests/<int:user_id>/reject/", ml_views.reject_receptionist_view, name="reject_receptionist"),
    path("admin-portal/doctor-requests/", ml_views.doctor_requests_view, name="admin_doctor_requests"),
    path("admin-portal/doctor-requests/<int:user_id>/approve/", ml_views.approve_doctor_view, name="approve_doctor"),
    path("admin-portal/doctor-requests/<int:user_id>/reject/", ml_views.reject_doctor_view, name="reject_doctor"),
    path("admin-portal/patients/", ml_views.admin_patient_list_view, name="admin_patient_list"),
    path("admin-portal/appointments/", ml_views.admin_appointment_list_view, name="admin_appointment_list"),
    path("admin-portal/queue/", ml_views.admin_appointment_list_view, name="admin_queue"),
    path("admin-portal/demand-forecast/", ml_views.admin_demand_forecast_view, name="admin_demand_forecast"),
    path("api/predict-duration/", ml_views.api_predict_duration, name="api_predict_duration"),

    # Legacy Insurance Predictor
    path("insurance/", include("predictor.urls")),
    path("insurance/api/", include("predictor.api_urls")),
]

from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()