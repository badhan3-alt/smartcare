import datetime
from django.db import models
from django.contrib.auth.models import User
from .report_files import PrivateReportStorage, report_upload_path, validate_report_file

ROLE_CHOICES = [
    ('patient', 'Patient'),
    ('doctor', 'Doctor'),
    ('receptionist', 'Receptionist'),
    ('hospital', 'Hospital'),
]

GENDER_CHOICES = [
    ('M', 'Male'),
    ('F', 'Female'),
    ('O', 'Other'),
]

BLOOD_GROUP_CHOICES = [
    ('A+', 'A+'),
    ('A-', 'A-'),
    ('B+', 'B+'),
    ('B-', 'B-'),
    ('AB+', 'AB+'),
    ('AB-', 'AB-'),
    ('O+', 'O+'),
    ('O-', 'O-'),
]

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='patient')
    email_verified = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=False)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='M')
    date_of_birth = models.DateField(null=True, blank=True)
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def display_name(self):
        if self.role == 'hospital':
            hospital = getattr(self.user, 'hospital_profile', None)
            if hospital is not None:
                return hospital.name
        return self.user.get_full_name() or self.user.username

    @property
    def calculated_age(self):
        if self.date_of_birth:
            today = datetime.date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return 32

    def __str__(self):
        return f"{self.display_name} ({self.get_role_display()})"


class HospitalProfile(models.Model):
    """Organization details for a hospital's report-upload account."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='hospital_profile',
        limit_choices_to={'profile__role': 'hospital'},
    )
    name = models.CharField(max_length=200)
    registration_number = models.CharField(max_length=100)
    contact_person = models.CharField(max_length=150, blank=True)
    website = models.URLField(blank=True)

    def __str__(self):
        return self.name


class MedicalHistory(models.Model):
    """Patient-owned longitudinal medical record."""
    patient = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='medical_history'
    )
    allergies = models.TextField(
        blank=True,
        help_text="List known drug, food, or environmental allergies"
    )
    current_medications = models.TextField(
        blank=True,
        help_text="Ongoing medications with dosage (e.g. Metformin 500mg twice daily)"
    )
    past_conditions = models.TextField(
        blank=True,
        help_text="Chronic or past diagnoses (e.g. Type 2 Diabetes, Hypertension)"
    )
    past_surgeries = models.TextField(
        blank=True,
        help_text="Previous surgeries or hospitalizations with approximate year"
    )
    family_history = models.TextField(
        blank=True,
        help_text="Significant hereditary conditions in immediate family"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Medical History — {self.patient.get_full_name() or self.patient.username}"


class MedicalReport(models.Model):
    """A hospital-uploaded report delivered to a specific patient."""

    patient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='medical_reports',
        limit_choices_to={'profile__role': 'patient'},
    )
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='uploaded_reports',
        editable=False,
    )
    consultation = models.ForeignKey(
        'appointments.Appointment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='medical_reports',
    )
    title = models.CharField(max_length=150)
    report_date = models.DateField(null=True, blank=True)
    notes = models.TextField(max_length=2000, blank=True)
    file = models.FileField(
        storage=PrivateReportStorage(), upload_to=report_upload_path,
        validators=[validate_report_file],
    )
    original_filename = models.CharField(max_length=255, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return f'{self.title} - {self.patient.get_full_name() or self.patient.username}'
