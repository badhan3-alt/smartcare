from django.shortcuts import render, redirect
from django.db.models import Count
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

