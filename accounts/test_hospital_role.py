from tempfile import TemporaryDirectory

from django.core import mail
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.forms import UserRegistrationForm
from accounts.models import HospitalProfile, MedicalReport, UserProfile
from doctors.models import Department


class HospitalRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username='hospital-approver', email='admin@example.com', password=None,
        )
        cls.hospital = User.objects.create_user(
            username='pending-hospital', password='HospitalPassword123!',
            is_active=False,
        )
        UserProfile.objects.create(
            user=cls.hospital, role='hospital', phone='01711223344', email_verified=True,
        )
        cls.patient = User.objects.create_user(username='approval-patient')
        UserProfile.objects.create(user=cls.patient, role='patient', phone='01711223345')
        cls.department = Department.objects.create(name='Hospital Role Tests', code='hospital-role-tests')

    def hospital_registration_data(self, **kwargs):
        return {
            'role': 'hospital',
            'username': 'registered-hospital',
            'email': 'reports@example.com',
            'password': 'HospitalPassword123!',
            'confirm_password': 'HospitalPassword123!',
            'phone': '01711223346',
            'hospital_name': 'Green Valley Medical Centre',
            'registration_number': 'HOSP-2026-1024',
            'hospital_address': '24 Hospital Road, Sylhet',
            'contact_person': 'Nusrat Ahmed',
            'website': 'https://hospital.example.com',
            **kwargs,
        }

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_hospital_registration_and_email_verification_require_approval(self):
        response = self.client.get(reverse('register'))
        self.assertContains(response, 'Hospital / Report Upload')
        response = self.client.post(reverse('register'), self.hospital_registration_data())
        self.assertRedirects(response, reverse('accounts:verify_registration'))
        hospital = User.objects.get(username='registered-hospital')
        self.assertEqual(hospital.profile.role, 'hospital')
        self.assertEqual(hospital.first_name, '')
        self.assertEqual(hospital.last_name, '')
        self.assertEqual(hospital.profile.gender, 'O')
        self.assertIsNone(hospital.profile.date_of_birth)
        self.assertEqual(hospital.profile.blood_group, '')
        self.assertEqual(hospital.profile.address, '24 Hospital Road, Sylhet')
        organization = hospital.hospital_profile
        self.assertEqual(organization.name, 'Green Valley Medical Centre')
        self.assertEqual(organization.registration_number, 'HOSP-2026-1024')
        self.assertEqual(organization.contact_person, 'Nusrat Ahmed')
        self.assertEqual(organization.website, 'https://hospital.example.com')
        self.assertEqual(hospital.profile.display_name, organization.name)
        self.assertFalse(hospital.is_active)
        self.assertFalse(hasattr(hospital, 'doctor_profile'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Hello Green Valley Medical Centre,', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['reports@example.com'])

        code = self.client.session['registration_verification']['code']
        response = self.client.post(reverse('accounts:verify_registration'), {'code': code})
        self.assertRedirects(response, reverse('login'))
        hospital.refresh_from_db()
        self.assertFalse(hospital.is_active)
        self.assertNotIn('registration_verification', self.client.session)

    def test_hospital_organization_and_shared_account_fields_are_required(self):
        for field in (
            'hospital_name', 'registration_number', 'hospital_address',
            'username', 'email', 'phone', 'password', 'confirm_password',
        ):
            with self.subTest(field=field):
                data = self.hospital_registration_data()
                data.pop(field)
                form = UserRegistrationForm(data)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
        self.assertFalse(User.objects.filter(username='registered-hospital').exists())

    def test_hospital_website_must_be_a_valid_url(self):
        form = UserRegistrationForm(self.hospital_registration_data(website='not a website'))
        self.assertFalse(form.is_valid())
        self.assertIn('website', form.errors)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_hospital_optional_organization_fields_can_be_omitted(self):
        data = self.hospital_registration_data()
        data.pop('contact_person')
        data.pop('website')
        response = self.client.post(reverse('register'), data)
        self.assertRedirects(response, reverse('accounts:verify_registration'))
        organization = HospitalProfile.objects.get(user__username='registered-hospital')
        self.assertEqual(organization.contact_person, '')
        self.assertEqual(organization.website, '')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_hospital_ignores_personal_and_clinical_values(self):
        response = self.client.post(reverse('register'), self.hospital_registration_data(
            first_name='Forged' * 30, last_name='Personal' * 30,
            gender='invalid', date_of_birth='invalid', blood_group='invalid',
            address='Unrelated personal address', department='999999',
            qualification='MBBS', specialization='Cardiology',
            experience_years='invalid', consultation_fee='invalid',
        ))
        self.assertRedirects(response, reverse('accounts:verify_registration'))
        hospital = User.objects.get(username='registered-hospital')
        self.assertEqual(hospital.first_name, '')
        self.assertEqual(hospital.last_name, '')
        self.assertEqual(hospital.profile.gender, 'O')
        self.assertIsNone(hospital.profile.date_of_birth)
        self.assertEqual(hospital.profile.blood_group, '')
        self.assertEqual(hospital.profile.address, '24 Hospital Road, Sylhet')
        self.assertFalse(hasattr(hospital, 'doctor_profile'))

    def test_person_roles_still_require_first_name_last_name_and_gender(self):
        for role in ('patient', 'doctor', 'receptionist'):
            for missing_field in ('first_name', 'last_name', 'gender'):
                with self.subTest(role=role, missing_field=missing_field):
                    data = self.hospital_registration_data(
                        role=role, first_name='Test', last_name='Person', gender='F',
                        department=self.department.pk, qualification='MBBS', specialization='Medicine',
                    )
                    data.pop(missing_field)
                    form = UserRegistrationForm(data)
                    self.assertFalse(form.is_valid())
                    self.assertIn(missing_field, form.errors)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_nonhospital_registration_ignores_organization_fields(self):
        response = self.client.post(reverse('register'), self.hospital_registration_data(
            role='patient', first_name='Samira', last_name='Akter', gender='F',
            date_of_birth='1995-03-15', blood_group='B+', address='Patient home address',
            hospital_name='x' * 250, registration_number='x' * 150,
            website='not a website',
        ))
        self.assertRedirects(response, reverse('accounts:verify_registration'))
        patient = User.objects.get(username='registered-hospital')
        self.assertEqual(patient.first_name, 'Samira')
        self.assertEqual(patient.last_name, 'Akter')
        self.assertEqual(patient.profile.display_name, 'Samira Akter')
        self.assertEqual(patient.profile.gender, 'F')
        self.assertEqual(patient.profile.date_of_birth.isoformat(), '1995-03-15')
        self.assertEqual(patient.profile.blood_group, 'B+')
        self.assertEqual(patient.profile.address, 'Patient home address')
        self.assertFalse(HospitalProfile.objects.filter(user=patient).exists())

    def test_hospital_metadata_appears_in_admin_approval_request(self):
        HospitalProfile.objects.create(
            user=self.hospital, name='Regional Hospital Organization',
            registration_number='REG-HOSP-2026', contact_person='Hospital Contact',
            website='https://regional.example.com',
        )
        UserProfile.objects.filter(user=self.hospital).update(address='Hospital administration address')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin_receptionist_requests'))
        self.assertContains(response, 'Regional Hospital Organization')
        self.assertContains(response, 'REG-HOSP-2026')
        self.assertContains(response, 'Hospital administration address')

    def test_hospital_name_is_used_in_navigation_and_report_attribution(self):
        organization = HospitalProfile.objects.create(
            user=self.hospital, name='Regional Hospital Organization',
            registration_number='REG-HOSP-2026',
        )
        self.hospital.is_active = True
        self.hospital.save(update_fields=['is_active'])
        self.client.force_login(self.hospital)
        response = self.client.get(reverse('accounts:hospital_dashboard'))
        self.assertContains(response, organization.name)
        with TemporaryDirectory() as directory, override_settings(SMARTCARE_REPORT_ROOT=directory):
            MedicalReport.objects.create(
                patient=self.patient, uploaded_by=self.hospital,
                title='Organization attribution report', original_filename='report.pdf',
                file=SimpleUploadedFile('report.pdf', b'%PDF-1.7\nReport\n%%EOF'),
            )
            self.client.force_login(self.patient)
            response = self.client.get(reverse('accounts:reports'))
            self.assertContains(response, 'by ' + organization.name)

    def test_pending_hospital_cannot_login_and_gets_approval_message(self):
        response = self.client.post(reverse('login'), {
            'username': self.hospital.username,
            'password': 'HospitalPassword123!',
        })
        self.assertContains(response, 'administrator approval')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_admin_can_approve_hospital_then_hospital_can_login(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('approve_receptionist', args=[self.hospital.pk]))
        self.assertRedirects(response, reverse('admin_receptionist_requests'))
        self.hospital.refresh_from_db()
        self.assertTrue(self.hospital.is_active)
        self.client.logout()

        response = self.client.post(reverse('login'), {
            'username': self.hospital.username,
            'password': 'HospitalPassword123!',
        })
        self.assertRedirects(response, reverse('accounts:dashboard'), fetch_redirect_response=False)
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertRedirects(response, reverse('accounts:hospital_dashboard'), fetch_redirect_response=False)

    def test_patient_cannot_approve_or_reject_hospital(self):
        self.client.force_login(self.patient)
        for route in ('approve_receptionist', 'reject_receptionist'):
            with self.subTest(route=route):
                response = self.client.post(reverse(route, args=[self.hospital.pk]))
                self.assertRedirects(response, reverse('accounts:dashboard'), fetch_redirect_response=False)
                self.hospital.refresh_from_db()
                self.assertFalse(self.hospital.is_active)

    def test_staff_requests_list_includes_hospital_and_admin_can_reject(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin_receptionist_requests'))
        self.assertContains(response, self.hospital.username)
        self.assertContains(response, 'Hospital')
        self.assertIn(self.hospital.profile, response.context['requests'])

        response = self.client.post(reverse('reject_receptionist', args=[self.hospital.pk]))
        self.assertRedirects(response, reverse('admin_receptionist_requests'))
        self.assertFalse(User.objects.filter(pk=self.hospital.pk).exists())
