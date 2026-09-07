import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import send_mail


def send_appointment_notification(subject, message, patient):
    """Send configured email and SMS notifications for an appointment."""
    channels = []
    if patient.email:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[patient.email],
            fail_silently=False,
        )
        channels.append('email')

    if patient.profile.phone and getattr(settings, 'SMARTCARE_SMS_WEBHOOK_URL', ''):
        payload = json.dumps({
            'to': patient.profile.phone,
            'message': message,
        }).encode('utf-8')
        request = urllib.request.Request(
            settings.SMARTCARE_SMS_WEBHOOK_URL,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f'SMS provider returned HTTP {response.status}.')
        except (urllib.error.URLError, TimeoutError) as error:
            raise RuntimeError('SMS provider request failed.') from error
        channels.append('sms')

    return channels
