import datetime
from django import forms
from .models import (
    Appointment, PatientFeedback, Payment, Waitlist, PAYMENT_METHOD_CHOICES,
)
from doctors.models import DoctorProfile

class AppointmentBookingForm(forms.ModelForm):
    doctor = forms.ModelChoiceField(
        queryset=DoctorProfile.objects.filter(is_available=True),
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

        schedule = doctor.schedules.filter(
            day_of_week=appointment_date.weekday(),
            is_active=True,
        ).first()
        if not doctor.is_available or not schedule:
            self.add_error(
                'appointment_date',
                'This doctor is not available on the selected date.',
            )
            return cleaned_data

        if not schedule.start_time <= appointment_time < schedule.end_time:
            self.add_error(
                'appointment_time',
                f'Choose a time between {schedule.start_time.strftime("%I:%M %p")} '
                f'and {schedule.end_time.strftime("%I:%M %p")}.',
            )
            return cleaned_data

        start_minutes = schedule.start_time.hour * 60 + schedule.start_time.minute
        selected_minutes = appointment_time.hour * 60 + appointment_time.minute
        if (selected_minutes - start_minutes) % schedule.slot_duration_minutes:
            self.add_error(
                'appointment_time',
                f'Choose one of the {schedule.slot_duration_minutes}-minute slots shown below.',
            )
            return cleaned_data

        if appointment_date == datetime.date.today() and appointment_time <= datetime.datetime.now().time():
            self.add_error('appointment_time', 'Choose a future time for today.')
            return cleaned_data

        if Appointment.objects.filter(
            doctor=doctor,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            status__in=['scheduled', 'waiting', 'in_consultation'],
        ).exists():
            self.add_error(
                'appointment_time',
                'This time has just been booked. Please choose another slot.',
            )

        return cleaned_data

class RescheduleAppointmentForm(forms.Form):
    appointment_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    appointment_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'})
    )

    def clean_appointment_date(self):
        appt_date = self.cleaned_data.get('appointment_date')
        if appt_date and appt_date < datetime.date.today():
            raise forms.ValidationError("Appointment date cannot be in the past.")
        return appt_date

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
            is_available=True
        ).select_related('department')

    def clean_preferred_date(self):
        preferred_date = self.cleaned_data['preferred_date']
        if preferred_date < datetime.date.today():
            raise forms.ValidationError("Waitlist date cannot be in the past.")
        return preferred_date
