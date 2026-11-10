import datetime
import logging
import secrets
from smtplib import SMTPException
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Appointment, PatientFeedback, Payment, Waitlist
from .forms import (
    AppointmentBookingForm, RescheduleAppointmentForm,
    CancelAppointmentForm, PatientFeedbackForm, PaymentForm, WaitlistForm,
    ReceptionPatientRegistrationForm,
)
from .queue_service import get_next_token_number, calculate_patient_queue_status, explain_queue_status, save_booked_appointment
from doctors.models import DoctorProfile
from doctors.models import DoctorSchedule
from accounts.models import UserProfile, MedicalHistory, MedicalReport
from ml_engine.ml_service import predict_consultation_duration

logger = logging.getLogger(__name__)
PAYMENT_OTP_SESSION_KEY = 'payment_otp'


def _require_patient(user):
    if not user.is_active or getattr(getattr(user, 'profile', None), 'role', None) != 'patient':
        raise PermissionDenied('Patient access is required.')


def _can_access_appointment(user, appointment):
    if appointment.patient_id == user.pk:
        return True
    return (
        user.is_active
        and getattr(getattr(user, 'profile', None), 'role', None) == 'doctor'
        and appointment.doctor.user_id == user.pk
    )


def _available_slots(doctor, appointment_date):
    schedule = DoctorSchedule.objects.filter(
        doctor=doctor,
        day_of_week=appointment_date.weekday(),
        is_active=True,
    ).first()
    if not doctor.is_available or not schedule or schedule.slot_duration_minutes <= 0:
        return []

    booked_times = set(
        Appointment.objects.filter(
            doctor=doctor,
            appointment_date=appointment_date,
            status__in=['scheduled', 'waiting', 'in_consultation'],
        ).values_list('appointment_time', flat=True)
    )
    slots = []
    current = datetime.datetime.combine(appointment_date, schedule.start_time)
    end = datetime.datetime.combine(appointment_date, schedule.end_time)
    step = datetime.timedelta(minutes=schedule.slot_duration_minutes)
    while current + step <= end:
        slot_time = current.time()
        is_available = slot_time not in booked_times
        if appointment_date == datetime.date.today() and slot_time <= datetime.datetime.now().time():
            is_available = False
        slots.append({
            'value': slot_time.strftime('%H:%M'),
            'label': slot_time.strftime('%I:%M %p').lstrip('0'),
            'available': is_available,
        })
        current += step
    return slots


@login_required
@require_GET
def appointment_slots_api(request):
    doctor_id = request.GET.get('doctor')
    date_value = request.GET.get('date')
    if not doctor_id or not doctor_id.isdigit() or not date_value:
        return JsonResponse({'error': 'Doctor and date are required.'}, status=400)

    try:
        appointment_date = datetime.date.fromisoformat(date_value)
    except ValueError:
        return JsonResponse({'error': 'Enter a valid appointment date.'}, status=400)

    doctor = get_object_or_404(
        DoctorProfile.objects.filter(user__is_active=True, user__profile__role='doctor').only('id', 'is_available'),
        id=doctor_id,
    )
    return JsonResponse({
        'date': date_value,
        'slots': _available_slots(doctor, appointment_date),
    })


def _reception_access(request):
    if hasattr(request.user, 'profile') and request.user.profile.role == 'receptionist':
        return None
    messages.error(request, 'Reception desk access is required.')
    return redirect('accounts:dashboard')


@login_required
def reception_dashboard_view(request):
    access_response = _reception_access(request)
    if access_response:
        return access_response

    today = datetime.date.today()
    appointments = Appointment.objects.filter(
        appointment_date=today
    ).select_related('patient', 'doctor', 'doctor__department').order_by(
        'doctor', 'token_number'
    )
    return render(request, 'appointments/reception_dashboard.html', {
        'today': today,
        'appointments': appointments,
        'total_today': appointments.count(),
        'waiting_count': appointments.filter(status='waiting').count(),
        'completed_count': appointments.filter(status='completed').count(),
        'available_doctors': DoctorProfile.objects.filter(is_available=True, user__is_active=True, user__profile__role='doctor').select_related('department'),
        'patient_count': UserProfile.objects.filter(role='patient').count(),
    })


@login_required
def reception_appointments_view(request):
    access_response = _reception_access(request)
    if access_response:
        return access_response
    today = datetime.date.today()
    appointments = Appointment.objects.filter(
        appointment_date=today
    ).select_related('patient', 'doctor', 'doctor__department').order_by('doctor', 'token_number')
    return render(request, 'appointments/reception_interface.html', {
        'title': "Today's Appointments",
        'description': 'Review and manage every appointment scheduled for today.',
        'appointments': appointments,
        'today': today,
    })


@login_required
def reception_waiting_view(request):
    access_response = _reception_access(request)
    if access_response:
        return access_response
    today = datetime.date.today()
    appointments = Appointment.objects.filter(
        appointment_date=today, status='waiting'
    ).select_related('patient', 'doctor', 'doctor__department').order_by('token_number')
    return render(request, 'appointments/reception_interface.html', {
        'title': 'Waiting Patients',
        'description': 'Call, check in, or cancel patients currently waiting.',
        'appointments': appointments,
        'today': today,
    })


@login_required
def reception_completed_view(request):
    access_response = _reception_access(request)
    if access_response:
        return access_response
    today = datetime.date.today()
    appointments = Appointment.objects.filter(
        appointment_date=today, status='completed'
    ).select_related('patient', 'doctor', 'doctor__department').order_by('token_number')
    return render(request, 'appointments/reception_interface.html', {
        'title': 'Completed Today',
        'description': 'Review consultations completed by the clinic today.',
        'appointments': appointments,
        'today': today,
    })


@login_required
def reception_doctors_view(request):
    access_response = _reception_access(request)
    if access_response:
        return access_response
    return render(request, 'appointments/reception_doctors.html', {
        'doctors': DoctorProfile.objects.filter(is_available=True, user__is_active=True, user__profile__role='doctor').select_related('department'),
    })


@login_required
def reception_patient_search_view(request):
    access_response = _reception_access(request)
    if access_response:
        return access_response

    query = request.GET.get('q', '').strip()
    patients = UserProfile.objects.filter(role='patient').select_related('user')
    if query:
        patient_filter = (
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(phone__icontains=query)
        )
        patient_number = query.upper().removeprefix('SC-')
        if patient_number.isascii() and patient_number.isdigit() and len(patient_number) <= 18:
            patient_filter |= Q(user_id=int(patient_number))
        patients = patients.filter(patient_filter)
    return render(request, 'appointments/reception_patients.html', {
        'patients': patients[:100],
        'query': query,
    })


@login_required
def reception_register_patient_view(request):
    access_response = _reception_access(request)
    if access_response:
        return access_response

    form = ReceptionPatientRegistrationForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            user = User.objects.create_user(
                username=data['username'], email=data['email'],
                password=data['password'] or None,
                first_name=data['first_name'], last_name=data['last_name'],
            )
            user.is_active = True
            user.save(update_fields=['is_active'])
            UserProfile.objects.create(
                user=user,
                role='patient',
                phone=data['phone'], gender=data['gender'],
                date_of_birth=data['date_of_birth'], address=data['address'],
            )
            MedicalHistory.objects.create(patient=user)
        messages.success(request, f'Patient registered successfully. Patient ID: SC-{user.id:05d}')
        return redirect(f'{request.path}?created={user.id}')

    return render(request, 'appointments/reception_register_patient.html', {
        'created_patient_id': request.GET.get('created'),
        'form': form,
    })


@login_required
def reception_book_appointment_view(request):
    access_response = _reception_access(request)
    if access_response:
        return access_response

    selected_patient = request.GET.get('patient_id') or request.POST.get('patient_id')
    patient = get_object_or_404(User, id=selected_patient, profile__role='patient') if selected_patient else None
    if request.method == 'POST':
        form = AppointmentBookingForm(request.POST)
        if form.is_valid() and patient:
            appointment = form.save(commit=False)
            appointment.patient = patient
            profile = patient.profile
            appointment.predicted_duration_minutes = predict_consultation_duration(
                patient_age=profile.calculated_age,
                patient_gender=profile.gender,
                department=appointment.doctor.department.name,
                visit_type=appointment.visit_type,
                symptom_severity=appointment.symptom_severity,
                has_chronic_condition=bool(getattr(patient, 'medical_history', None)),
                doctor_experience_years=appointment.doctor.experience_years,
            )
            try:
                save_booked_appointment(appointment)
            except ValidationError as error:
                form.add_error('appointment_time', error)
            except (IntegrityError, OperationalError):
                form.add_error('appointment_time', 'The schedule changed while booking. Please choose an available slot and try again.')
            else:
                messages.success(request, f'Appointment confirmed. Token #{appointment.token_number}.')
                return redirect('reception:dashboard')
        if not patient:
            messages.error(request, 'Select a patient before booking.')
    else:
        form = AppointmentBookingForm(initial={'appointment_date': datetime.date.today()})

    return render(request, 'appointments/reception_book_appointment.html', {
        'form': form,
        'patient': patient,
        'patients': User.objects.filter(profile__role='patient').order_by('first_name', 'last_name')[:200],
    })


@login_required
@require_POST
def reception_checkin_view(request, appointment_id):
    access_response = _reception_access(request)
    if access_response:
        return access_response
    appointment = get_object_or_404(Appointment, id=appointment_id)
    changed = Appointment.objects.filter(pk=appointment.pk, status='scheduled').update(
        status='waiting', updated_at=timezone.now(),
    )
    if changed:
        messages.success(request, f'Token #{appointment.token_number} checked in.')
    return redirect('reception:dashboard')


@login_required
@require_POST
def reception_queue_action_view(request, appointment_id, action):
    access_response = _reception_access(request)
    if access_response:
        return access_response
    appointment = get_object_or_404(Appointment, id=appointment_id)
    if action == 'call':
        changed = Appointment.objects.filter(pk=appointment.pk, status='scheduled').update(
            status='waiting', updated_at=timezone.now(),
        )
        if changed:
            messages.info(request, f'Token #{appointment.token_number} moved to waiting.')
    elif action == 'cancel':
        changed = Appointment.objects.filter(pk=appointment.pk, status__in=['scheduled', 'waiting']).update(
            status='cancelled', cancellation_reason='Cancelled at reception desk',
            telemedicine_enabled=False, updated_at=timezone.now(),
        )
        if changed:
            messages.warning(request, f'Token #{appointment.token_number} cancelled.')
    return redirect('reception:dashboard')

@login_required
def patient_dashboard_view(request):
    user = request.user
    if not hasattr(user, 'profile') or user.profile.role != 'patient':
        return redirect('accounts:dashboard')
    today = datetime.date.today()
    
    # Active appointment today (for live queue banner)
    today_appointment = Appointment.objects.filter(
        patient=user,
        appointment_date=today,
        status__in=['scheduled', 'waiting', 'in_consultation']
    ).first()
    
    today_queue_info = None
    if today_appointment:
        today_queue_info = calculate_patient_queue_status(today_appointment)
        
    # Upcoming appointments
    upcoming = Appointment.objects.filter(
        patient=user,
        appointment_date__gte=today,
        status__in=['scheduled', 'waiting']
    ).exclude(id=today_appointment.id if today_appointment else 0).select_related('doctor', 'doctor__department')
    
    # Past appointments
    past = Appointment.objects.filter(
        patient=user
    ).filter(
        Q(appointment_date__lt=today) | Q(status__in=['completed', 'cancelled', 'no_show'])
    ).select_related('doctor', 'doctor__department').order_by('-appointment_date', '-appointment_time')[:10]
    waitlist_entries = Waitlist.objects.filter(
        patient=user, status='waiting'
    ).select_related('doctor', 'doctor__department')
    
    context = {
        'today_appointment': today_appointment,
        'today_queue_info': today_queue_info,
        'upcoming': upcoming,
        'past': past,
        'waitlist_entries': waitlist_entries,
        'recent_reports': MedicalReport.objects.filter(patient=user).select_related(
            'consultation__doctor__user'
        )[:5],
    }
    return render(request, 'appointments/patient_dashboard.html', context)


@login_required
def book_appointment_view(request):
    # Only patients can book appointments
    user = request.user
    if not hasattr(user, 'profile') or user.profile.role != 'patient':
        messages.warning(request, "Only patients can book appointments.")
        return redirect('accounts:dashboard')
    if user.is_superuser:
        messages.warning(request, "Only patients can book appointments.")
        return redirect('accounts:dashboard')

    initial_doctor = request.GET.get('doctor_id')
    user_age = user.profile.calculated_age if hasattr(user, 'profile') else 30
    user_gender = user.profile.gender if hasattr(user, 'profile') else 'M'
    
    if request.method == 'POST':
        form = AppointmentBookingForm(request.POST)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.patient = user
            
            # Predict consultation duration using ML
            doc = appointment.doctor
            dept_name = doc.department.name
            pred_duration = predict_consultation_duration(
                patient_age=user_age,
                patient_gender=user_gender,
                department=dept_name,
                visit_type=appointment.visit_type,
                symptom_severity=appointment.symptom_severity,
                has_chronic_condition=appointment.has_chronic_condition,
                doctor_experience_years=doc.experience_years
            )
            appointment.predicted_duration_minutes = pred_duration
            try:
                save_booked_appointment(appointment)
            except ValidationError as error:
                form.add_error('appointment_time', error)
            except (IntegrityError, OperationalError):
                form.add_error('appointment_time', 'The schedule changed while booking. Please choose an available slot and try again.')
            else:
                messages.success(request, f'Appointment booked! Token #{appointment.token_number}. Please submit payment details for billing review.')
                return redirect('appointments:payment', appointment_id=appointment.id)
    else:
        initial = {}
        if initial_doctor:
            initial['doctor'] = initial_doctor
        initial['appointment_date'] = datetime.date.today()
        form = AppointmentBookingForm(initial=initial)
        
    doctors = DoctorProfile.objects.filter(is_available=True, user__is_active=True, user__profile__role='doctor').select_related('department')
    
    context = {
        'form': form,
        'doctors': doctors,
        'user_age': user_age,
        'user_gender': user_gender,
    }
    return render(request, 'appointments/book_appointment.html', context)


@login_required
@require_GET
def queue_tracker_view(request, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related('doctor', 'doctor__department', 'patient'),
        id=appointment_id
    )
    
    if not _can_access_appointment(request.user, appointment):
        raise PermissionDenied('Access denied.')
        
    queue_status = calculate_patient_queue_status(appointment)
    queue_explanation = explain_queue_status(appointment)

    context = {
        'appointment': appointment,
        'queue_status': queue_status,
        'queue_explanation': queue_explanation,
    }
    return render(request, 'appointments/queue_tracker.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def cancel_appointment_view(request, appointment_id):
    _require_patient(request.user)
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)
    if request.method == 'POST':
        DoctorProfile.objects.select_for_update().get(pk=appointment.doctor_id)
        appointment = get_object_or_404(Appointment.objects.select_for_update(), id=appointment_id, patient=request.user)
    
    if appointment.status not in {'scheduled', 'waiting'}:
        messages.warning(request, "This appointment cannot be cancelled.")
        return redirect('appointments:patient_dashboard')
        
    if request.method == 'POST':
        form = CancelAppointmentForm(request.POST)
        if form.is_valid():
            appointment.status = 'cancelled'
            appointment.cancellation_reason = form.cleaned_data['cancellation_reason']
            appointment.save()
            waiting_entry = Waitlist.objects.select_for_update().filter(
                doctor=appointment.doctor,
                preferred_date=appointment.appointment_date,
                status='waiting',
                patient__is_active=True,
            ).select_related('patient').first()
            if waiting_entry:
                promoted = Appointment.objects.create(
                    patient=waiting_entry.patient,
                    doctor=appointment.doctor,
                    appointment_date=appointment.appointment_date,
                    appointment_time=appointment.appointment_time,
                    token_number=get_next_token_number(
                        appointment.doctor, appointment.appointment_date
                    ),
                    visit_type='first_visit',
                    status='scheduled',
                    predicted_duration_minutes=20.0,
                )
                waiting_entry.status = 'promoted'
                waiting_entry.promoted_appointment = promoted
                waiting_entry.notified_at = timezone.now()
                waiting_entry.save(update_fields=[
                    'status', 'promoted_appointment', 'notified_at'
                ])
                if waiting_entry.patient.email:
                    try:
                        send_mail(
                            subject='SmartCare waitlist slot available',
                            message=(
                                f'An appointment is now available with {appointment.doctor.full_name} '
                                f'on {appointment.appointment_date:%B %d, %Y} at '
                                f'{appointment.appointment_time:%I:%M %p}. '
                                f'Your token is #{promoted.token_number}.'
                            ),
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[waiting_entry.patient.email],
                            fail_silently=False,
                        )
                    except (SMTPException, OSError, ValueError) as error:
                        logger.exception('Waitlist promotion email failed: %s', error)
            messages.info(request, f"Appointment #{appointment.token_number} has been cancelled.")
            return redirect('appointments:patient_dashboard')
    else:
        form = CancelAppointmentForm()
        
    return render(request, 'appointments/cancel.html', {'appointment': appointment, 'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def join_waitlist_view(request):
    _require_patient(request.user)
    if request.method == 'POST':
        form = WaitlistForm(request.POST)
        if form.is_valid():
            entry, created = Waitlist.objects.get_or_create(
                patient=request.user, doctor=form.cleaned_data['doctor'],
                preferred_date=form.cleaned_data['preferred_date'],
                defaults={'confirm_token': secrets.token_urlsafe(32)},
            )
            messages.success(
                request,
                f"You are on the waitlist for {entry.doctor.full_name} on "
                f"{entry.preferred_date:%b %d, %Y}.",
            )
            return redirect('appointments:patient_dashboard')
    else:
        form = WaitlistForm()
    return render(request, 'appointments/waitlist.html', {'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def reschedule_appointment_view(request, appointment_id):
    _require_patient(request.user)
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)
    
    if appointment.status not in {'scheduled', 'waiting'}:
        messages.warning(request, "Completed or cancelled appointments cannot be rescheduled.")
        return redirect('appointments:patient_dashboard')
        
    if request.method == 'POST':
        form = RescheduleAppointmentForm(request.POST, appointment=appointment)
        if form.is_valid():
            new_date = form.cleaned_data['appointment_date']
            new_time = form.cleaned_data['appointment_time']
            
            appointment.appointment_date = new_date
            appointment.appointment_time = new_time
            try:
                save_booked_appointment(appointment)
            except ValidationError as error:
                form.add_error('appointment_time', error)
            except (IntegrityError, OperationalError):
                form.add_error('appointment_time', 'The schedule changed. Choose an available slot and try again.')
            else:
                messages.success(request, f'Appointment rescheduled to {new_date}. Token #{appointment.token_number}.')
                return redirect('appointments:queue_tracker', appointment_id=appointment.id)
    else:
        form = RescheduleAppointmentForm(appointment=appointment, initial={
            'appointment_date': appointment.appointment_date,
            'appointment_time': appointment.appointment_time
        })
        
    return render(request, 'appointments/reschedule.html', {'appointment': appointment, 'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def submit_feedback_view(request, appointment_id):
    _require_patient(request.user)
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)
    
    if appointment.status != 'completed':
        messages.error(request, "Feedback can only be provided for completed appointments.")
        return redirect('appointments:patient_dashboard')
        
    if hasattr(appointment, 'feedback'):
        messages.info(request, "You have already submitted feedback for this consultation.")
        return redirect('appointments:patient_dashboard')
        
    if request.method == 'POST':
        form = PatientFeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.appointment = appointment
            feedback.save()
            messages.success(request, "Thank you! Your feedback has been recorded.")
            return redirect('appointments:patient_dashboard')
    else:
        form = PatientFeedbackForm()
        
    return render(request, 'appointments/feedback.html', {'appointment': appointment, 'form': form})


@login_required
@require_GET
def api_queue_status(request, appointment_id):
    """
    AJAX endpoint called by queue tracker to poll real-time queue position and remaining wait time.
    """
    appointment = get_object_or_404(
        Appointment.objects.select_related('doctor', 'doctor__department', 'patient'),
        id=appointment_id,
    )
    if not _can_access_appointment(request.user, appointment):
        return JsonResponse({'error': 'Access denied.'}, status=403)
    status_info = calculate_patient_queue_status(appointment)
    return JsonResponse(status_info)


def _pdf_escape(value):
    return str(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def build_pdf_response(lines, filename):
    content = ['BT', '/F1 12 Tf', '50 780 Td']
    for index, line in enumerate(lines):
        if index:
            content.append('0 -18 Td')
        content.append(f'({_pdf_escape(line)}) Tj')
    content.append('ET')
    body = '\n'.join(content).encode('latin-1', errors='replace')
    objects = [
        b'1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj',
        b'2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj',
        b'3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj',
        b'4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj',
        b'5 0 obj << /Length ' + str(len(body)).encode() + b' >> stream\n' + body + b'\nendstream endobj',
    ]
    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj + b'\n')
    xref_offset = len(pdf)
    pdf.extend(f'xref\n0 {len(objects) + 1}\n'.encode())
    pdf.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode())
    pdf.extend(f'trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF'.encode())
    response = HttpResponse(bytes(pdf), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def prescription_pdf_view(request, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related('patient', 'doctor', 'doctor__department'),
        id=appointment_id, patient=request.user, status='completed',
    )
    if not appointment.prescription.strip():
        messages.info(request, 'No prescription is available for this consultation.')
        return redirect('appointments:patient_dashboard')

    lines = [
        'SMARTCARE DIGITAL PRESCRIPTION',
        f'Patient: {appointment.patient.get_full_name() or appointment.patient.username}',
        f'Doctor: {appointment.doctor.full_name}',
        f'Department: {appointment.doctor.department.name}',
        f'Date: {appointment.appointment_date:%B %d, %Y}',
        f'Appointment token: #{appointment.token_number}',
        '',
        'Prescription:',
        *appointment.prescription.splitlines(),
        '',
        'Doctor notes:',
        *(appointment.doctor_notes.splitlines() or ['None']),
    ]
    return build_pdf_response(
        lines, f'smartcare-prescription-{appointment.id}.pdf'
    )


@login_required
def invoice_pdf_view(request, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related('patient', 'doctor', 'doctor__department'),
        id=appointment_id,
    )
    allowed = _can_access_appointment(request.user, appointment)
    if not allowed:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')
    payment = getattr(appointment, 'payment', None)
    if not payment or payment.status != 'completed':
        messages.info(request, 'An invoice is available after payment is completed.')
        return redirect('appointments:patient_dashboard')
    return build_pdf_response([
        'SMARTCARE PAYMENT INVOICE',
        f'Invoice for appointment #{appointment.token_number}',
        f'Patient: {appointment.patient.get_full_name() or appointment.patient.username}',
        f'Doctor: {appointment.doctor.full_name}',
        f'Date: {appointment.appointment_date:%B %d, %Y}',
        f'Payment method: {payment.get_payment_method_display()}',
        f'Transaction ID: {payment.transaction_id or "N/A"}',
        f'Amount paid: BDT {payment.amount}',
        f'Paid at: {payment.paid_at:%B %d, %Y %I:%M %p}',
    ], f'smartcare-invoice-{appointment.id}.pdf')


@login_required
def telemedicine_view(request, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related('patient', 'doctor'),
        id=appointment_id,
    )
    if not _can_access_appointment(request.user, appointment):
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')
    if appointment.status not in {'scheduled', 'waiting', 'in_consultation'}:
        messages.error(request, 'This appointment is not open for telemedicine.')
        return redirect('accounts:dashboard')
    if not appointment.telemedicine_enabled:
        messages.info(request, 'The doctor has not opened the telemedicine room yet.')
        return redirect('appointments:queue_tracker', appointment_id=appointment.id)
    return render(request, 'appointments/telemedicine.html', {
        'appointment': appointment,
        'room_name': f'smartcare-{appointment.telemedicine_room}',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def payment_view(request, appointment_id):
    _require_patient(request.user)
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)
    if appointment.status not in {'scheduled', 'waiting', 'completed'}:
        raise PermissionDenied('Payment cannot be submitted for this appointment.')
    # A patient-supplied reference or email code never proves that funds arrived.
    # Only trusted billing staff or a verified gateway integration may settle it.
    request.session.pop(PAYMENT_OTP_SESSION_KEY, None)
    existing_payment = getattr(appointment, 'payment', None)
    if existing_payment and existing_payment.status == 'completed':
        messages.info(request, 'Payment was already confirmed by billing.')
        return redirect('appointments:queue_tracker', appointment_id=appointment.id)

    consultation_fee = appointment.doctor.consultation_fee
    form = PaymentForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and request.POST.get('action') == 'verify_otp':
        form.add_error(None, 'Email codes cannot verify a payment. Submit your payment reference for billing review.')
    elif request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            # Serialize against trusted billing changes to avoid reverting a settled payment.
            appointment = get_object_or_404(
                Appointment.objects.select_for_update(), id=appointment_id, patient=request.user,
            )
            payment, _ = Payment.objects.select_for_update().get_or_create(
                appointment=appointment,
                defaults={'patient': request.user, 'amount': consultation_fee},
            )
            if payment.status != 'completed':
                payment.payment_method = form.cleaned_data['payment_method']
                payment.transaction_id = form.cleaned_data.get('transaction_id', '')
                payment.amount = consultation_fee
                payment.status = 'pending'
                payment.paid_at = None
                payment.save(update_fields=[
                    'payment_method', 'transaction_id', 'amount', 'status', 'paid_at',
                ])
        messages.info(request, 'Payment details submitted. Payment remains pending until hospital billing verifies receipt.')
        return redirect('appointments:queue_tracker', appointment_id=appointment.id)

    return render(request, 'appointments/payment.html', {
        'appointment': appointment,
        'form': form,
        'consultation_fee': consultation_fee,
        'payment': existing_payment,
    })
