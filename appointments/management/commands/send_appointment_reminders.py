import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from smtplib import SMTPException
from django.utils import timezone

from appointments.models import Appointment
from appointments.notification_service import send_appointment_notification


class Command(BaseCommand):
    help = 'Send one-time 24-hour and 2-hour appointment reminders.'

    def handle(self, *args, **options):
        now = timezone.localtime()
        sent = 0
        failed = 0
        for appointment in Appointment.objects.filter(
            status__in=['scheduled', 'waiting'],
            appointment_date__gte=now.date(),
        ).select_related('patient', 'doctor__user'):
            start = timezone.make_aware(
                datetime.datetime.combine(
                    appointment.appointment_date, appointment.appointment_time
                ),
                timezone.get_current_timezone(),
            )
            hours = (start - now).total_seconds() / 3600
            field = None
            label = None
            if 23 <= hours <= 25 and not appointment.reminder_24h_sent:
                field, label = 'reminder_24h_sent', '24 hours'
            elif 1 <= hours <= 3 and not appointment.reminder_2h_sent:
                field, label = 'reminder_2h_sent', '2 hours'
            if not field or not (
                appointment.patient.email
                or (
                    hasattr(appointment.patient, 'profile')
                    and appointment.patient.profile.phone
                    and getattr(settings, 'SMARTCARE_SMS_WEBHOOK_URL', '')
                )
            ):
                continue
            try:
                send_appointment_notification(
                    subject=f'SmartCare appointment reminder ({label})',
                    message=(
                        f'Your appointment with {appointment.doctor.full_name} is in {label}.\n'
                        f'Date: {appointment.appointment_date:%B %d, %Y}\n'
                        f'Time: {appointment.appointment_time:%I:%M %p}\n'
                        f'Token: #{appointment.token_number}\n'
                        f'Room: {appointment.doctor.room_number}\n'
                    ),
                    patient=appointment.patient,
                )
            except (SMTPException, OSError, RuntimeError, ValueError) as error:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(
                        f'Could not send {label} reminder for appointment '
                        f'#{appointment.id}: {error}'
                    )
                )
                continue
            setattr(appointment, field, True)
            appointment.save(update_fields=[field, 'updated_at'])
            sent += 1
        self.stdout.write(
            self.style.SUCCESS(
                f'Sent {sent} appointment reminder(s); {failed} failed.'
            )
        )
