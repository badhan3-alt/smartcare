import datetime
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from accounts.models import UserProfile
from doctors.models import Department, DoctorProfile
from appointments.models import Appointment
from appointments.models import Payment
from appointments.queue_service import get_next_token_number, calculate_patient_queue_status

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

