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
from django.core.exceptions import PermissionDenied, ValidationError
from django.conf import settings
from django.core.mail import send_mail
from smtplib import SMTPException
from django.db import transaction
from django.views.decorators.http import require_http_methods, require_POST
from .models import HospitalProfile, MedicalHistory, UserProfile
from .forms import MedicalHistoryForm, UserRegistrationForm
from doctors.models import DoctorProfile, DoctorSchedule

logger = logging.getLogger(__name__)

RESET_CODE_SESSION_KEY = 'password_reset'
REGISTRATION_CODE_SESSION_KEY = 'registration_verification'
RESET_CODE_TTL = 10 * 60


def _account_display_name(user):
    profile = getattr(user, 'profile', None)
    return profile.display_name if profile is not None else user.get_full_name() or user.username


def _send_registration_email(user, code, reception=False):
    send_mail(
        subject='Verify your SmartCare reception account' if reception else 'Verify your SmartCare account',
        message=(
            f'Hello {_account_display_name(user)},\n\n'
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
            f'Hello {_account_display_name(user)},\n\n'
            f'Your SmartCare password reset code is: {code}\n\n'
            'This code expires in 10 minutes. If you did not request a '
            'password reset, you can ignore this email.\n\n'
            'Thank you,\nSmartCare'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )

@require_http_methods(['GET', 'POST'])
def register_view(request, registration_data=None, template_name='accounts/register.html', reception=False):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
        
    if request.method == 'POST':
        data = registration_data if registration_data is not None else request.POST
        form = UserRegistrationForm(data)
        if form.is_valid():
            role = form.cleaned_data.get('role', 'patient')
            with transaction.atomic():
                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password'],
                    first_name='' if role == 'hospital' else form.cleaned_data['first_name'],
                    last_name='' if role == 'hospital' else form.cleaned_data['last_name'],
                )
                user.is_active = False
                user.save(update_fields=['is_active'])
                UserProfile.objects.create(
                    user=user,
                    role=role,
                    phone=form.cleaned_data['phone'],
                    gender='O' if role == 'hospital' else form.cleaned_data['gender'],
                    date_of_birth=None if role == 'hospital' else form.cleaned_data.get('date_of_birth'),
                    blood_group='' if role == 'hospital' else form.cleaned_data.get('blood_group', ''),
                    address=form.cleaned_data['hospital_address'] if role == 'hospital' else form.cleaned_data.get('address', ''),
                )

                if role == 'hospital':
                    HospitalProfile.objects.create(
                        user=user,
                        name=form.cleaned_data['hospital_name'],
                        registration_number=form.cleaned_data['registration_number'],
                        contact_person=form.cleaned_data.get('contact_person', ''),
                        website=form.cleaned_data.get('website', ''),
                    )
                elif role == 'doctor':
                    dept = form.cleaned_data['department']
                    doc_profile = DoctorProfile.objects.create(
                        user=user,
                        department=dept,
                        qualification=form.cleaned_data['qualification'],
                        specialization=form.cleaned_data['specialization'],
                        experience_years=form.cleaned_data.get('experience_years') or 5,
                        consultation_fee=form.cleaned_data.get('consultation_fee') or 500.00,
                        room_number=form.cleaned_data.get('room_number') or 'Room 101',
                        is_available=False
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
            request.session.cycle_key()
            request.session[REGISTRATION_CODE_SESSION_KEY] = {
                'user_id': user.pk, 'code': code,
                'expires_at': int(time.time()) + RESET_CODE_TTL,
                'attempts': 0,
            }
            try:
                _send_registration_email(user, code, reception=reception)
            except (SMTPException, OSError, ValueError):
                logger.warning('Registration verification email delivery failed.')
                request.session.pop(REGISTRATION_CODE_SESSION_KEY, None)
                user.delete()
                messages.error(
                    request,
                    'We could not send the verification email. Please try again later.',
                )
                return render(request, template_name, {'form': form})
            messages.success(request, 'A verification code has been sent to your email.')
            return redirect('accounts:verify_registration')
    else:
        form = UserRegistrationForm()
        
        if reception:
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
    return render(request, template_name, {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

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
            if not user_obj.is_active and user_obj.check_password(password):
                if getattr(getattr(user_obj, 'profile', None), 'role', None) == 'hospital':
                    messages.error(
                        request,
                        'Hospital accounts require email verification and administrator approval before you can sign in.',
                    )
                else:
                    messages.error(request, "Please verify your email with the code sent during registration.")
                return render(request, 'accounts/login.html')
            else:
                user = authenticate(request, username=user_obj.username, password=password)
        else:
            user = None
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {_account_display_name(user)}!")
            return redirect('accounts:dashboard')
        else:
            messages.error(request, "Invalid username/email or password.")
    return render(request, 'accounts/login.html')


def verify_registration_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    verification_data = request.session.get(REGISTRATION_CODE_SESSION_KEY)
    if not verification_data:
        messages.error(request, 'Please register first to request a verification code.')
        return redirect('register')

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        verification_data['attempts'] = verification_data.get('attempts', 0) + 1
        request.session[REGISTRATION_CODE_SESSION_KEY] = verification_data
        if verification_data['attempts'] > 5:
            request.session.pop(REGISTRATION_CODE_SESSION_KEY, None)
            messages.error(request, 'Too many invalid attempts. Please request a new code.')
        elif int(time.time()) > verification_data.get('expires_at', 0):
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
                user.profile.email_verified = True
                user.profile.save(update_fields=['email_verified'])
                if user.profile.role in {'receptionist', 'doctor', 'hospital'}:
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

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        request.session.pop(RESET_CODE_SESSION_KEY, None)
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

    reset_data = request.session.get(RESET_CODE_SESSION_KEY)
    if not reset_data:
        messages.error(request, 'Please request a password reset code first.')
        return redirect('accounts:forgot_password')

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        reset_data['attempts'] = reset_data.get('attempts', 0) + 1
        request.session[RESET_CODE_SESSION_KEY] = reset_data
        if reset_data['attempts'] > 5:
            request.session.pop(RESET_CODE_SESSION_KEY, None)
            messages.error(request, 'Too many invalid attempts. Please request a new reset code.')
        elif int(time.time()) > reset_data.get('expires_at', 0):
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


@require_POST
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
        elif role == 'hospital':
            return redirect('accounts:hospital_dashboard')
        elif role == 'admin' or user.is_superuser:
            return redirect('admin_dashboard')
        else:
            return redirect('patient_dashboard')
    elif user.is_superuser:
        return redirect('admin_dashboard')
    return redirect('patient_dashboard')


@login_required
def medical_history_view(request):
    if getattr(getattr(request.user, 'profile', None), 'role', None) != 'patient':
        raise PermissionDenied('Patient access is required.')
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
