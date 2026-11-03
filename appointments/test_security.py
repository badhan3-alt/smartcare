import datetime

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserProfile
from appointments.forms import AppointmentBookingForm, RescheduleAppointmentForm
from appointments.models import Appointment, Payment
from appointments.queue_service import save_booked_appointment
from doctors.models import Department, DoctorProfile, DoctorSchedule


class AppointmentSecurityTests(TestCase):
    def setUp(self):
        department = Department.objects.create(name='Appointment Security', code='appointment-security')
        self.doctor_user = User.objects.create_user('appointment-doctor')
        UserProfile.objects.create(user=self.doctor_user, role='doctor', phone='01700000000')
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, department=department)
        self.patient = User.objects.create_user('appointment-patient')
        UserProfile.objects.create(user=self.patient, role='patient', phone='01700000001')
        self.date = datetime.date.today() + datetime.timedelta(days=7)
        DoctorSchedule.objects.create(doctor=self.doctor, day_of_week=self.date.weekday(), start_time=datetime.time(9), end_time=datetime.time(11), slot_duration_minutes=30)
        self.appointment = Appointment.objects.create(patient=self.patient, doctor=self.doctor, appointment_date=self.date, appointment_time=datetime.time(9), token_number=1)

    def test_appointment_and_queue_are_visible_only_to_patient_and_assigned_doctor(self):
        for actor in (self.patient, self.doctor_user):
            self.client.force_login(actor)
            self.assertEqual(self.client.get(reverse('appointments:queue_tracker', args=[self.appointment.pk])).status_code, 200)
            self.assertEqual(self.client.get(reverse('appointments:api_queue_status', args=[self.appointment.pk])).status_code, 200)
        for role in ('patient', 'doctor', 'admin', 'receptionist', 'hospital'):
            actor = User.objects.create_user('unrelated-' + role, is_staff=(role == 'admin'))
            UserProfile.objects.create(user=actor, role=role, phone='01700000002')
            self.client.force_login(actor)
            with self.subTest(role=role):
                self.assertEqual(self.client.get(reverse('appointments:queue_tracker', args=[self.appointment.pk])).status_code, 403)
                self.assertEqual(self.client.get(reverse('appointments:api_queue_status', args=[self.appointment.pk])).status_code, 403)

    def test_reception_changes_require_post_and_csrf(self):
        receptionist = User.objects.create_user('secure-reception')
        UserProfile.objects.create(user=receptionist, role='receptionist', phone='01700000003')
        self.client.force_login(receptionist)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(receptionist)
        for name, args in (('reception_checkin', [self.appointment.pk]), ('reception_queue_action', [self.appointment.pk, 'cancel'])):
            url = reverse('appointments:' + name, args=args)
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(csrf_client.post(url).status_code, 403)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'scheduled')

    def test_rescheduling_cannot_bypass_schedule_or_take_another_patients_slot(self):
        Appointment.objects.create(patient=self.patient, doctor=self.doctor, appointment_date=self.date, appointment_time=datetime.time(10), token_number=2)
        for appointment_time in ('08:00', '09:15', '10:00', '11:00', '09:30:01'):
            form = RescheduleAppointmentForm(data={'appointment_date': self.date, 'appointment_time': appointment_time}, appointment=self.appointment)
            self.assertFalse(form.is_valid(), appointment_time)
        form = RescheduleAppointmentForm(data={'appointment_date': self.date, 'appointment_time': '09:30'}, appointment=self.appointment)
        self.assertTrue(form.is_valid(), form.errors)

    def test_booking_rechecks_a_slot_after_form_validation(self):
        form = AppointmentBookingForm(data={
            'doctor': self.doctor.pk, 'appointment_date': self.date,
            'appointment_time': '09:30', 'visit_type': 'first_visit', 'symptom_severity': 'mild',
        })
        self.assertTrue(form.is_valid(), form.errors)
        Appointment.objects.create(patient=self.patient, doctor=self.doctor, appointment_date=self.date, appointment_time=datetime.time(9, 30), token_number=2)
        pending = form.save(commit=False)
        pending.patient = self.patient
        with self.assertRaises(ValidationError):
            save_booked_appointment(pending)
        self.assertEqual(Appointment.objects.filter(doctor=self.doctor, appointment_date=self.date, appointment_time=datetime.time(9, 30)).count(), 1)

    def test_patient_cannot_cancel_or_reschedule_ongoing_consultation(self):
        self.appointment.status = 'in_consultation'
        self.appointment.save()
        self.client.force_login(self.patient)
        self.client.post(reverse('appointments:cancel', args=[self.appointment.pk]), {'cancellation_reason': 'test'})
        self.client.post(reverse('appointments:reschedule', args=[self.appointment.pk]), {'appointment_date': self.date, 'appointment_time': '10:30'})
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'in_consultation')
        self.assertEqual(self.appointment.appointment_time, datetime.time(9))

    def test_patient_cannot_edit_another_patients_payment(self):
        other = User.objects.create_user('other-payment-patient')
        UserProfile.objects.create(user=other, role='patient', phone='01700000004')
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse('appointments:payment', args=[self.appointment.pk]), {'payment_method': 'cash'}).status_code, 404)
        self.assertFalse(Payment.objects.exists())

    def test_malformed_slot_api_input_returns_validation_error(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(reverse('appointments:available_slots'), {'doctor': 'invalid', 'date': self.date.isoformat()}).status_code, 400)

    def test_reception_rejects_invalid_patient_details_without_creating_user(self):
        receptionist = User.objects.create_user('registration-reception')
        UserProfile.objects.create(user=receptionist, role='receptionist', phone='01700000005')
        self.client.force_login(receptionist)
        response = self.client.post(reverse('reception:register_patient'), {
            'username': 'invalid-patient', 'first_name': 'Patient', 'email': 'invalid-email',
            'phone': 'not-a-phone', 'gender': 'invalid', 'date_of_birth': 'not-a-date',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='invalid-patient').exists())

    def test_reception_cannot_undo_ongoing_or_completed_consultation(self):
        receptionist = User.objects.create_user('status-reception')
        UserProfile.objects.create(user=receptionist, role='receptionist', phone='01700000006')
        self.client.force_login(receptionist)
        for status in ('in_consultation', 'completed'):
            self.appointment.status = status
            self.appointment.save()
            self.client.post(reverse('appointments:reception_checkin', args=[self.appointment.pk]))
            self.client.post(reverse('appointments:reception_queue_action', args=[self.appointment.pk, 'cancel']))
            self.appointment.refresh_from_db()
            self.assertEqual(self.appointment.status, status)
