from django import forms
from django.contrib.auth.models import User
from .models import UserProfile, GENDER_CHOICES, BLOOD_GROUP_CHOICES
from doctors.models import Department

class UserRegistrationForm(forms.ModelForm):
    ROLE_CHOICES = [
        ('patient', 'Patient'),
        ('doctor', 'Doctor / Specialist'),
        # ('admin', 'Administrator'),  # Admin registration disabled
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

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('confirm_password')
        if p1 and p2 and p1 != p2:
            self.add_error('confirm_password', 'Passwords do not match.')

        role = cleaned_data.get('role')
        if role == 'doctor':
            if not cleaned_data.get('department'):
                self.add_error('department', 'Department is required for Doctor registration.')
            if not cleaned_data.get('qualification'):
                self.add_error('qualification', 'Medical qualification is required for Doctor registration.')
            if not cleaned_data.get('specialization'):
                self.add_error('specialization', 'Specialization is required for Doctor registration.')

        return cleaned_data

