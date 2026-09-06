from django.db import models
from django.contrib.auth.models import User
from doctors.models import DoctorProfile

VISIT_TYPE_CHOICES = [
    ('first_visit', 'First Visit'),
    ('follow_up', 'Follow-up Consultation'),
    ('routine_checkup', 'Routine Checkup'),
    ('urgent', 'Urgent / Acute Care'),
]

SEVERITY_CHOICES = [
    ('mild', 'Mild (Standard examination)'),
    ('moderate', 'Moderate (Requires detailed diagnosis)'),
    ('severe', 'Severe (Complex or acute symptoms)'),
]

APPOINTMENT_STATUS_CHOICES = [
    ('scheduled', 'Scheduled'),
    ('waiting', 'Waiting in Clinic'),
    ('in_consultation', 'In Consultation'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
    ('no_show', 'No-Show'),
]

class Appointment(models.Model):
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='patient_appointments')
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name='appointments')
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    token_number = models.PositiveIntegerField()
    
    # Clinical factors used by ML duration model
    visit_type = models.CharField(max_length=30, choices=VISIT_TYPE_CHOICES, default='first_visit')
    symptom_severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='mild')
    has_chronic_condition = models.BooleanField(default=False)
    primary_symptom = models.CharField(max_length=255, blank=True)
    patient_notes = models.TextField(blank=True, help_text="Specific complaints or queries")

    # Workflow & Queue Status
    status = models.CharField(max_length=20, choices=APPOINTMENT_STATUS_CHOICES, default='scheduled')
    
    # ML & Actual Metrics
    predicted_duration_minutes = models.FloatField(default=20.0, help_text="Predicted by SmartCare ML Regressor")
    actual_duration_minutes = models.FloatField(null=True, blank=True, help_text="Recorded after consultation")
    
    # Consultation outcome
    consultation_started_at = models.DateTimeField(null=True, blank=True)
    consultation_ended_at = models.DateTimeField(null=True, blank=True)
    doctor_notes = models.TextField(blank=True)
    prescription = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)

    # Reminder tracking — set True after each reminder email is sent
    reminder_24h_sent = models.BooleanField(default=False)
    reminder_2h_sent = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['appointment_date', 'token_number']
        unique_together = ('doctor', 'appointment_date', 'token_number')

    def __str__(self):
        return f"#{self.token_number} - {self.patient.get_full_name() or self.patient.username} with {self.doctor.full_name} on {self.appointment_date}"

class PatientFeedback(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='feedback')
    rating = models.IntegerField(choices=[(1, '1 Star'), (2, '2 Stars'), (3, '3 Stars'), (4, '4 Stars'), (5, '5 Stars')], default=5)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback for {self.appointment}: {self.rating} Stars"


PAYMENT_METHOD_CHOICES = [
    ('bkash', 'bKash'),
    ('nagad', 'Nagad'),
    ('rocket', 'Rocket'),
    ('card', 'Credit/Debit Card'),
    ('cash', 'Cash at Counter'),
]

PAYMENT_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('completed', 'Completed'),
    ('failed', 'Failed'),
    ('refunded', 'Refunded'),
]

class Payment(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='payment')
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='bkash')
    transaction_id = models.CharField(max_length=100, blank=True, help_text="Mobile banking or card transaction ID")
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment ৳{self.amount} by {self.patient.get_full_name() or self.patient.username} - {self.get_status_display()}"


WAITLIST_STATUS_CHOICES = [
    ('waiting', 'Waiting'),
    ('promoted', 'Promoted to Appointment'),
    ('expired', 'Expired'),
    ('cancelled', 'Cancelled by Patient'),
]

class Waitlist(models.Model):
    """Holds patients who want a slot on a fully-booked day."""
    patient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='waitlist_entries'
    )
    doctor = models.ForeignKey(
        DoctorProfile, on_delete=models.CASCADE, related_name='waitlist'
    )
    preferred_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=WAITLIST_STATUS_CHOICES, default='waiting'
    )
    # Unique token used for the one-click confirmation email link
    confirm_token = models.CharField(max_length=64, blank=True, unique=True)
    promoted_appointment = models.OneToOneField(
        Appointment, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='waitlist_source'
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['preferred_date', 'requested_at']
        unique_together = ('patient', 'doctor', 'preferred_date')

    def __str__(self):
        return (
            f"Waitlist: {self.patient.get_full_name() or self.patient.username} "
            f"→ {self.doctor.full_name} on {self.preferred_date} [{self.get_status_display()}]"
        )
