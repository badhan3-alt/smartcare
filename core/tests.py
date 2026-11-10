import datetime

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from accounts.models import UserProfile
from appointments.models import Appointment
from doctors.models import Department, DoctorProfile

class HomeViewSessionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='Password123!'
        )
        UserProfile.objects.create(user=self.user, role='patient')

    def test_entering_site_at_home_preserves_authenticated_session(self):
        # Log the user in
        login_success = self.client.login(username='testuser', password='Password123!')
        self.assertTrue(login_success)

        # Confirm the client session is currently authenticated
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirects to role-specific dashboard

        # A GET to the home page redirects without mutating authentication.
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('accounts:dashboard'), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_visiting_login_preserves_authenticated_session(self):
        self.client.login(username='testuser', password='Password123!')
        response = self.client.get(reverse('login'))
        self.assertRedirects(response, reverse('accounts:dashboard'), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)


class SearchSuggestionTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Cardiology', code='cardiology')
        self.doctor_user = User.objects.create_user(
            username='dr.cardiologist', first_name='Amina', last_name='Rahman',
            password='Password123!',
        )
        UserProfile.objects.create(user=self.doctor_user, role='doctor', phone='01700000001')
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user,
            department=self.department,
            qualification='MBBS, MD',
            specialization='Heart Care',
        )
        self.patient = User.objects.create_user(
            username='patient_sam', first_name='Sam', last_name='Hossain',
            password='Password123!',
        )
        UserProfile.objects.create(user=self.patient, role='patient', phone='01800000002')

    def test_public_doctor_suggestions_match_directory_fields(self):
        response = self.client.get(reverse('core:search_suggestions'), {
            'type': 'doctors', 'q': 'Cardio',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['value'], 'Cardiology')
        self.assertIn('Amina Rahman', response.json()['results'][0]['label'])

    def test_patient_suggestions_require_staff_role(self):
        response = self.client.get(reverse('core:search_suggestions'), {
            'type': 'admin-patients', 'q': 'Sam',
        })
        self.assertEqual(response.status_code, 403)

        admin = User.objects.create_user(username='portal-admin', password='Password123!')
        UserProfile.objects.create(user=admin, role='admin', phone='01700000003')
        Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            appointment_date=datetime.date.today(),
            appointment_time=datetime.time(9, 0),
            token_number=1,
        )
        self.client.force_login(admin)
        response = self.client.get(reverse('core:search_suggestions'), {
            'type': 'admin-patients', 'q': 'Sam',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['value'], 'Sam')

        response = self.client.get(reverse('core:search_suggestions'), {
            'type': 'admin-appointments', 'q': 'Amina',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('patient_sam', response.json()['results'][0]['label'])
        self.assertEqual(response.json()['results'][0]['value'], 'Amina')
        for route, suggestion_type in (
            ('admin_patient_list', 'admin-patients'),
            ('admin_appointment_list', 'admin-appointments'),
        ):
            page = self.client.get(reverse(route))
            self.assertContains(page, f'data-suggest-type="{suggestion_type}"')

    def test_doctor_suggestions_only_include_the_doctors_todays_patients(self):
        other_user = User.objects.create_user(
            username='dr.other', first_name='Other', password='Password123!',
        )
        UserProfile.objects.create(user=other_user, role='doctor', phone='01700000004')
        other_doctor = DoctorProfile.objects.create(
            user=other_user, department=self.department,
            qualification='MBBS', specialization='General Medicine',
        )
        for doctor, patient, token in (
            (self.doctor, self.patient, 1),
            (other_doctor, User.objects.create_user(
                username='another_sam', first_name='Sam', password='Password123!',
            ), 2),
        ):
            Appointment.objects.create(
                doctor=doctor,
                patient=patient,
                appointment_date=datetime.date.today(),
                appointment_time=datetime.time(9, token),
                token_number=token,
            )
        self.client.force_login(self.doctor_user)

        response = self.client.get(reverse('core:search_suggestions'), {
            'type': 'doctor-patients', 'metric': 'today', 'q': 'Sam',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)
        self.assertIn('patient_sam', response.json()['results'][0]['label'])
        page = self.client.get(reverse('doctors:today_patients'))
        self.assertContains(page, 'data-suggest-type="doctor-patients"')

    def test_reception_suggestions_support_the_patient_id_on_the_directory(self):
        receptionist = User.objects.create_user(username='front-desk', password='Password123!')
        UserProfile.objects.create(user=receptionist, role='receptionist', phone='01700000005')
        self.client.force_login(receptionist)

        response = self.client.get(reverse('core:search_suggestions'), {
            'type': 'reception-patients', 'q': f'SC-{self.patient.pk:05d}',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['value'], f'SC-{self.patient.pk:05d}')

        directory_response = self.client.get(reverse('appointments:reception_patients'), {
            'q': f'SC-{self.patient.pk:05d}',
        })
        self.assertContains(directory_response, 'Sam Hossain')
        self.assertContains(directory_response, 'data-suggest-type="reception-patients"')

    def test_short_queries_and_unknown_suggestion_types_are_handled(self):
        response = self.client.get(reverse('core:search_suggestions'), {
            'type': 'doctors', 'q': 'a',
        })
        self.assertEqual(response.json(), {'results': []})

        response = self.client.get(reverse('core:search_suggestions'), {
            'type': 'unknown', 'q': 'Sam',
        })
        self.assertEqual(response.status_code, 400)
