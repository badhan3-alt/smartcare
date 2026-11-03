from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import (
    UserProfile, MedicalHistory, GENDER_CHOICES, BLOOD_GROUP_CHOICES,
)
from doctors.models import Department

class UserRegistrationForm(forms.ModelForm):
    ROLE_CHOICES = [
        ('patient', 'Patient'),
        ('doctor', 'Doctor / Specialist'),
        ('receptionist', 'Receptionist'),
        ('hospital', 'Hospital / Report Upload'),
    ]

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        initial='patient',
        widget=forms.Select(attrs={'class': 'form-select fw-bold', 'id': 'id_role'})
    )
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Create Password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}))
    
    # Profile fields
    phone = forms.CharField(max_length=20, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}))
    gender = forms.ChoiceField(choices=GENDER_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    blood_group = forms.ChoiceField(choices=[('', 'Select Blood Group')] + BLOOD_GROUP_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    address = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Address'}), required=False)

    # Organization fields are required only for the Hospital role.
    hospital_name = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Hospital name'}),
    )
    registration_number = forms.CharField(
        max_length=100, required=False, label='Hospital registration / license number',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Registration or license number'}),
    )
    hospital_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Full hospital address'}),
    )
    contact_person = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact person (optional)'}),
    )
    website = forms.URLField(
        required=False, label='Hospital website',
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com'}),
    )

    # Doctor-specific fields (used when role == 'doctor')
    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_department'}),
        empty_label="Select Department / Specialty"
    )
    qualification = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. MBBS, FCPS, MD', 'id': 'id_qualification'})
    )
    specialization = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Interventional Cardiologist', 'id': 'id_specialization'})
    )
    experience_years = forms.IntegerField(
        required=False,
        initial=5,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_experience_years'})
    )
    consultation_fee = forms.DecimalField(
        required=False,
        initial=500.00,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_consultation_fee'})
    )
    room_number = forms.CharField(
        required=False,
        initial='Room 101',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Room 101', 'id': 'id_room_number'})
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Choose Username'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        selected_role = self.data.get('role') if self.is_bound else self.initial.get('role', 'patient')
        is_hospital = selected_role == 'hospital'
        for name in ('first_name', 'last_name', 'gender'):
            self.fields[name].required = not is_hospital
        for name in ('hospital_name', 'registration_number', 'hospital_address'):
            self.fields[name].required = is_hospital
        if selected_role != 'doctor':
            for name in (
                'department', 'qualification', 'specialization', 'experience_years',
                'consultation_fee', 'room_number',
            ):
                self.fields[name].disabled = True
        if is_hospital:
            # Ignore stale personal fields when switching from another role.
            for name in ('first_name', 'last_name', 'gender', 'date_of_birth', 'blood_group', 'address'):
                self.fields[name].disabled = True
            self.fields['email'].label = 'Official email address'
            self.fields['phone'].label = 'Official phone number'
        else:
            for name in ('hospital_name', 'registration_number', 'hospital_address', 'contact_person', 'website'):
                self.fields[name].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('confirm_password')
        if p1 and p2 and p1 != p2:
            self.add_error('confirm_password', 'Passwords do not match.')
        if p1:
            candidate = User(
                username=cleaned_data.get('username', ''),
                email=cleaned_data.get('email', ''),
                first_name=cleaned_data.get('first_name', ''),
                last_name=cleaned_data.get('last_name', ''),
            )
            try:
                validate_password(p1, candidate)
            except ValidationError as error:
                self.add_error('password', error)

        role = cleaned_data.get('role')
        if role == 'doctor':
            if not cleaned_data.get('department'):
                self.add_error('department', 'Department is required for Doctor registration.')
            if not cleaned_data.get('qualification'):
                self.add_error('qualification', 'Medical qualification is required for Doctor registration.')
            if not cleaned_data.get('specialization'):
                self.add_error('specialization', 'Specialization is required for Doctor registration.')

        return cleaned_data

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('An account with these details already exists.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('An account with these details already exists.')
        return email


class MedicalHistoryForm(forms.ModelForm):
    class Meta:
        model = MedicalHistory
        fields = [
            'allergies', 'current_medications', 'past_conditions',
            'past_surgeries', 'family_history',
        ]
        widgets = {
            field: forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
            }) for field in fields
        }
