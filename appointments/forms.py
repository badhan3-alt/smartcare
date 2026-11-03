import datetime
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from .models import (
    Appointment, PatientFeedback, Payment, Waitlist, PAYMENT_METHOD_CHOICES,
)
from doctors.models import DoctorProfile
from accounts.models import GENDER_CHOICES


class ReceptionPatientRegistrationForm(forms.Form):
    username = User._meta.get_field('username').formfield()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField()
    phone = forms.RegexField(regex=r'^\+?[0-9 ()-]{7,20}$', max_length=20)
    gender = forms.ChoiceField(choices=GENDER_CHOICES, initial='M')
    date_of_birth = forms.DateField(required=False)
    address = forms.CharField(max_length=2000, required=False)
    password = forms.CharField(max_length=128, required=False)

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('That username is already in use.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('That email is already registered.')
        return email

    def clean_date_of_birth(self):
        date = self.cleaned_data['date_of_birth']
        if date and date > timezone.localdate():
            raise ValidationError('Date of birth cannot be in the future.')
        return date

    def clean(self):
        data = super().clean()
        if data.get('password'):
            try:
                validate_password(data['password'], User(
                    username=data.get('username', ''), email=data.get('email', ''),
                    first_name=data.get('first_name', ''), last_name=data.get('last_name', ''),
                ))
            except ValidationError as error:
                self.add_error('password', error)
        return data


def validate_appointment_slot(doctor, appointment_date, appointment_time, exclude_id=None):
    if not doctor.is_available or not doctor.user.is_active or getattr(getattr(doctor.user, 'profile', None), 'role', None) != 'doctor':
        raise ValidationError('This doctor is not available for booking.')
    schedule = doctor.schedules.filter(day_of_week=appointment_date.weekday(), is_active=True).first()
    if not schedule or schedule.slot_duration_minutes <= 0:
        raise ValidationError('This doctor is not available on the selected date.')
    if appointment_date < timezone.localdate() or (
        appointment_date == timezone.localdate() and appointment_time <= timezone.localtime().time()
    ):
        raise ValidationError('Choose a future appointment time.')
    start_minutes = schedule.start_time.hour * 60 + schedule.start_time.minute
    selected_minutes = appointment_time.hour * 60 + appointment_time.minute
    end_minutes = schedule.end_time.hour * 60 + schedule.end_time.minute
    if (
        appointment_time.second or appointment_time.microsecond
        or selected_minutes < start_minutes
        or selected_minutes + schedule.slot_duration_minutes > end_minutes
        or (selected_minutes - start_minutes) % schedule.slot_duration_minutes
    ):
        raise ValidationError('Choose an available time from the doctor\'s schedule.')
    existing = Appointment.objects.filter(
        doctor=doctor, appointment_date=appointment_date, appointment_time=appointment_time,
        status__in=['scheduled', 'waiting', 'in_consultation'],
    )
    if exclude_id:
        existing = existing.exclude(pk=exclude_id)
    if existing.exists():
        raise ValidationError('This time has just been booked. Please choose another slot.')

class AppointmentBookingForm(forms.ModelForm):
    doctor = forms.ModelChoiceField(
        queryset=DoctorProfile.objects.filter(is_available=True, user__is_active=True, user__profile__role='doctor'),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_doctor'}),
        empty_label="Select Doctor"
    )
    appointment_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'id': 'id_appointment_date'
        })
    )
    appointment_time = forms.TimeField(
        widget=forms.TimeInput(attrs={
            'class': 'form-control',
            'type': 'time',
            'value': '10:00',
            'id': 'id_appointment_time'
        })
    )

    class Meta:
        model = Appointment
        fields = [
            'doctor', 'appointment_date', 'appointment_time',
            'visit_type', 'symptom_severity', 'has_chronic_condition',
            'primary_symptom', 'patient_notes'
        ]
        widgets = {
            'visit_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_visit_type'}),
            'symptom_severity': forms.Select(attrs={'class': 'form-select', 'id': 'id_symptom_severity'}),
            'has_chronic_condition': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_has_chronic_condition'}),
            'primary_symptom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Chest discomfort, persistent headache, fever', 'id': 'id_primary_symptom'}),
            'patient_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe your symptoms, previous treatments, or any specific concerns...'}),
        }

    def clean_appointment_date(self):
        appt_date = self.cleaned_data.get('appointment_date')
        if appt_date and appt_date < datetime.date.today():
            raise forms.ValidationError("Appointment date cannot be in the past.")
        return appt_date

    def clean(self):
        cleaned_data = super().clean()
        doctor = cleaned_data.get('doctor')
        appointment_date = cleaned_data.get('appointment_date')
        appointment_time = cleaned_data.get('appointment_time')

        if not doctor or not appointment_date or not appointment_time:
            return cleaned_data

        try:
            validate_appointment_slot(doctor, appointment_date, appointment_time)
        except ValidationError as error:
            self.add_error('appointment_time', error)
        return cleaned_data


class RescheduleAppointmentForm(forms.Form):
    appointment_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    appointment_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'})
    )

    def __init__(self, *args, appointment, **kwargs):
        super().__init__(*args, **kwargs)
        self.appointment = appointment

    def clean(self):
        cleaned_data = super().clean()
        appointment_date = cleaned_data.get('appointment_date')
        appointment_time = cleaned_data.get('appointment_time')
        if appointment_date and appointment_time:
            try:
                validate_appointment_slot(
                    self.appointment.doctor, appointment_date, appointment_time,
                    exclude_id=self.appointment.pk,
                )
            except ValidationError as error:
                self.add_error('appointment_time', error)
        return cleaned_data


class CancelAppointmentForm(forms.Form):
    cancellation_reason = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Reason for cancellation...'}),
        required=True
    )

class PatientFeedbackForm(forms.ModelForm):
    class Meta:
        model = PatientFeedback
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.Select(attrs={'class': 'form-select'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Share your experience with the doctor and service...'}),
        }

class PaymentForm(forms.Form):
    payment_method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='bkash'
    )
    transaction_id = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your transaction ID (for mobile banking / card)',
            'id': 'id_transaction_id'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get('payment_method')
        txn_id = cleaned_data.get('transaction_id')
        if method != 'cash' and not txn_id:
            self.add_error('transaction_id', 'Transaction ID is required for online payments.')
        return cleaned_data


class WaitlistForm(forms.ModelForm):
    class Meta:
        model = Waitlist
        fields = ['doctor', 'preferred_date']
        widgets = {
            'doctor': forms.Select(attrs={'class': 'form-select'}),
            'preferred_date': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['doctor'].queryset = DoctorProfile.objects.filter(
            is_available=True, user__is_active=True, user__profile__role='doctor',
        ).select_related('department')

    def clean_preferred_date(self):
        preferred_date = self.cleaned_data['preferred_date']
        if preferred_date < datetime.date.today():
            raise forms.ValidationError("Waitlist date cannot be in the past.")
        return preferred_date
