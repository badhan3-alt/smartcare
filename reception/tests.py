from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import UserProfile


class ReceptionAppTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='reception-user', password='test-pass')
        UserProfile.objects.create(user=user, role='receptionist', phone='01700000000')
        self.client.force_login(user)

    def test_reception_app_pages_render(self):
        self.assertEqual(self.client.get('/reception/').status_code, 200)
        self.assertEqual(self.client.get('/reception/appointments/').status_code, 200)
        self.assertEqual(self.client.get('/reception/waiting/').status_code, 200)
        self.assertEqual(self.client.get('/reception/completed/').status_code, 200)
        self.assertEqual(self.client.get('/reception/doctors/').status_code, 200)
        self.assertEqual(self.client.get('/reception/patients/').status_code, 200)
        self.assertEqual(self.client.get('/reception/appointments/book/').status_code, 200)

    def test_reception_login_accepts_only_receptionist_accounts(self):
        self.client.logout()
        response = self.client.post('/reception/login/', {
            'username': 'reception-user',
            'password': 'test-pass',
        })
        self.assertRedirects(response, '/reception/')

        self.client.logout()
        patient = User.objects.create_user(username='patient-user', password='test-pass')
        UserProfile.objects.create(user=patient, role='patient', phone='01800000000')
        response = self.client.post('/reception/login/', {
            'username': 'patient-user',
            'password': 'test-pass',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid reception staff credentials.')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_reception_registration_requires_email_verification(self):
        self.client.logout()
        registration_page = self.client.get('/reception/register/')
        self.assertEqual(registration_page.status_code, 200)
        self.assertContains(registration_page, 'Account role')
        self.assertContains(registration_page, 'Receptionist')

        response = self.client.post('/reception/register/', {
            'first_name': 'Front',
            'last_name': 'Desk',
            'username': 'front-desk-2',
            'email': 'frontdesk2@example.com',
            'phone': '01900000000',
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
        })
        self.assertRedirects(response, reverse('accounts:verify_registration'))
        account = User.objects.get(username='front-desk-2')
        self.assertFalse(account.is_active)
        self.assertEqual(account.profile.role, 'receptionist')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Verify your SmartCare reception account', mail.outbox[0].subject)

        code = mail.outbox[0].body.split('code is: ')[1].splitlines()[0]
        response = self.client.post(reverse('accounts:verify_registration'), {
            'code': code,
        })
        self.assertRedirects(response, reverse('login'))
        account.refresh_from_db()
        self.assertFalse(account.is_active)

        account.is_active = True
        account.save(update_fields=['is_active'])
        response = self.client.post('/reception/login/', {
            'username': 'front-desk-2',
            'password': 'StrongPass123!',
        })
        self.assertRedirects(response, '/reception/')
        self.assertEqual(response.wsgi_request.user, account)
