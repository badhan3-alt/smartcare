from django import forms

class DoctorConsultationForm(forms.Form):
    actual_duration_minutes = forms.FloatField(
        min_value=0.5,
        max_value=480,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'placeholder': 'Minutes'}),
        required=True
    )
    doctor_notes = forms.CharField(
        max_length=10000,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Clinical observations, examination findings, diagnosis...'}),
        required=False
    )
    prescription = forms.CharField(
        max_length=10000,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Medicines, dosage, dietary advice, follow-up tests...'}),
        required=False
    )

