"""Reception desk application views.

The workflow implementation remains shared with appointments so patient booking,
queue tokens, and ML duration prediction use one consistent service path.
"""

import logging
import secrets
import time

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from smtplib import SMTPException

from accounts.models import UserProfile
from appointments.views import (
    reception_dashboard_view,
    reception_patient_search_view,
    reception_register_patient_view,
    reception_book_appointment_view,
    reception_checkin_view,
    reception_queue_action_view,
    reception_appointments_view,
    reception_waiting_view,
    reception_completed_view,
    reception_doctors_view,
)


dashboard_view = reception_dashboard_view
patient_search_view = reception_patient_search_view
register_patient_view = reception_register_patient_view
book_appointment_view = reception_book_appointment_view
checkin_view = reception_checkin_view
queue_action_view = reception_queue_action_view
appointments_view = reception_appointments_view
waiting_view = reception_waiting_view
completed_view = reception_completed_view
doctors_view = reception_doctors_view

logger = logging.getLogger(__name__)
REGISTRATION_CODE_SESSION_KEY = 'registration_verification'
REGISTRATION_CODE_TTL = 10 * 60


@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('reception:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        if not all([username, email, first_name, phone, password]):
            messages.error(request, 'Name, username, email, phone, and password are required.')
        elif password != password_confirm:
            messages.error(request, 'Passwords do not match.')
        elif User.objects.filter(username__iexact=username).exists():
            messages.error(request, 'That username is already in use.')
        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'That email is already registered.')
        else:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=False,
                )
                UserProfile.objects.create(
                    user=user,
                    role='receptionist',
                    phone=phone,
                    gender=request.POST.get('gender', 'O'),
                    address=request.POST.get('address', '').strip(),
                )
            code = f'{secrets.randbelow(1000000):06d}'
            request.session[REGISTRATION_CODE_SESSION_KEY] = {
                'user_id': user.id,
                'code': code,
                'expires_at': int(time.time()) + REGISTRATION_CODE_TTL,
            }
            request.session.modified = True
            try:
                send_mail(
                    subject='Verify your SmartCare reception account',
                    message=(
                        f'Hello {user.get_full_name() or user.username},\n\n'
                        f'Your SmartCare email verification code is: {code}\n\n'
                        'Verify your email before administrator approval. '
                        'This code expires in 10 minutes.\n\n'
                        'Thank you,\nSmartCare'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except (SMTPException, OSError, ValueError) as error:
                logger.exception('Reception registration email failed: %s', error)
                request.session.pop(REGISTRATION_CODE_SESSION_KEY, None)
                user.delete()
                messages.error(
                    request,
                    'We could not send the verification email. Configure the SMTP settings and try again.',
                )
            else:
                messages.success(request, 'A verification code has been sent to your email.')
                return redirect('accounts:verify_registration')

    return render(request, 'reception/register.html')


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'profile') and request.user.profile.role == 'receptionist':
            return redirect('reception:dashboard')
        messages.error(request, 'This login is only for authorized reception staff.')
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        pending_user = User.objects.filter(username__iexact=identifier).select_related('profile').first()
        user = authenticate(request, username=identifier, password=password)
        if (
            pending_user
            and not pending_user.is_active
            and hasattr(pending_user, 'profile')
            and pending_user.profile.role == 'receptionist'
            and pending_user.check_password(password)
        ):
            messages.warning(request, 'Your registration is pending administrator approval.')
        elif user and user.is_active and hasattr(user, 'profile') and user.profile.role == 'receptionist':
            login(request, user)
            messages.success(request, f'Welcome to the reception desk, {user.get_full_name() or user.username}.')
            return redirect('reception:dashboard')
        messages.error(request, 'Invalid reception staff credentials.')

    return render(request, 'reception/login.html')
