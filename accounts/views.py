import datetime
import logging
import secrets
import time
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.mail import send_mail
from smtplib import SMTPException
from django.db import transaction
from .models import MedicalHistory, UserProfile
from .forms import MedicalHistoryForm, UserRegistrationForm
from doctors.models import DoctorProfile, DoctorSchedule

logger = logging.getLogger(__name__)

RESET_CODE_SESSION_KEY = 'password_reset'
REGISTRATION_CODE_SESSION_KEY = 'registration_verification'
RESET_CODE_TTL = 10 * 60


def _send_registration_email(user, code):
    send_mail(
        subject='Verify your SmartCare account',
        message=(
            f'Hello {user.get_full_name() or user.username},\n\n'
            f'Your SmartCare verification code is: {code}\n\n'
            'Enter this code on the verification page to activate your account. '
            'This code expires in 10 minutes.\n\n'
            'Thank you,\nSmartCare'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def _send_password_reset_code(user, code):
    send_mail(
        subject='Your SmartCare password reset code',
        message=(
            f'Hello {user.get_full_name() or user.username},\n\n'
            f'Your SmartCare password reset code is: {code}\n\n'
            'This code expires in 10 minutes. If you did not request a '
            'password reset, you can ignore this email.\n\n'
            'Thank you,\nSmartCare'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )

def register_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
        logout(request)
        
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            role = form.cleaned_data.get('role', 'patient')
            with transaction.atomic():
                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password'],
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name']
                )
                user.is_active = False
                user.save(update_fields=['is_active'])
                if role == 'admin':
                    user.is_staff = True
                    user.save()

                UserProfile.objects.create(
                    user=user,
                    role=role,
                    phone=form.cleaned_data['phone'],
                    gender=form.cleaned_data['gender'],
                    date_of_birth=form.cleaned_data.get('date_of_birth'),
                    blood_group=form.cleaned_data.get('blood_group', ''),
                    address=form.cleaned_data.get('address', '')
                )

                if role == 'doctor':
                    dept = form.cleaned_data['department']
                    doc_profile = DoctorProfile.objects.create(
                        user=user,
                        department=dept,
                        qualification=form.cleaned_data['qualification'],
                        specialization=form.cleaned_data['specialization'],
                        experience_years=form.cleaned_data.get('experience_years') or 5,
                        consultation_fee=form.cleaned_data.get('consultation_fee') or 500.00,
                        room_number=form.cleaned_data.get('room_number') or 'Room 101',
                        is_available=True
                    )
                    for day_idx in range(5): # Mon-Fri
                        DoctorSchedule.objects.create(
                            doctor=doc_profile,
                            day_of_week=day_idx,
                            start_time=datetime.time(9, 0),
                            end_time=datetime.time(17, 0),
                            slot_duration_minutes=20,
                            is_active=True
                        )

            code = f'{secrets.randbelow(1000000):06d}'
            request.session[REGISTRATION_CODE_SESSION_KEY] = {
                'user_id': user.id,
                'code': code,
                'expires_at': int(time.time()) + RESET_CODE_TTL,
            }
            request.session.modified = True
            try:
                _send_registration_email(user, code)
            except (SMTPException, OSError, ValueError) as error:
                logger.exception('Registration verification email failed: %s', error)
                user.delete()
                messages.error(
                    request,
                    'We could not send the verification email. Configure EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in .env, then restart the server.',
                )
                return render(request, 'accounts/register.html', {'form': form})
            messages.success(request, 'A verification code has been sent to your email.')
            return redirect('accounts:verify_registration')
    else:
        form = UserRegistrationForm()
        
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
        logout(request)

    if request.method == 'POST':
        identifier = request.POST.get('username')
        password = request.POST.get('password')
        # Allow login with email address (case‑insensitive)
        user_obj = None
        if identifier:
            if '@' in identifier:
                user_obj = User.objects.filter(email__iexact=identifier).first()
            else:
                # case‑insensitive username lookup
                user_obj = User.objects.filter(username__iexact=identifier).first()
        if user_obj:
            if not user_obj.is_active:
                messages.error(request, "Please verify your email with the code sent during registration.")
                return render(request, 'accounts/login.html')
            else:
                user = authenticate(request, username=user_obj.username, password=password)
        else:
            user = None
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
            return redirect('accounts:dashboard')
        else:
            messages.error(request, "Invalid username/email or password.")
    return render(request, 'accounts/login.html')


def verify_registration_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
        logout(request)

    verification_data = request.session.get(REGISTRATION_CODE_SESSION_KEY)
    if not verification_data:
        messages.error(request, 'Please register first to request a verification code.')
        return redirect('register')

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        if int(time.time()) > verification_data.get('expires_at', 0):
            request.session.pop(REGISTRATION_CODE_SESSION_KEY, None)
            messages.error(request, 'This verification code has expired. Please register again.')
        elif code != verification_data.get('code'):
            messages.error(request, 'The verification code is invalid.')
        else:
            user = User.objects.filter(id=verification_data.get('user_id')).first()
            if not user:
                request.session.pop(REGISTRATION_CODE_SESSION_KEY, None)
                messages.error(request, 'This verification request is no longer valid.')
            else:
                if user.profile.role in {'receptionist', 'doctor'}:
                    messages.success(
                        request,
                        'Your email is verified. A SmartCare administrator must approve your account before you can sign in.',
                    )
                else:
                    user.is_active = True
                    user.save(update_fields=['is_active'])
                    messages.success(request, 'Your account is verified. You can now sign in.')
                request.session.pop(REGISTRATION_CODE_SESSION_KEY, None)
                return redirect('login')

    return render(request, 'accounts/verify_registration.html')


def forgot_password_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
        logout(request)

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        user = User.objects.filter(email__iexact=email).first()
        if user:
            code = f'{secrets.randbelow(1000000):06d}'
            request.session[RESET_CODE_SESSION_KEY] = {
                'user_id': user.id,
                'code': code,
                'expires_at': int(time.time()) + RESET_CODE_TTL,
            }
            request.session.modified = True
            try:
                _send_password_reset_code(user, code)
            except (SMTPException, OSError, ValueError) as error:
                logger.exception('Password reset email failed: %s', error)
                request.session.pop(RESET_CODE_SESSION_KEY, None)
                messages.error(
                    request,
                    'We could not send the reset email. Configure EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in .env, then restart the server.',
                )
                return redirect('accounts:forgot_password')
        messages.info(
            request,
            'If an account uses that email, a password reset code has been sent.',
        )
        return redirect('accounts:reset_password')

    return render(request, 'accounts/forgot_password.html')


def reset_password_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
        logout(request)

    reset_data = request.session.get(RESET_CODE_SESSION_KEY)
    if not reset_data:
        messages.error(request, 'Please request a password reset code first.')
        return redirect('accounts:forgot_password')

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        if int(time.time()) > reset_data.get('expires_at', 0):
            request.session.pop(RESET_CODE_SESSION_KEY, None)
            messages.error(request, 'This reset code has expired. Please request a new one.')
        elif code != reset_data.get('code'):
            messages.error(request, 'The reset code is invalid.')
        elif password != confirm_password:
            messages.error(request, 'Passwords do not match.')
        else:
            user = User.objects.filter(id=reset_data.get('user_id')).first()
            if not user:
                request.session.pop(RESET_CODE_SESSION_KEY, None)
                messages.error(request, 'This reset request is no longer valid.')
            else:
                try:
                    validate_password(password, user)
                except ValidationError as error:
                    for message in error.messages:
                        messages.error(request, message)
                else:
                    user.set_password(password)
                    user.save(update_fields=['password'])
                    request.session.pop(RESET_CODE_SESSION_KEY, None)
                    messages.success(request, 'Your password has been reset. You can now sign in.')
                    return redirect('login')

    return render(request, 'accounts/reset_password.html')


def logout_view(request):
    logout(request)
    messages.info(request, "You have been safely logged out.")
    return redirect('core:home')


@login_required
def dashboard_view(request):
    user = request.user
    if hasattr(user, 'profile'):
        role = user.profile.role
        if role == 'doctor':
            return redirect('doctor_dashboard')
        elif role == 'receptionist':
            return redirect('reception:dashboard')
        elif role == 'admin' or user.is_superuser:
            return redirect('admin_dashboard')
        else:
            return redirect('patient_dashboard')
    elif user.is_superuser:
        return redirect('admin_dashboard')
    return redirect('patient_dashboard')


@login_required
def medical_history_view(request):
    if hasattr(request.user, 'doctor_profile'):
        messages.error(request, 'Only patients can edit medical history.')
        return redirect('doctor_dashboard')
    history, _ = MedicalHistory.objects.get_or_create(patient=request.user)
    if request.method == 'POST':
        form = MedicalHistoryForm(request.POST, instance=history)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your medical history has been updated.')
            return redirect('accounts:medical_history')
    else:
        form = MedicalHistoryForm(instance=history)
    return render(
        request, 'accounts/medical_history.html',
        {'form': form, 'history': history},
    )
