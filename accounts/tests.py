from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from accounts.models import UserProfile
from doctors.models import Department

class AccountsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Cardiology", code="cardiology")

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_patient_registration_requires_email_verification(self):
        response = self.client.post(reverse('register'), {
            'role': 'patient',
            'username': 'testpatient',
            'first_name': 'Test',
            'last_name': 'Patient',
            'email': 'testpatient@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!',
            'phone': '01711223344',
            'gender': 'M',
            'blood_group': 'B+',
            'address': 'Sylhet'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        user = User.objects.filter(username='testpatient').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.profile.role, 'patient')
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Verify your SmartCare account', mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['testpatient@example.com'])
        code = mail.outbox[0].body.split('code is: ')[1].splitlines()[0]

        response = self.client.post(reverse('accounts:verify_registration'), {
            'code': code,
        })
        self.assertRedirects(response, reverse('login'))
        user.refresh_from_db()
        self.assertTrue(user.is_active)

        response = self.client.post(reverse('login'), {
            'username': 'testpatient',
            'password': 'Password123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:dashboard'))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_code_resets_password(self):
        user = User.objects.create_user(
            username='resetuser',
            email='reset@example.com',
            password='OldPassword123!',
        )

        response = self.client.post(reverse('accounts:forgot_password'), {
            'email': user.email,
        })
        self.assertRedirects(response, reverse('accounts:reset_password'))
        self.assertEqual(len(mail.outbox), 1)
        code = mail.outbox[0].body.split('code is: ')[1].splitlines()[0]

        response = self.client.post(reverse('accounts:reset_password'), {
            'code': code,
            'password': 'NewPassword123!',
            'confirm_password': 'NewPassword123!',
        })
        self.assertRedirects(response, reverse('login'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('NewPassword123!'))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_doctor_registration(self):
        response = self.client.post(reverse('register'), {
            'role': 'doctor',
            'username': 'testdoc',
            'first_name': 'Hasan',
            'last_name': 'Ali',
            'email': 'testdoc@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!',
            'phone': '01711556677',
            'gender': 'M',
            'department': self.dept.id,
            'qualification': 'MBBS, FCPS',
            'specialization': 'Clinical Cardiologist',
            'experience_years': 7,
            'consultation_fee': 600,
            'room_number': 'Room 103'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        user = User.objects.filter(username='testdoc').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.profile.role, 'doctor')
        self.assertTrue(hasattr(user, 'doctor_profile'))
        self.assertEqual(user.doctor_profile.department, self.dept)
