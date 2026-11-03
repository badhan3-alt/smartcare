from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import F, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from appointments.models import Appointment
from .models import MedicalReport, UserProfile
from .report_forms import CONSULTATION_STATUSES, MedicalReportForm


def _has_role(user, role):
    profile = getattr(user, 'profile', None)
    return profile is not None and profile.role == role


def _require_hospital(user):
    if not _has_role(user, 'hospital'):
        raise PermissionDenied('Hospital access is required to upload reports.')


def _doctor_reports(user):
    # Recheck the consultation's patient and status on every request.
    if not _has_role(user, 'doctor') or not hasattr(user, 'doctor_profile'):
        return MedicalReport.objects.none()
    return MedicalReport.objects.filter(
        consultation__doctor__user=user,
        consultation__status__in=CONSULTATION_STATUSES,
        patient_id=F('consultation__patient_id'),
    )


def _report_details(reports):
    return reports.select_related(
        'patient', 'uploaded_by', 'consultation__doctor__user',
    )


@login_required
@require_GET
def hospital_dashboard_view(request):
    _require_hospital(request.user)
    query = request.GET.get('q', '').strip()[:100]
    patients = UserProfile.objects.filter(
        role='patient', user__is_active=True,
    ).select_related('user').order_by('user__first_name', 'user__last_name', 'user_id')
    if query:
        search = (
            Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query)
            | Q(user__username__icontains=query) | Q(phone__icontains=query)
        )
        patient_number = query.upper().removeprefix('SC-')
        if patient_number.isascii() and patient_number.isdigit() and len(patient_number) <= 18:
            search |= Q(user_id=int(patient_number))
        patients = patients.filter(search)
    return render(request, 'accounts/hospital_dashboard.html', {
        'patients': patients[:100], 'query': query,
    })


@login_required
@require_GET
def reports_view(request):
    if not _has_role(request.user, 'patient'):
        raise PermissionDenied('Patient access is required.')
    return render(request, 'accounts/reports.html', {
        'patient': request.user,
        'reports': _report_details(request.user.medical_reports.all()),
        'can_manage': False, 'can_download': True,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def patient_reports_view(request, patient_id):
    _require_hospital(request.user)
    patient = get_object_or_404(
        User, pk=patient_id, profile__role='patient', is_active=True,
    )
    form = MedicalReportForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
        patient=patient,
    )
    if request.method == 'POST' and form.is_valid():
        report = form.save(commit=False)
        report.patient = patient
        report.uploaded_by = request.user
        report.original_filename = form.cleaned_data['file'].name
        report.save()
        messages.success(request, 'PDF report uploaded for the patient and their treating doctor.')
        return redirect('accounts:patient_reports', patient_id=patient.pk)
    return render(request, 'accounts/reports.html', {
        'patient': patient,
        'reports': _report_details(patient.medical_reports.filter(uploaded_by=request.user)),
        'can_manage': True, 'can_download': False, 'form': form,
    })


@login_required
@require_GET
def doctor_reports_view(request):
    if not _has_role(request.user, 'doctor') or not hasattr(request.user, 'doctor_profile'):
        raise PermissionDenied('Doctor access is required.')
    return render(request, 'accounts/reports.html', {
        'patient': None,
        'reports': _report_details(_doctor_reports(request.user)),
        'can_manage': False, 'can_download': True, 'is_doctor': True,
    })


@login_required
@require_GET
def consultation_reports_view(request, appointment_id):
    if not _has_role(request.user, 'doctor') or not hasattr(request.user, 'doctor_profile'):
        raise PermissionDenied('Doctor access is required.')
    consultation = get_object_or_404(
        Appointment.objects.select_related('patient', 'doctor__user'),
        pk=appointment_id, doctor__user=request.user,
        status__in=CONSULTATION_STATUSES,
    )
    return render(request, 'accounts/reports.html', {
        'patient': consultation.patient, 'consultation': consultation,
        'reports': _report_details(_doctor_reports(request.user).filter(consultation=consultation)),
        'can_manage': False, 'can_download': True, 'is_doctor': True,
    })


@login_required
@require_GET
def report_download_view(request, report_id):
    if _has_role(request.user, 'patient'):
        reports = MedicalReport.objects.filter(patient=request.user)
    else:
        reports = _doctor_reports(request.user)
    report = get_object_or_404(reports, pk=report_id)
    try:
        report_file = report.file.open('rb')
    except FileNotFoundError:
        raise Http404('The report file is no longer available.')
    response = FileResponse(
        report_file, as_attachment=request.GET.get('view') != '1', filename=report.original_filename,
        content_type='application/pdf',
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    # User-supplied PDFs may contain active content. Keep inline previews isolated
    # from the application's origin, cookies, scripts, forms, and network access.
    response['Content-Security-Policy'] = "sandbox; default-src 'none'; base-uri 'none'; form-action 'none'"
    response['Referrer-Policy'] = 'no-referrer'
    response['Cross-Origin-Resource-Policy'] = 'same-origin'
    return response


@login_required
@require_POST
def report_delete_view(request, report_id):
    _require_hospital(request.user)
    report = get_object_or_404(MedicalReport, pk=report_id, uploaded_by=request.user)
    patient_id = report.patient_id
    report.delete()
    messages.success(request, 'The report has been deleted.')
    return redirect('accounts:patient_reports', patient_id=patient_id)
