import json
import datetime
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count
from django.db.models import Q

from accounts.models import UserProfile
from doctors.models import DoctorProfile
from appointments.models import Appointment, Payment
from .ml_service import predict_consultation_duration, forecast_appointment_demand, get_staffing_recommendations


def _require_admin(request):
    if request.user.is_superuser or (
        hasattr(request.user, 'profile') and request.user.profile.role == 'admin'
    ):
        return None
    messages.error(request, "Administrator privileges required.")
    return redirect('accounts:dashboard')

@login_required
def admin_dashboard_view(request):
    access_response = _require_admin(request)
    if access_response:
        return access_response
        
    total_patients = UserProfile.objects.filter(role='patient').count()
    total_doctors = DoctorProfile.objects.filter(is_available=True).count()
    total_appointments = Appointment.objects.count()
    
    today = datetime.date.today()
    today_appointments = Appointment.objects.filter(appointment_date=today).count()
    
    # Status breakdown
    status_counts = Appointment.objects.values('status').annotate(count=Count('status'))
    status_dict = {item['status']: item['count'] for item in status_counts}
    
    # Department breakdown
    dept_counts = Appointment.objects.values('doctor__department__name').annotate(count=Count('id'))
    dept_labels = [item['doctor__department__name'] or 'General' for item in dept_counts]
    dept_values = [item['count'] for item in dept_counts]
    
    # Recent appointments
    recent_appointments = Appointment.objects.select_related(
        'patient', 'doctor', 'doctor__department'
    ).order_by('-id')[:12]

    # Payment / Revenue stats
    from django.db.models import Sum
    total_revenue = Payment.objects.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
    today_revenue = Payment.objects.filter(status='completed', paid_at__date=today).aggregate(total=Sum('amount'))['total'] or 0
    total_payments = Payment.objects.filter(status='completed').count()
    recent_payments = Payment.objects.filter(status='completed').select_related(
        'patient', 'appointment', 'appointment__doctor'
    ).order_by('-paid_at')[:10]

    context = {
        'stats': {
            'total_patients': total_patients,
            'total_doctors': total_doctors,
            'total_appointments': total_appointments,
            'today_appointments': today_appointments,
            'total_revenue': total_revenue,
            'today_revenue': today_revenue,
            'total_payments': total_payments,
        },
        'today': today,
        'status_dict': json.dumps(status_dict),
        'dept_labels': json.dumps(dept_labels),
        'dept_values': json.dumps(dept_values),
        'recent_appointments': recent_appointments,
        'recent_payments': recent_payments,
    }
    return render(request, 'ml_engine/admin_dashboard.html', context)


@login_required
def admin_patient_list_view(request):
    access_response = _require_admin(request)
    if access_response:
        return access_response

    search_query = request.GET.get('q', '').strip()
    patients = UserProfile.objects.filter(role='patient').select_related('user').order_by(
        'user__first_name', 'user__last_name', 'user__username'
    )
    if search_query:
        patients = patients.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(phone__icontains=search_query)
        )

    return render(request, 'ml_engine/admin_patient_list.html', {
        'patients': patients,
        'search_query': search_query,
    })


@login_required
def admin_appointment_list_view(request):
    access_response = _require_admin(request)
    if access_response:
        return access_response

    selected_date = request.GET.get('date', '').strip()
    selected_status = request.GET.get('status', '').strip()
    search_query = request.GET.get('q', '').strip()
    appointments = Appointment.objects.select_related(
        'patient', 'doctor', 'doctor__department'
    ).order_by('-appointment_date', 'doctor', 'token_number')

    if selected_date:
        appointments = appointments.filter(appointment_date=selected_date)
    if selected_status:
        appointments = appointments.filter(status=selected_status)
    if search_query:
        appointments = appointments.filter(
            Q(patient__first_name__icontains=search_query) |
            Q(patient__last_name__icontains=search_query) |
            Q(patient__username__icontains=search_query) |
            Q(doctor__user__first_name__icontains=search_query) |
            Q(doctor__user__last_name__icontains=search_query)
        )

    return render(request, 'ml_engine/admin_appointment_list.html', {
        'appointments': appointments,
        'selected_date': selected_date,
        'selected_status': selected_status,
        'search_query': search_query,
        'status_choices': Appointment._meta.get_field('status').choices,
        'today': datetime.date.today(),
        'queue_view': selected_date == datetime.date.today().isoformat(),
    })


@login_required
def admin_demand_forecast_view(request):
    access_response = _require_admin(request)
    if access_response:
        return access_response
        
    days = int(request.GET.get('days', 7))
    forecast_data = forecast_appointment_demand(days_ahead=days)
    
    # Chart series
    daily_summaries = forecast_data['daily_summaries']
    chart_dates = [v['date'].strftime('%b %d (%a)') for v in daily_summaries.values()]
    chart_daily_totals = [v['total_projected_visits'] for v in daily_summaries.values()]
    
    # Specialty aggregated totals
    dept_totals = {}
    for item in forecast_data['forecasts']:
        d = item['department']
        dept_totals[d] = dept_totals.get(d, 0) + item['predicted_visits']
        
    chart_dept_names = list(dept_totals.keys())
    chart_dept_totals = list(dept_totals.values())
    
    staffing_recommendations = get_staffing_recommendations(forecast_data)

    context = {
        'days': days,
        'forecast_data': forecast_data,
        'staffing_recommendations': staffing_recommendations,
        'chart_dates': json.dumps(chart_dates),
        'chart_daily_totals': json.dumps(chart_daily_totals),
        'chart_dept_names': json.dumps(chart_dept_names),
        'chart_dept_totals': json.dumps(chart_dept_totals),
    }
    return render(request, 'ml_engine/demand_forecast.html', context)


def api_predict_duration(request):
    """
    AJAX endpoint returning dynamic ML duration prediction given patient attributes.
    """
    age = int(request.GET.get('age', 30))
    gender = request.GET.get('gender', 'M')
    department = request.GET.get('department', 'General Medicine')
    visit_type = request.GET.get('visit_type', 'first_visit')
    severity = request.GET.get('severity', 'mild')
    chronic = (request.GET.get('chronic') in ['1', 'true', 'True'])
    experience = int(request.GET.get('doctor_experience', 8))
    
    pred_mins = predict_consultation_duration(
        patient_age=age,
        patient_gender=gender,
        department=department,
        visit_type=visit_type,
        symptom_severity=severity,
        has_chronic_condition=chronic,
        doctor_experience_years=experience
    )
    
    return JsonResponse({'predicted_duration': pred_mins})
