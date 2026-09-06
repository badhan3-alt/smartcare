import datetime
from django.utils import timezone
from django.db.models import Max
from .models import Appointment

def get_next_token_number(doctor, appointment_date):
    """
    Returns the next queue token number for a given doctor on a specific date.
    """
    latest = Appointment.objects.filter(
        doctor=doctor,
        appointment_date=appointment_date
    ).aggregate(Max('token_number'))['token_number__max']
    
    return (latest or 0) + 1

def calculate_patient_queue_status(appointment):
    """
    Computes real-time queue position and estimated waiting time for a patient appointment.
    Estimated wait time is calculated dynamically using ML predicted consultation durations.
    """
    today = datetime.date.today()
    doctor = appointment.doctor
    
    status_info = {
        'appointment_id': appointment.id,
        'token_number': appointment.token_number,
        'status': appointment.status,
        'status_display': appointment.get_status_display(),
        'doctor_name': doctor.full_name,
        'department': doctor.department.name,
        'room_number': doctor.room_number,
        'appointment_date': appointment.appointment_date,
        'appointment_time': appointment.appointment_time.strftime("%I:%M %p"),
        'is_today': (appointment.appointment_date == today),
        'currently_serving_token': None,
        'patients_ahead_count': 0,
        'estimated_wait_minutes': 0,
        'estimated_consultation_time': appointment.predicted_duration_minutes,
        'doctor_status': 'Available' if doctor.is_available else 'Away',
    }

    if appointment.status in ['completed', 'cancelled', 'no_show']:
        return status_info

    if not status_info['is_today']:
        days_away = (appointment.appointment_date - today).days
        status_info['message'] = f"Appointment is scheduled in {days_away} day{'s' if days_away != 1 else ''}."
        return status_info

    todays_appointments = Appointment.objects.filter(
        doctor=doctor,
        appointment_date=today
    ).order_by('token_number')

    in_consultation_appt = todays_appointments.filter(status='in_consultation').first()
    remaining_current_mins = 0.0

    if in_consultation_appt:
        status_info['currently_serving_token'] = in_consultation_appt.token_number
        if in_consultation_appt.consultation_started_at:
            elapsed_mins = (timezone.now() - in_consultation_appt.consultation_started_at).total_seconds() / 60.0
            remaining_current_mins = max(1.0, in_consultation_appt.predicted_duration_minutes - elapsed_mins)
        else:
            remaining_current_mins = in_consultation_appt.predicted_duration_minutes
    else:
        last_completed = todays_appointments.filter(status='completed').last()
        status_info['currently_serving_token'] = last_completed.token_number if last_completed else 0

    if appointment.status == 'in_consultation':
        status_info['patients_ahead_count'] = 0
        status_info['estimated_wait_minutes'] = 0
        status_info['message'] = "It is your turn! Please proceed to the consultation room."
        return status_info

    patients_ahead = todays_appointments.filter(
        token_number__lt=appointment.token_number,
        status__in=['scheduled', 'waiting']
    )

    status_info['patients_ahead_count'] = patients_ahead.count()
    ahead_duration_sum = sum(p.predicted_duration_minutes for p in patients_ahead)
    total_wait = remaining_current_mins + ahead_duration_sum

    status_info['estimated_wait_minutes'] = int(round(total_wait))
    
    if status_info['patients_ahead_count'] == 0:
        if in_consultation_appt:
            status_info['message'] = f"You are next! Estimated wait: {status_info['estimated_wait_minutes']} mins."
        else:
            status_info['message'] = "You are first in queue. Doctor will call you shortly."
    else:
        status_info['message'] = f"{status_info['patients_ahead_count']} patient(s) ahead. Estimated wait: ~{status_info['estimated_wait_minutes']} mins."

    return status_info

def get_doctor_live_queue_summary(doctor, date=None):
    """
    Returns full queue breakdown for doctor's console on a given date (defaults to today).
    """
    if date is None:
        date = datetime.date.today()
        
    appts = Appointment.objects.filter(
        doctor=doctor,
        appointment_date=date
    ).select_related('patient', 'patient__profile').order_by('token_number')
    
    in_consultation = appts.filter(status='in_consultation').first()
    waiting_count = appts.filter(status='waiting').count()
    scheduled_count = appts.filter(status='scheduled').count()
    completed_count = appts.filter(status='completed').count()
    cancelled_count = appts.filter(status='cancelled').count()
    no_show_count = appts.filter(status='no_show').count()
    
    pending_appts = appts.filter(status__in=['scheduled', 'waiting', 'in_consultation'])
    total_pending_minutes = sum(a.predicted_duration_minutes for a in pending_appts)
    
    return {
        'date': date,
        'appointments': appts,
        'in_consultation': in_consultation,
        'total_count': appts.count(),
        'waiting_count': waiting_count,
        'scheduled_count': scheduled_count,
        'completed_count': completed_count,
        'cancelled_count': cancelled_count,
        'no_show_count': no_show_count,
        'pending_minutes': int(round(total_pending_minutes))
    }

