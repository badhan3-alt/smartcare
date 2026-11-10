import datetime

from django.shortcuts import render, redirect
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from doctors.models import Department, DoctorProfile
from appointments.models import Appointment
from accounts.models import UserProfile


def home_view(request):
    # Visiting a public page must not change an authenticated session.
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    departments = Department.objects.filter(is_active=True).annotate(
        doc_count=Count('doctors')
    )
    featured_doctors = DoctorProfile.objects.filter(is_available=True).select_related('user', 'department')[:6]
    
    total_doctors = DoctorProfile.objects.count()
    total_patients = UserProfile.objects.filter(role='patient').count()
    total_appointments = Appointment.objects.count()
    completed_appointments = Appointment.objects.filter(status='completed').count()
    
    context = {
        'departments': departments,
        'featured_doctors': featured_doctors,
        'stats': {
            'total_doctors': total_doctors,
            'total_patients': total_patients,
            'total_appointments': total_appointments,
            'completed_appointments': completed_appointments,
        }
    }
    return render(request, 'core/home.html', context)


def _suggestion_value(query, *values):
    normalized_query = query.casefold()
    return next(
        (value for value in values if value and normalized_query in value.casefold()),
        '',
    )


def _suggestion(label, value):
    return {'label': label, 'value': value}


@require_GET
def search_suggestions_view(request):
    kind = request.GET.get('type', '')
    query = request.GET.get('q', '').strip()[:100]
    allowed_types = {
        'doctors', 'doctor-patients', 'admin-patients',
        'admin-appointments', 'reception-patients', 'hospital-patients',
    }
    if kind not in allowed_types:
        return JsonResponse({'error': 'Unknown suggestion type.'}, status=400)
    if len(query) < 2:
        return JsonResponse({'results': []})

    user = request.user
    profile = getattr(user, 'profile', None) if user.is_authenticated else None
    role = getattr(profile, 'role', None)
    staff_types = {
        'doctor-patients': 'doctor',
        'admin-patients': 'admin',
        'admin-appointments': 'admin',
        'reception-patients': 'receptionist',
        'hospital-patients': 'hospital',
    }
    required_role = staff_types.get(kind)
    if required_role and (
        not user.is_authenticated
        or not user.is_active
        or (role != required_role and not (kind.startswith('admin-') and user.is_superuser))
    ):
        return JsonResponse({'error': 'You are not allowed to search these records.'}, status=403)

    results = []
    if kind == 'doctors':
        doctors = DoctorProfile.objects.filter(
            is_available=True,
            user__is_active=True,
            user__profile__role='doctor',
        ).select_related('user', 'department').filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(specialization__icontains=query)
            | Q(qualification__icontains=query)
            | Q(department__name__icontains=query)
        ).order_by('user__first_name', 'user__last_name')[:8]
        for doctor in doctors:
            name = doctor.user.get_full_name() or doctor.user.username
            value = _suggestion_value(
                query, doctor.user.first_name, doctor.user.last_name,
                doctor.specialization, doctor.qualification, doctor.department.name,
            )
            results.append(_suggestion(
                f'{name} — {doctor.specialization} · {doctor.department.name}',
                value,
            ))

    elif kind == 'doctor-patients':
        doctor = DoctorProfile.objects.filter(
            user=user, user__is_active=True, user__profile__role='doctor',
        ).first()
        if doctor is None:
            return JsonResponse({'error': 'Doctor access is required.'}, status=403)
        metric = request.GET.get('metric', '')
        if metric not in {'today', 'waiting', 'completed', 'workload'}:
            return JsonResponse({'error': 'Unknown patient list.'}, status=400)
        appointments = Appointment.objects.filter(
            doctor=doctor,
            appointment_date=datetime.date.today(),
        )
        if metric == 'waiting':
            appointments = appointments.filter(status__in=['scheduled', 'waiting'])
        elif metric == 'completed':
            appointments = appointments.filter(status='completed')
        elif metric == 'workload':
            appointments = appointments.filter(
                status__in=['scheduled', 'waiting', 'in_consultation'],
            )
        patient_filter = (
            Q(patient__first_name__icontains=query)
            | Q(patient__last_name__icontains=query)
            | Q(patient__username__icontains=query)
        )
        if query.isdigit():
            patient_filter |= Q(token_number=int(query))
        appointments = appointments.filter(patient_filter).select_related(
            'patient',
        ).order_by('token_number')[:30]
        seen_patients = set()
        for appointment in appointments:
            patient = appointment.patient
            if patient.pk in seen_patients:
                continue
            seen_patients.add(patient.pk)
            name = patient.get_full_name() or patient.username
            value = _suggestion_value(
                query, patient.first_name, patient.last_name, patient.username,
            )
            if not value and query.isdigit():
                value = str(appointment.token_number)
            results.append(_suggestion(
                f'{name} (@{patient.username}) · Token #{appointment.token_number}',
                value,
            ))
            if len(results) == 8:
                break

    elif kind in {'admin-patients', 'reception-patients', 'hospital-patients'}:
        patients = UserProfile.objects.filter(role='patient').select_related('user')
        if kind == 'hospital-patients':
            patients = patients.filter(user__is_active=True)
        patient_filter = (
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(phone__icontains=query)
        )
        patient_number = query.upper().removeprefix('SC-')
        if (
            kind in {'reception-patients', 'hospital-patients'}
            and patient_number.isascii()
            and patient_number.isdigit()
            and len(patient_number) <= 18
        ):
            patient_filter |= Q(user_id=int(patient_number))
        patients = patients.filter(patient_filter).order_by(
            'user__first_name', 'user__last_name', 'user__username',
        )[:8]
        for patient_profile in patients:
            patient = patient_profile.user
            name = patient.get_full_name() or patient.username
            value = _suggestion_value(
                query, patient.first_name, patient.last_name,
                patient.username, patient_profile.phone,
            )
            if not value and patient_number.isascii() and patient_number.isdigit():
                value = f'SC-{patient.pk:05d}'
            results.append(_suggestion(
                f'{name} (@{patient.username}) · SC-{patient.pk:05d}',
                value,
            ))

    else:
        appointments = Appointment.objects.select_related(
            'patient', 'doctor__user', 'doctor__department',
        ).filter(
            Q(patient__first_name__icontains=query)
            | Q(patient__last_name__icontains=query)
            | Q(patient__username__icontains=query)
            | Q(doctor__user__first_name__icontains=query)
            | Q(doctor__user__last_name__icontains=query)
        ).order_by('-appointment_date', 'doctor', 'token_number')[:30]
        seen_patients = set()
        for appointment in appointments:
            patient = appointment.patient
            if patient.pk in seen_patients:
                continue
            seen_patients.add(patient.pk)
            value = _suggestion_value(
                query,
                patient.first_name,
                patient.last_name,
                patient.username,
                appointment.doctor.user.first_name,
                appointment.doctor.user.last_name,
            )
            doctor_name = appointment.doctor.full_name
            patient_name = patient.get_full_name() or patient.username
            results.append(_suggestion(
                f'{patient_name} (@{patient.username}) — {doctor_name}',
                value,
            ))
            if len(results) == 8:
                break

    return JsonResponse({'results': results})
