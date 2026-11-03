import datetime

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserProfile
from appointments.models import Appointment, PatientFeedback
from doctors.models import Department, DoctorProfile, DoctorSchedule


class DoctorSecurityTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Security Clinic', code='security-clinic')
        self.doctor_user = User.objects.create_user('security-doctor')
        UserProfile.objects.create(user=self.doctor_user, role='doctor', phone='01700000000')
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, department=self.department)
        self.patient = User.objects.create_user('security-patient')
        UserProfile.objects.create(user=self.patient, role='patient', phone='01700000001')
        self.appointment = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor, appointment_date=datetime.date.today(),
            appointment_time=datetime.time(10), token_number=1,
        )
        self.client.force_login(self.doctor_user)

    def test_clinical_mutations_reject_get_and_missing_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.doctor_user)
        for name in ('call_patient', 'start_consultation', 'complete_consultation', 'no_show', 'open_telemedicine'):
            url = reverse('doctors:' + name, args=[self.appointment.pk])
            with self.subTest(name=name):
                self.assertEqual(self.client.get(url).status_code, 405)
                self.assertEqual(csrf_client.post(url).status_code, 403)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'scheduled')
        self.assertIsNone(self.appointment.consultation_started_at)
        self.assertFalse(self.appointment.telemedicine_enabled)

    def test_csrf_protected_call_can_be_used_by_assigned_doctor(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.doctor_user)
        response = client.get(reverse('doctors:queue_console'))
        self.assertContains(response, 'csrfmiddlewaretoken')
        token = client.cookies['csrftoken'].value
        response = client.post(reverse('doctors:call_patient', args=[self.appointment.pk]), HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'waiting')

    def test_other_doctor_cannot_change_or_read_patient_consultation(self):
        other = User.objects.create_user('unrelated-doctor')
        UserProfile.objects.create(user=other, role='doctor', phone='01700000002')
        DoctorProfile.objects.create(user=other, department=self.department)
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse('doctors:start_consultation', args=[self.appointment.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('appointments:queue_tracker', args=[self.appointment.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('appointments:api_queue_status', args=[self.appointment.pk])).status_code, 403)

    def test_completed_consultation_cannot_be_reopened_or_overwritten(self):
        self.appointment.status = 'completed'
        self.appointment.doctor_notes = 'Recorded clinical outcome'
        self.appointment.save()
        for name in ('call_patient', 'start_consultation', 'no_show', 'complete_consultation'):
            self.client.post(reverse('doctors:' + name, args=[self.appointment.pk]), {
                'actual_duration_minutes': 30, 'doctor_notes': 'Overwritten',
            })
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'completed')
        self.assertEqual(self.appointment.doctor_notes, 'Recorded clinical outcome')

    def test_invalid_consultation_duration_does_not_complete_visit(self):
        self.appointment.status = 'in_consultation'
        self.appointment.save()
        for duration in ('-1', '0', '481', 'NaN', 'inf'):
            self.client.post(reverse('doctors:complete_consultation', args=[self.appointment.pk]), {
                'actual_duration_minutes': duration,
            })
            self.appointment.refresh_from_db()
            self.assertEqual(self.appointment.status, 'in_consultation')

    def test_patient_role_with_doctor_profile_has_no_clinical_access(self):
        UserProfile.objects.filter(user=self.doctor_user).update(role='patient')
        self.assertEqual(self.client.get(reverse('doctors:dashboard')).status_code, 403)
        self.assertEqual(self.client.post(reverse('doctors:call_patient', args=[self.appointment.pk])).status_code, 403)

    def test_unapproved_doctor_not_public_or_bookable(self):
        self.doctor_user.is_active = False
        self.doctor_user.save(update_fields=['is_active'])
        self.client.logout()
        self.assertNotContains(self.client.get(reverse('doctor_list')), self.doctor_user.username)
        self.assertEqual(self.client.get(reverse('doctor_detail', args=[self.doctor.pk])).status_code, 404)

    def test_schedule_get_is_read_only(self):
        self.assertEqual(self.client.get(reverse('doctors:schedule')).status_code, 200)
        self.assertFalse(DoctorSchedule.objects.filter(doctor=self.doctor).exists())

    def test_public_reviews_do_not_disclose_patient_identity(self):
        self.patient.first_name = 'PrivatePatientName'
        self.patient.last_name = 'Confidential'
        self.patient.save()
        PatientFeedback.objects.create(appointment=self.appointment, rating=5, comment='Clear explanation.')
        self.client.logout()
        response = self.client.get(reverse('doctor_detail', args=[self.doctor.pk]))
        self.assertContains(response, 'Verified patient')
        self.assertNotContains(response, self.patient.first_name)
        self.assertNotContains(response, self.patient.username)
