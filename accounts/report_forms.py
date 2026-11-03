from django import forms
from appointments.models import Appointment

from .models import MedicalReport


CONSULTATION_STATUSES = ('in_consultation', 'completed')


class MedicalReportForm(forms.ModelForm):
    consultation = forms.ModelChoiceField(
        queryset=Appointment.objects.none(),
        label='Consultation / treating doctor',
        help_text='Only the doctor on this consultation can access this report with the patient.',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, patient, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['consultation'].queryset = Appointment.objects.filter(
            patient=patient, status__in=CONSULTATION_STATUSES,
        ).select_related('doctor', 'doctor__user').order_by('-appointment_date', '-pk')

    class Meta:
        model = MedicalReport
        fields = ['consultation', 'title', 'report_date', 'notes', 'file']
        labels = {'file': 'PDF report'}
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g. Complete blood count',
            }),
            'report_date': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'file': forms.FileInput(attrs={
                'class': 'form-control', 'accept': '.pdf,application/pdf',
            }),
        }
