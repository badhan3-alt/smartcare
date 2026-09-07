import datetime
import logging
import secrets
import time
from smtplib import SMTPException
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.utils import timezone

from .models import Appointment, PatientFeedback, Payment, Waitlist
from .forms import (
    AppointmentBookingForm, RescheduleAppointmentForm,
    CancelAppointmentForm, PatientFeedbackForm, PaymentForm, WaitlistForm
)
from .queue_service import get_next_token_number, calculate_patient_queue_status, explain_queue_status
from doctors.models import DoctorProfile
from ml_engine.ml_service import predict_consultation_duration

logger = logging.getLogger(__name__)
PAYMENT_OTP_SESSION_KEY = 'payment_otp'
PAYMENT_OTP_TTL = 10 * 60

@login_required
def patient_dashboard_view(request):
    user = request.user
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
    }
    return render(request, 'appointments/patient_dashboard.html', context)


@login_required
def book_appointment_view(request):
    # Only patients can book appointments
    user = request.user
    if hasattr(user, 'profile') and user.profile.role in ['admin', 'doctor']:
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
            appointment.token_number = get_next_token_number(doc, appointment.appointment_date)
            appointment.status = 'scheduled'
            appointment.save()
            
            messages.success(
                request,
                f"Appointment booked! Token #{appointment.token_number}. "
                f"ML estimated duration: {pred_duration} mins. Please complete payment."
            )
            return redirect('appointments:payment', appointment_id=appointment.id)
    else:
        initial = {}
        if initial_doctor:
            initial['doctor'] = initial_doctor
        initial['appointment_date'] = datetime.date.today()
        form = AppointmentBookingForm(initial=initial)
        
    doctors = DoctorProfile.objects.filter(is_available=True).select_related('department')
    
    context = {
        'form': form,
        'doctors': doctors,
        'user_age': user_age,
        'user_gender': user_gender,
    }
    return render(request, 'appointments/book_appointment.html', context)


@login_required
def queue_tracker_view(request, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related('doctor', 'doctor__department', 'patient'),
        id=appointment_id
    )
    
    if appointment.patient != request.user and not (hasattr(request.user, 'profile') and request.user.profile.role in ['doctor', 'admin']):
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')
        
    queue_status = calculate_patient_queue_status(appointment)
    queue_explanation = explain_queue_status(appointment)

    context = {
        'appointment': appointment,
        'queue_status': queue_status,
        'queue_explanation': queue_explanation,
    }
    return render(request, 'appointments/queue_tracker.html', context)


@login_required
def cancel_appointment_view(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)
    
    if appointment.status in ['completed', 'cancelled']:
        messages.warning(request, "This appointment cannot be cancelled.")
        return redirect('appointments:patient_dashboard')
        
    if request.method == 'POST':
        form = CancelAppointmentForm(request.POST)
        if form.is_valid():
            appointment.status = 'cancelled'
            appointment.cancellation_reason = form.cleaned_data['cancellation_reason']
            appointment.save()
            waiting_entry = Waitlist.objects.filter(
                doctor=appointment.doctor,
                preferred_date=appointment.appointment_date,
                status='waiting',
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
                messages.info(
                    request,
                    f"{waiting_entry.patient.get_full_name() or waiting_entry.patient.username} "
                    "was promoted from the waitlist.",
                )
            messages.info(request, f"Appointment #{appointment.token_number} has been cancelled.")
            return redirect('appointments:patient_dashboard')
    else:
        form = CancelAppointmentForm()
        
    return render(request, 'appointments/cancel.html', {'appointment': appointment, 'form': form})


@login_required
def join_waitlist_view(request):
    if request.method == 'POST':
        form = WaitlistForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.patient = request.user
            entry.confirm_token = secrets.token_urlsafe(32)
            entry.save()
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
def reschedule_appointment_view(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)
    
    if appointment.status in ['completed', 'cancelled']:
        messages.warning(request, "Completed or cancelled appointments cannot be rescheduled.")
        return redirect('appointments:patient_dashboard')
        
    if request.method == 'POST':
        form = RescheduleAppointmentForm(request.POST)
        if form.is_valid():
            new_date = form.cleaned_data['appointment_date']
            new_time = form.cleaned_data['appointment_time']
            
            appointment.appointment_date = new_date
            appointment.appointment_time = new_time
            appointment.token_number = get_next_token_number(appointment.doctor, new_date)
            appointment.status = 'scheduled'
            appointment.save()
            
            messages.success(request, f"Appointment rescheduled to {new_date} with new Token #{appointment.token_number}.")
            return redirect('appointments:queue_tracker', appointment_id=appointment.id)
    else:
        form = RescheduleAppointmentForm(initial={
            'appointment_date': appointment.appointment_date,
            'appointment_time': appointment.appointment_time
        })
        
    return render(request, 'appointments/reschedule.html', {'appointment': appointment, 'form': form})


@login_required
def submit_feedback_view(request, appointment_id):
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


def api_queue_status(request, appointment_id):
    """
    AJAX endpoint called by queue tracker to poll real-time queue position and remaining wait time.
    """
    appointment = get_object_or_404(Appointment, id=appointment_id)
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
    allowed = appointment.patient_id == request.user.id or appointment.doctor.user_id == request.user.id or request.user.is_staff
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
    if request.user.id not in {appointment.patient_id, appointment.doctor.user_id}:
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
def payment_view(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)

    # If already paid, go to queue tracker
    if hasattr(appointment, 'payment') and appointment.payment.status == 'completed':
        messages.info(request, "Payment already completed for this appointment.")
        return redirect('appointments:queue_tracker', appointment_id=appointment.id)

    consultation_fee = appointment.doctor.consultation_fee

    if request.method == 'POST':
        if request.POST.get('action') == 'verify_otp':
            otp_data = request.session.get(PAYMENT_OTP_SESSION_KEY)
            submitted_otp = request.POST.get('otp', '').strip()
            if (
                not otp_data
                or otp_data.get('appointment_id') != appointment.id
                or int(time.time()) > otp_data.get('expires_at', 0)
            ):
                request.session.pop(PAYMENT_OTP_SESSION_KEY, None)
                messages.error(request, 'This payment OTP has expired. Please request a new one.')
            elif not secrets.compare_digest(submitted_otp, otp_data.get('code', '')):
                messages.error(request, 'The payment OTP is invalid.')
            else:
                payment = get_object_or_404(Payment, appointment=appointment, patient=request.user)
                payment.status = 'completed'
                payment.paid_at = timezone.now()
                payment.save(update_fields=['status', 'paid_at'])
                request.session.pop(PAYMENT_OTP_SESSION_KEY, None)
                try:
                    send_mail(
                        subject='SmartCare payment confirmation',
                        message=(
                            f'Hello {request.user.get_full_name() or request.user.username},\n\n'
                            f'Your payment of ৳{consultation_fee} for appointment '
                            f'#{appointment.token_number} has been confirmed.\n'
                            f'Doctor: {appointment.doctor.full_name}\n'
                            f'Date: {appointment.appointment_date}\n'
                            f'Payment method: {payment.get_payment_method_display()}\n'
                            f'Transaction ID: {payment.transaction_id or "N/A"}\n\n'
                            'Thank you,\nSmartCare'
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[request.user.email],
                        fail_silently=False,
                    )
                except (SMTPException, OSError, ValueError) as error:
                    logger.exception('Payment confirmation email failed: %s', error)
                    messages.warning(
                        request,
                        f"Payment of ৳{consultation_fee} completed successfully, "
                        "but the confirmation email could not be sent.",
                    )
                else:
                    messages.success(
                        request,
                        f"Payment of ৳{consultation_fee} completed successfully! "
                        "Your appointment is confirmed. A confirmation email has been sent.",
                    )
                return redirect('appointments:queue_tracker', appointment_id=appointment.id)
        else:
            form = PaymentForm(request.POST)
            if form.is_valid():
                payment, _ = Payment.objects.get_or_create(
                    appointment=appointment,
                    defaults={
                        'patient': request.user,
                        'amount': consultation_fee,
                    }
                )
                payment.payment_method = form.cleaned_data['payment_method']
                payment.transaction_id = form.cleaned_data.get('transaction_id', '')
                payment.amount = consultation_fee
                payment.status = 'pending'
                payment.paid_at = None
                payment.save(update_fields=[
                    'payment_method', 'transaction_id', 'amount', 'status', 'paid_at'
                ])

                if not request.user.email:
                    messages.error(request, 'Add an email address to your account before confirming payment.')
                else:
                    code = f'{secrets.randbelow(1000000):06d}'
                    request.session[PAYMENT_OTP_SESSION_KEY] = {
                        'appointment_id': appointment.id,
                        'code': code,
                        'expires_at': int(time.time()) + PAYMENT_OTP_TTL,
                    }
                    request.session.modified = True
                    try:
                        send_mail(
                            subject='Your SmartCare payment verification code',
                            message=(
                                f'Hello {request.user.get_full_name() or request.user.username},\n\n'
                                f'Your SmartCare payment verification code is: {code}\n\n'
                                'This code expires in 10 minutes. '
                                'Do not share this code with anyone.\n\n'
                                'Thank you,\nSmartCare'
                            ),
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[request.user.email],
                            fail_silently=False,
                        )
                        messages.info(
                            request,
                            f'A payment verification OTP was sent to {request.user.email}.',
                        )
                    except (SMTPException, OSError, ValueError) as error:
                        logger.exception('Payment OTP email failed: %s', error)
                        request.session.pop(PAYMENT_OTP_SESSION_KEY, None)
                        messages.error(
                            request,
                            'We could not send the payment OTP. Check your email configuration and try again.',
                        )
    else:
        form = PaymentForm()

    otp_pending = request.session.get(PAYMENT_OTP_SESSION_KEY, {}).get('appointment_id') == appointment.id
    context = {
        'appointment': appointment,
        'form': form,
        'consultation_fee': consultation_fee,
        'otp_pending': otp_pending,
    }
    return render(request, 'appointments/payment.html', context)
