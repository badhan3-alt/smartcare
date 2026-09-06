import datetime
from django.db import models
from django.contrib.auth.models import User

ROLE_CHOICES = [
    ('patient', 'Patient'),
    ('doctor', 'Doctor'),
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
    phone = models.CharField(max_length=20, blank=False)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='M')
    date_of_birth = models.DateField(null=True, blank=True)
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def calculated_age(self):
        if self.date_of_birth:
            today = datetime.date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return 32

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"


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

