import datetime
from django.db import models
from django.contrib.auth.models import User

DAYS_OF_WEEK = [
    (0, 'Monday'),
    (1, 'Tuesday'),
    (2, 'Wednesday'),
    (3, 'Thursday'),
    (4, 'Friday'),
    (5, 'Saturday'),
    (6, 'Sunday'),
]

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='bi-heart-pulse')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='doctor_profile')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='doctors')
    qualification = models.CharField(max_length=200, help_text="e.g. MBBS, FCPS (Cardiology)")
    specialization = models.CharField(max_length=200, help_text="e.g. Interventional Cardiologist")
    experience_years = models.PositiveIntegerField(default=5)
    consultation_fee = models.DecimalField(max_digits=8, decimal_places=2, default=500.00)
    room_number = models.CharField(max_length=50, default='Room 101')
    max_patients_per_day = models.PositiveIntegerField(default=30)
    bio = models.TextField(blank=True)
    is_available = models.BooleanField(default=True)

    @property
    def full_name(self):
        name = self.user.get_full_name()
        if name:
            return f"Dr. {name}" if not name.lower().startswith("dr.") else name
        return f"Dr. {self.user.username}"

    @property
    def average_rating(self):
        feedbacks = self.appointments.filter(feedback__isnull=False)
        from appointments.models import PatientFeedback
        fb_qs = PatientFeedback.objects.filter(appointment__doctor=self)
        if fb_qs.exists():
            return round(fb_qs.aggregate(models.Avg('rating'))['rating__avg'] or 5.0, 1)
        return 5.0

    @property
    def total_reviews(self):
        from appointments.models import PatientFeedback
        return PatientFeedback.objects.filter(appointment__doctor=self).count()

    def __str__(self):
        return f"{self.full_name} - {self.department.name}"

class DoctorSchedule(models.Model):
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField(default=datetime.time(9, 0))
    end_time = models.TimeField(default=datetime.time(17, 0))
    slot_duration_minutes = models.PositiveIntegerField(default=20)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('doctor', 'day_of_week')
        ordering = ['day_of_week', 'start_time']

    def __str__(self):
        return f"{self.doctor.full_name} | {self.get_day_of_week_display()} ({self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')})"

