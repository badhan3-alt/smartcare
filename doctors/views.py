import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone

from .models import Department, DoctorProfile, DoctorSchedule
from .forms import DoctorConsultationForm

def doctor_list_view(request):
    dept_id = request.GET.get('department')
    search_query = request.GET.get('q', '').strip()
    
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
        
    departments = Department.objects.filter(is_active=True)
    
    context = {
        'doctors': doctors,
        'departments': departments,
        'selected_dept': int(dept_id) if dept_id and dept_id.isdigit() else None,
        'search_query': search_query,
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
    
    context = {
        'doctor': doctor,
        'queue': queue_data,
        'recent_completed': recent_completed,
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
    
    if request.method == 'POST':
        is_avail = request.POST.get('is_available') == 'on'
        doctor.is_available = is_avail
        doctor.save()
        messages.success(request, f"Availability updated to {'Available' if is_avail else 'Away'}.")
        return redirect('doctors:schedule')
        
    return render(request, 'doctors/manage_schedule.html', {'doctor': doctor, 'schedules': schedules})

