import json
import datetime
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count

from accounts.models import UserProfile
from doctors.models import DoctorProfile
from appointments.models import Appointment, Payment
from .ml_service import predict_consultation_duration, forecast_appointment_demand

@login_required
def admin_dashboard_view(request):
    if not (request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'admin')):
        messages.error(request, "Administrator privileges required.")
        return redirect('accounts:dashboard')
        
    total_patients = UserProfile.objects.filter(role='patient').count()
    total_doctors = DoctorProfile.objects.count()
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
        'status_dict': json.dumps(status_dict),
        'dept_labels': json.dumps(dept_labels),
        'dept_values': json.dumps(dept_values),
        'recent_appointments': recent_appointments,
        'recent_payments': recent_payments,
    }
    return render(request, 'ml_engine/admin_dashboard.html', context)


@login_required
def admin_demand_forecast_view(request):
    if not (request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'admin')):
        messages.error(request, "Administrator privileges required.")
        return redirect('accounts:dashboard')
        
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
    
    context = {
        'days': days,
        'forecast_data': forecast_data,
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

