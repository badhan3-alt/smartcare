import datetime
import json
from django.db.models import Avg, Count, Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone

from .models import Department, DoctorProfile, DoctorSchedule
from .forms import DoctorConsultationForm
from appointments.models import Appointment

def doctor_list_view(request):
    dept_id = request.GET.get('department')
    search_query = request.GET.get('q', '').strip()
    specialization = request.GET.get('specialization', '').strip()
    min_experience = request.GET.get('min_experience', '').strip()
    max_fee = request.GET.get('max_fee', '').strip()
    min_rating = request.GET.get('min_rating', '').strip()
    
    doctors = DoctorProfile.objects.filter(is_available=True).select_related('user', 'department')
    
    if dept_id:
        doctors = doctors.filter(department_id=dept_id)
        
    if search_query:
        doctors = doctors.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(specialization__icontains=search_query) |
            Q(qualification__icontains=search_query) |
            Q(department__name__icontains=search_query)
        )
    if specialization:
        doctors = doctors.filter(specialization__icontains=specialization)
    if min_experience.isdigit():
        doctors = doctors.filter(experience_years__gte=int(min_experience))
    try:
        if max_fee:
            doctors = doctors.filter(consultation_fee__lte=float(max_fee))
    except ValueError:
        pass
    if min_rating in {'3', '4', '5'}:
        doctors = [
            doctor for doctor in doctors
            if doctor.average_rating >= int(min_rating)
        ]
        
    departments = Department.objects.filter(is_active=True)
    
    context = {
        'doctors': doctors,
        'departments': departments,
        'selected_dept': int(dept_id) if dept_id and dept_id.isdigit() else None,
        'search_query': search_query,
        'specialization': specialization,
        'min_experience': min_experience,
        'max_fee': max_fee,
        'min_rating': min_rating,
    }
    return render(request, 'doctors/doctor_list.html', context)


def doctor_detail_view(request, doctor_id):
    doctor = get_object_or_404(DoctorProfile.objects.select_related('user', 'department'), id=doctor_id)
    schedules = doctor.schedules.filter(is_active=True).order_by('day_of_week')
    
    from appointments.models import PatientFeedback
    feedbacks = PatientFeedback.objects.filter(appointment__doctor=doctor).select_related('appointment__patient')[:10]
    
    context = {
        'doctor': doctor,
        'schedules': schedules,
        'feedbacks': feedbacks,
    }
    return render(request, 'doctors/doctor_detail.html', context)


@login_required
def doctor_dashboard_view(request):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    today = datetime.date.today()
    
    from appointments.queue_service import get_doctor_live_queue_summary
    from appointments.models import Appointment
    
    queue_data = get_doctor_live_queue_summary(doctor, today)
    recent_completed = Appointment.objects.filter(
        doctor=doctor,
        status='completed'
    ).select_related('patient').order_by('-updated_at')[:8]
    period_start = today - datetime.timedelta(days=30)
    period = Appointment.objects.filter(doctor=doctor, appointment_date__gte=period_start)
    completed = period.filter(status='completed')
    analytics = {
        'period_start': period_start,
        'total': period.count(),
        'completed': completed.count(),
        'completion_rate': round(completed.count() / period.count() * 100, 1) if period.exists() else 0,
        'average_duration': round(completed.aggregate(value=Avg('actual_duration_minutes'))['value'] or 0, 1),
        'revenue': period.filter(payment__status='completed').aggregate(value=Sum('payment__amount'))['value'] or 0,
        'visit_types': list(period.values('visit_type').annotate(count=Count('id')).order_by('-count')),
    }
    
    context = {
        'doctor': doctor,
        'queue': queue_data,
        'recent_completed': recent_completed,
        'analytics': analytics,
        'analytics_visit_types': json.dumps(analytics['visit_types']),
    }
    return render(request, 'doctors/dashboard.html', context)


@login_required
def doctor_queue_console_view(request):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    today = datetime.date.today()
    
    from appointments.queue_service import get_doctor_live_queue_summary
    queue_data = get_doctor_live_queue_summary(doctor, today)
    form = DoctorConsultationForm()
    
    context = {
        'doctor': doctor,
        'queue': queue_data,
        'form': form,
    }
    return render(request, 'doctors/queue_console.html', context)


@login_required
def doctor_open_telemedicine_view(request, appointment_id):
    appointment = get_object_or_404(
        Appointment, id=appointment_id, doctor__user=request.user,
    )
    if appointment.status not in {'scheduled', 'waiting', 'in_consultation'}:
        messages.error(request, 'Telemedicine is only available for active appointments.')
    else:
        appointment.telemedicine_enabled = True
        appointment.save(update_fields=['telemedicine_enabled', 'updated_at'])
        messages.success(request, f'Telemedicine room opened for Token #{appointment.token_number}.')
    return redirect('doctors:queue_console')


@login_required
def doctor_call_patient_view(request, appointment_id):
    from appointments.models import Appointment
    appointment = get_object_or_404(Appointment, id=appointment_id, doctor__user=request.user)
    appointment.status = 'waiting'
    appointment.save()
    messages.info(request, f"Called patient Token #{appointment.token_number} ({appointment.patient.get_full_name() or appointment.patient.username}).")
    return redirect('doctors:queue_console')


@login_required
def doctor_start_consultation_view(request, appointment_id):
    from appointments.models import Appointment
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    
    ongoing = Appointment.objects.filter(doctor=doctor, status='in_consultation').first()
    if ongoing and ongoing.id != appointment_id:
        messages.warning(request, f"Token #{ongoing.token_number} is already in consultation. Please complete it first.")
        return redirect('doctors:queue_console')
        
    appointment = get_object_or_404(Appointment, id=appointment_id, doctor=doctor)
    appointment.status = 'in_consultation'
    appointment.consultation_started_at = timezone.now()
    appointment.save()
    
    messages.success(request, f"Consultation started with Token #{appointment.token_number}!")
    return redirect('doctors:queue_console')


@login_required
def doctor_complete_consultation_view(request, appointment_id):
    from appointments.models import Appointment
    appointment = get_object_or_404(Appointment, id=appointment_id, doctor__user=request.user)
    
    if request.method == 'POST':
        form = DoctorConsultationForm(request.POST)
        if form.is_valid():
            appointment.status = 'completed'
            appointment.actual_duration_minutes = form.cleaned_data['actual_duration_minutes']
            appointment.doctor_notes = form.cleaned_data['doctor_notes']
            appointment.prescription = form.cleaned_data['prescription']
            appointment.consultation_ended_at = timezone.now()
            appointment.save()
            
            messages.success(request, f"Consultation for Token #{appointment.token_number} completed and recorded!")
            return redirect('doctors:queue_console')
    
    messages.error(request, "Invalid submission.")
    return redirect('doctors:queue_console')


@login_required
def doctor_no_show_view(request, appointment_id):
    from appointments.models import Appointment
    appointment = get_object_or_404(Appointment, id=appointment_id, doctor__user=request.user)
    appointment.status = 'no_show'
    appointment.save()
    messages.warning(request, f"Token #{appointment.token_number} marked as No-Show.")
    return redirect('doctors:queue_console')


@login_required
def doctor_schedule_view(request):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    schedules = doctor.schedules.all().order_by('day_of_week')

    if not schedules.exists():
        default_days = list(range(5))
        for day_idx in default_days:
            DoctorSchedule.objects.get_or_create(
                doctor=doctor,
                day_of_week=day_idx,
                defaults={
                    'start_time': datetime.time(9, 0),
                    'end_time': datetime.time(17, 0),
                    'slot_duration_minutes': 20,
                    'is_active': True,
                },
            )
        schedules = doctor.schedules.all().order_by('day_of_week')

    if request.method == 'POST':
        is_avail = request.POST.get('is_available') == 'on'
        doctor.is_available = is_avail
        doctor.save(update_fields=['is_available'])

        for schedule in schedules:
            prefix = f'schedule_{schedule.id}'
            start_value = request.POST.get(f'{prefix}_start_time')
            end_value = request.POST.get(f'{prefix}_end_time')
            duration_value = request.POST.get(f'{prefix}_slot_duration_minutes')

            if not start_value or not end_value or not duration_value:
                continue

            try:
                start_time = datetime.datetime.strptime(start_value, '%H:%M').time()
                end_time = datetime.datetime.strptime(end_value, '%H:%M').time()
                slot_duration = int(duration_value)
            except ValueError:
                messages.error(request, f'Please enter valid times for {schedule.get_day_of_week_display()}.')
                return redirect('doctors:schedule')

            if start_time >= end_time:
                messages.error(request, f'End time must be after start time for {schedule.get_day_of_week_display()}.')
                return redirect('doctors:schedule')

            if slot_duration <= 0:
                messages.error(request, f'Slot duration must be greater than zero for {schedule.get_day_of_week_display()}.')
                return redirect('doctors:schedule')

            schedule.start_time = start_time
            schedule.end_time = end_time
            schedule.slot_duration_minutes = slot_duration
            schedule.is_active = f'{prefix}_is_active' in request.POST
            schedule.save(update_fields=['start_time', 'end_time', 'slot_duration_minutes', 'is_active'])

        messages.success(request, f"Availability updated to {'Available' if is_avail else 'Away'}.")
        return redirect('doctors:schedule')

    return render(request, 'doctors/manage_schedule.html', {'doctor': doctor, 'schedules': schedules})


@login_required
def doctor_analytics_report_view(request):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    from appointments.views import build_pdf_response
    today = datetime.date.today()
    start = today - datetime.timedelta(days=30)
    appointments = Appointment.objects.filter(doctor=doctor, appointment_date__gte=start)
    completed = appointments.filter(status='completed')
    lines = [
        'SMARTCARE DOCTOR ANALYTICS REPORT',
        f'Doctor: {doctor.full_name}',
        f'Period: {start:%B %d, %Y} - {today:%B %d, %Y}',
        '',
        f'Total appointments: {appointments.count()}',
        f'Completed consultations: {completed.count()}',
        f'Average actual duration: {completed.aggregate(v=Avg("actual_duration_minutes"))["v"] or 0:.1f} minutes',
        f'Completed revenue: {appointments.filter(payment__status="completed").aggregate(v=Sum("payment__amount"))["v"] or 0}',
    ]
    return build_pdf_response(lines, f'doctor-analytics-{doctor.id}.pdf')
