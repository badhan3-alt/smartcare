import datetime
from unittest.mock import patch
from io import StringIO
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from accounts.models import UserProfile
from doctors.models import Department, DoctorProfile, DoctorSchedule
from appointments.forms import AppointmentBookingForm
from appointments.models import Appointment
from appointments.models import Payment
from appointments.queue_service import get_next_token_number, calculate_patient_queue_status, explain_queue_status

class AppointmentsTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Cardiology", code="cardiology")
        self.doc_user = User.objects.create_user(username="dr.cardio", password="password123")
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.dept,
            qualification="MBBS, MD",
            specialization="Cardiologist",
            experience_years=10,
            consultation_fee=700.0,
            room_number="Room 105"
        )
        self.patient = User.objects.create_user(username="patient_sam", password="password123")
        UserProfile.objects.create(user=self.patient, role="patient", gender="M")

    def test_token_sequencing(self):
        today = datetime.date.today()
        token1 = get_next_token_number(self.doctor, today)
        self.assertEqual(token1, 1)

        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=today,
            appointment_time=datetime.time(10, 0),
            token_number=token1,
            status="scheduled",
            predicted_duration_minutes=20.0
        )

        token2 = get_next_token_number(self.doctor, today)
        self.assertEqual(token2, 2)

    def test_available_slots_api_returns_schedule_and_booked_state(self):
        appointment_date = datetime.date.today() + datetime.timedelta(days=7)
        DoctorSchedule.objects.create(
            doctor=self.doctor,
            day_of_week=appointment_date.weekday(),
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0),
            slot_duration_minutes=30,
        )
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=appointment_date,
            appointment_time=datetime.time(9, 0),
            token_number=1,
            status='scheduled',
        )
        self.client.force_login(self.patient)

        response = self.client.get(reverse('appointments:available_slots'), {
            'doctor': self.doctor.id,
            'date': appointment_date.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['slots'], [
            {'value': '09:00', 'label': '9:00 AM', 'available': False},
            {'value': '09:30', 'label': '9:30 AM', 'available': True},
        ])

    def test_booking_form_rejects_time_outside_doctor_schedule(self):
        appointment_date = datetime.date.today() + datetime.timedelta(days=7)
        DoctorSchedule.objects.create(
            doctor=self.doctor,
            day_of_week=appointment_date.weekday(),
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0),
            slot_duration_minutes=30,
        )

        form = AppointmentBookingForm(data={
            'doctor': self.doctor.id,
            'appointment_date': appointment_date.isoformat(),
            'appointment_time': '11:00',
            'visit_type': 'first_visit',
            'symptom_severity': 'mild',
            'primary_symptom': '',
            'patient_notes': '',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('appointment_time', form.errors)

    def test_queue_status_wait_time(self):
        today = datetime.date.today()
        appt1 = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=today,
            appointment_time=datetime.time(10, 0),
            token_number=1,
            status="in_consultation",
            predicted_duration_minutes=20.0
        )

        patient2 = User.objects.create_user(username="patient_lisa", password="password123")
        UserProfile.objects.create(user=patient2, role="patient", gender="F")

        appt2 = Appointment.objects.create(
            patient=patient2,
            doctor=self.doctor,
            appointment_date=today,
            appointment_time=datetime.time(10, 30),
            token_number=2,
            status="scheduled",
            predicted_duration_minutes=15.0
        )

        status_p2 = calculate_patient_queue_status(appt2)
        self.assertEqual(status_p2['currently_serving_token'], 1)
        self.assertGreaterEqual(status_p2['estimated_wait_minutes'], 10)

        explanation = explain_queue_status(appt2)
        self.assertTrue(explanation)
        self.assertIn('patient', ' '.join(explanation).lower())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_appointment_reminder_command_sends_email_and_marks_flag(self):
        now = timezone.localtime()
        self.patient.email = 'patient@example.com'
        self.patient.save(update_fields=['email'])
        appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=(now + datetime.timedelta(hours=24)).date(),
            appointment_time=(now + datetime.timedelta(hours=24)).time().replace(microsecond=0),
            token_number=1,
            status='scheduled',
        )

        with patch(
            'appointments.management.commands.send_appointment_reminders.timezone.localtime',
            return_value=now,
        ):
            call_command('send_appointment_reminders', stdout=StringIO())

        appointment.refresh_from_db()
        self.assertTrue(appointment.reminder_24h_sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('24 hours', mail.outbox[0].subject)

    def test_queue_status_api_rejects_other_patient(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=datetime.date.today(),
            appointment_time=datetime.time(10, 0),
            token_number=1,
            status='scheduled',
        )
        other_patient = User.objects.create_user(username='other_patient', password='test-pass')
        UserProfile.objects.create(user=other_patient, role='patient', gender='F')
        self.client.force_login(other_patient)

        response = self.client.get(
            reverse('appointments:api_queue_status', args=[appointment.id])
        )

        self.assertEqual(response.status_code, 403)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_payment_requires_email_otp_before_completion(self):
        self.patient.email = 'patient@example.com'
        self.patient.save(update_fields=['email'])
        appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=datetime.date.today(),
            appointment_time=datetime.time(10, 0),
            token_number=1,
            status='scheduled',
            predicted_duration_minutes=20.0,
        )
        self.client.force_login(self.patient)

        response = self.client.post(
            f'/appointments/payment/{appointment.id}/',
            {'payment_method': 'bkash', 'transaction_id': 'TXN-123'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        payment = Payment.objects.get(appointment=appointment)
        self.assertEqual(payment.status, 'pending')
        code = mail.outbox[0].body.split('code is: ')[1].splitlines()[0]
        self.assertContains(response, 'Verify OTP')

        response = self.client.post(
            f'/appointments/payment/{appointment.id}/',
            {'action': 'verify_otp', 'otp': code},
        )
        self.assertRedirects(response, f'/appointments/queue/{appointment.id}/')
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'completed')
        self.assertIsNotNone(payment.paid_at)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('payment confirmation', mail.outbox[1].subject.lower())
        self.assertIn('has been confirmed', mail.outbox[1].body)

    def test_payment_page_renders_payment_method_logos(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=datetime.date.today(),
            appointment_time=datetime.time(10, 0),
            token_number=1,
            status='scheduled',
            predicted_duration_minutes=20.0,
        )
        self.client.force_login(self.patient)
        response = self.client.get(f'/appointments/payment/{appointment.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'bkash.svg')
        self.assertContains(response, 'nagad.svg')
        self.assertContains(response, 'rocket.svg')
        self.assertContains(response, 'card.svg')
        self.assertContains(response, 'cash.svg')
        self.assertContains(response, 'id="txnIdSection"')

    def test_reception_dashboard_and_patient_registration(self):
        receptionist = User.objects.create_user(username='frontdesk', password='test-pass')
        UserProfile.objects.create(user=receptionist, role='receptionist', gender='F')
        self.client.force_login(receptionist)

        response = self.client.get('/reception/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reception Dashboard')
        self.assertEqual(self.client.get('/appointments/reception/patients/').status_code, 200)
        self.assertEqual(self.client.get('/appointments/reception/appointments/book/').status_code, 200)

        response = self.client.post('/appointments/reception/patients/register/', {
            'first_name': 'Nabila',
            'last_name': 'Ahmed',
            'username': 'nabila.ahmed',
            'email': 'nabila@example.com',
            'phone': '01700000000',
            'gender': 'F',
        })
        registered = User.objects.get(username='nabila.ahmed')
        self.assertRedirects(
            response,
            f'/appointments/reception/patients/register/?created={registered.id}',
        )
        self.assertEqual(registered.profile.role, 'patient')
