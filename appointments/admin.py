from django.contrib import admin
from .models import Appointment, PatientFeedback, Payment

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('token_number', 'appointment_date', 'patient', 'doctor', 'status', 'predicted_duration_minutes', 'actual_duration_minutes')
    list_filter = ('status', 'appointment_date', 'doctor__department', 'visit_type')
    search_fields = ('patient__username', 'patient__first_name', 'patient__last_name', 'doctor__user__last_name')
    date_hierarchy = 'appointment_date'

@admin.register(PatientFeedback)
class PatientFeedbackAdmin(admin.ModelAdmin):
    list_display = ('appointment', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'appointment', 'amount', 'payment_method', 'status', 'transaction_id', 'paid_at')
    list_filter = ('status', 'payment_method', 'paid_at')
    search_fields = ('patient__username', 'patient__first_name', 'transaction_id')
    date_hierarchy = 'paid_at'
