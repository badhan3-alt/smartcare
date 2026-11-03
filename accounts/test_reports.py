import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import MedicalReport, UserProfile
from appointments.models import Appointment
from doctors.models import Department, DoctorProfile


class MedicalReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.patient = cls.make_user('report-patient', 'patient', first_name='Amina', last_name='Rahman')
        cls.other_patient = cls.make_user('other-report-patient', 'patient', first_name='Rafiq', last_name='Karim')
        cls.hospital = cls.make_user('report-hospital', 'hospital')
        cls.other_hospital = cls.make_user('other-report-hospital', 'hospital')
        cls.receptionist = cls.make_user('report-receptionist', 'receptionist')
        cls.administrator = cls.make_user('report-administrator', 'admin')
        cls.doctor_user = cls.make_user('report-doctor', 'doctor')
        cls.other_doctor_user = cls.make_user('other-report-doctor', 'doctor')
        cls.staff_patient = cls.make_user('staff-patient', 'patient', is_staff=True)
        cls.superuser = User.objects.create_superuser(
            username='report-superuser', email='reports@example.com', password=None,
        )
        department = Department.objects.create(name='Report Department', code='reports')
        cls.doctor = DoctorProfile.objects.create(
            user=cls.doctor_user, department=department,
            qualification='MBBS', specialization='General Medicine',
        )
        cls.other_doctor = DoctorProfile.objects.create(
            user=cls.other_doctor_user, department=department,
            qualification='MBBS', specialization='General Medicine',
        )
        cls.consultation = cls.make_consultation(cls.patient, cls.doctor, 'completed')
        cls.other_doctor_consultation = cls.make_consultation(cls.patient, cls.other_doctor, 'completed')
        cls.other_patient_consultation = cls.make_consultation(cls.other_patient, cls.doctor, 'in_consultation')

    @staticmethod
    def make_user(username, role, **kwargs):
        user = User.objects.create_user(username=username, **kwargs)
        UserProfile.objects.create(user=user, role=role, phone='01711223344')
        return user

    @staticmethod
    def make_consultation(patient, doctor, status):
        return Appointment.objects.create(
            patient=patient, doctor=doctor, status=status,
            appointment_date=datetime.date(2026, 10, 30),
            appointment_time=datetime.time(10),
            token_number=doctor.appointments.count() + 1,
        )

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.report_root = Path(directory.name)
        settings_override = override_settings(SMARTCARE_REPORT_ROOT=directory.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    @staticmethod
    def pdf_document():
        objects = (
            b'<< /Type /Catalog /Pages 2 0 R >>',
            b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>',
        )
        document = b'%PDF-1.7\n'
        offsets = [0]
        for number, obj in enumerate(objects, 1):
            offsets.append(len(document))
            document += f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n'
        xref_offset = len(document)
        document += b'xref\n0 4\n0000000000 65535 f \n'
        for offset in offsets[1:]:
            document += f'{offset:010d} 00000 n \n'.encode()
        document += b'trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n'
        return document + str(xref_offset).encode() + b'\n%%EOF\n'

    @classmethod
    def uploaded_file(cls, name='blood-test.pdf', content=None):
        if content is None:
            content = cls.pdf_document()
        return SimpleUploadedFile(name, content, content_type='application/pdf')

    def create_report(self, patient=None, title='Blood test results', **kwargs):
        fields = {
            'patient': patient or self.patient, 'uploaded_by': self.hospital,
            'consultation': self.consultation, 'title': title,
            'report_date': datetime.date(2026, 10, 30),
            'notes': 'Collected at the hospital laboratory.',
            'file': self.uploaded_file(), 'original_filename': 'blood-test.pdf',
        }
        fields.update(kwargs)
        return MedicalReport.objects.create(**fields)

    def upload_url(self, patient=None):
        return reverse('accounts:patient_reports', args=[(patient or self.patient).pk])

    def download_url(self, report):
        return reverse('accounts:report_download', args=[report.pk])

    def delete_url(self, report):
        return reverse('accounts:report_delete', args=[report.pk])

    def upload_data(self, **kwargs):
        return {
            'title': 'Hospital blood test', 'consultation': self.consultation.pk,
            'file': self.uploaded_file(), **kwargs,
        }

    def test_all_report_routes_require_login(self):
        report = self.create_report()
        for url in (
            reverse('accounts:reports'), self.upload_url(),
            reverse('accounts:hospital_dashboard'), reverse('accounts:doctor_reports'),
            reverse('accounts:consultation_reports', args=[self.consultation.pk]),
            self.download_url(report), self.delete_url(report),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response.url)

    def test_hospital_upload_sets_recipient_and_uploader_from_request(self):
        self.client.force_login(self.hospital)
        response = self.client.post(self.upload_url(), self.upload_data(
            report_date='2026-10-30', notes='Hospital laboratory result.',
            patient=self.other_patient.pk, uploaded_by=self.other_hospital.pk,
        ))
        self.assertEqual(response.status_code, 302)
        report = MedicalReport.objects.get()
        self.assertEqual(report.patient, self.patient)
        self.assertEqual(report.uploaded_by, self.hospital)
        self.assertEqual(report.consultation, self.consultation)
        self.assertEqual(report.title, 'Hospital blood test')
        self.assertEqual(report.report_date, datetime.date(2026, 10, 30))
        self.assertEqual(report.notes, 'Hospital laboratory result.')
        self.assertEqual(report.original_filename, 'blood-test.pdf')
        self.assertTrue(report.file.storage.exists(report.file.name))
        self.assertTrue(Path(report.file.path).is_relative_to(self.report_root))
        self.assertNotEqual(Path(report.file.name).name, 'blood-test.pdf')
        with self.assertRaises(ValueError):
            _ = report.file.url

    def test_upload_accepts_active_and_completed_consultations(self):
        active = self.make_consultation(self.patient, self.doctor, 'in_consultation')
        self.client.force_login(self.hospital)
        for consultation in (active, self.consultation):
            with self.subTest(status=consultation.status):
                response = self.client.post(self.upload_url(), self.upload_data(
                    title=f'Report for {consultation.pk}', consultation=consultation.pk,
                ))
                self.assertEqual(response.status_code, 302)
                report = MedicalReport.objects.get(title=f'Report for {consultation.pk}')
                self.assertEqual(report.consultation, consultation)
                self.assertIsNone(report.report_date)

    def test_consultation_choices_are_patient_specific_and_eligible(self):
        scheduled = self.make_consultation(self.patient, self.doctor, 'scheduled')
        self.client.force_login(self.hospital)
        response = self.client.get(self.upload_url())
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        choices = set(form.fields['consultation'].queryset.values_list('pk', flat=True))
        self.assertIn(self.consultation.pk, choices)
        self.assertIn(self.other_doctor_consultation.pk, choices)
        self.assertNotIn(self.other_patient_consultation.pk, choices)
        self.assertNotIn(scheduled.pk, choices)

    def test_upload_rejects_missing_foreign_and_ineligible_consultations(self):
        self.client.force_login(self.hospital)
        invalid_ids = ['', self.other_patient_consultation.pk, 999999]
        for status in ('scheduled', 'waiting', 'cancelled', 'no_show'):
            invalid_ids.append(self.make_consultation(self.patient, self.doctor, status).pk)
        for consultation_id in invalid_ids:
            with self.subTest(consultation_id=consultation_id):
                response = self.client.post(self.upload_url(), self.upload_data(consultation=consultation_id))
                self.assertEqual(response.status_code, 200)
                self.assertIn('consultation', response.context['form'].errors)
                self.assertFalse(MedicalReport.objects.exists())
                self.assertEqual(list(self.report_root.rglob('*')), [])

    def test_only_hospital_role_can_access_upload_and_search_portals(self):
        for user in (
            self.patient, self.doctor_user, self.receptionist,
            self.administrator, self.staff_patient, self.superuser,
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                for url in (self.upload_url(), reverse('accounts:hospital_dashboard')):
                    self.assertIn(self.client.get(url).status_code, (403, 404))
                self.assertIn(self.client.post(self.upload_url(), self.upload_data()).status_code, (403, 404))
        self.assertFalse(MedicalReport.objects.exists())
        self.assertEqual(list(self.report_root.rglob('*')), [])

    def test_hospital_can_only_upload_for_active_patients(self):
        inactive = self.make_user('inactive-report-patient', 'patient', is_active=False)
        no_profile = User.objects.create_user(username='report-user-without-profile')
        self.client.force_login(self.hospital)
        for user in (inactive, no_profile, self.doctor_user, self.hospital):
            with self.subTest(user=user.username):
                self.assertEqual(self.client.post(self.upload_url(user), self.upload_data()).status_code, 404)
        self.assertFalse(MedicalReport.objects.exists())

    def test_hospital_dashboard_search_finds_active_patients(self):
        self.make_user('inactive-search-patient', 'patient',
                       first_name='Amina', last_name='Inactive', is_active=False)
        self.client.force_login(self.hospital)
        response = self.client.get(reverse('accounts:hospital_dashboard'), {'q': 'Amina'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.upload_url())
        self.assertNotContains(response, self.upload_url(self.other_patient))
        self.assertNotContains(response, 'Amina Inactive')

    def test_hospital_search_handles_unusual_and_oversized_identifiers(self):
        self.client.force_login(self.hospital)
        for query in ('²', '9' * 5000, 'SC-' + '9' * 100):
            with self.subTest(query_length=len(query)):
                response = self.client.get(reverse('accounts:hospital_dashboard'), {'q': query})
                self.assertEqual(response.status_code, 200)
                self.assertLessEqual(len(response.context['query']), 100)

    def test_hospital_sees_only_own_metadata_without_download_links(self):
        own_report = self.create_report(title='Own hospital metadata')
        other_report = self.create_report(title='Other hospital private metadata', uploaded_by=self.other_hospital)
        self.client.force_login(self.hospital)
        response = self.client.get(self.upload_url())
        self.assertContains(response, own_report.title)
        self.assertNotContains(response, other_report.title)
        self.assertFalse(response.context['can_download'])
        self.assertNotContains(response, self.download_url(own_report))
        self.assertNotContains(response, self.download_url(other_report))
        self.assertContains(response, self.delete_url(own_report))
        self.assertNotContains(response, self.delete_url(other_report))

    def test_patient_list_is_private_and_read_only_including_legacy_reports(self):
        own_report = self.create_report()
        legacy = self.create_report(title='Legacy patient result', consultation=None)
        other_report = self.create_report(self.other_patient, 'Other patient private result',
                                          consultation=self.other_patient_consultation)
        self.client.force_login(self.patient)
        response = self.client.get(reverse('accounts:reports'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_download'])
        for report in (own_report, legacy):
            self.assertContains(response, report.title)
            self.assertContains(response, self.download_url(report))
        self.assertNotContains(response, other_report.title)
        self.assertNotContains(response, self.download_url(other_report))
        self.assertNotContains(response, self.delete_url(own_report))
        self.assertNotContains(response, 'type="file"')
        response = self.client.post(reverse('accounts:reports'), self.upload_data())
        self.assertEqual(response.status_code, 405)
        self.assertEqual(MedicalReport.objects.count(), 3)

    def test_patient_dashboard_shows_own_recent_report_download(self):
        own_report = self.create_report()
        other_report = self.create_report(self.other_patient, 'Private dashboard result',
                                          consultation=self.other_patient_consultation)
        self.client.force_login(self.patient)
        response = self.client.get(reverse('appointments:patient_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_report.title)
        self.assertContains(response, self.download_url(own_report))
        self.assertNotContains(response, other_report.title)
        self.assertNotContains(response, self.download_url(other_report))

    def test_doctor_list_only_includes_reports_on_their_own_consultations(self):
        own_report = self.create_report()
        another_doctor_report = self.create_report(title='Same patient other consultation',
                                                  consultation=self.other_doctor_consultation)
        legacy = self.create_report(title='Unlinked private report', consultation=None)
        mismatch = self.create_report(title='Mismatched recipient', consultation=self.other_patient_consultation)
        self.client.force_login(self.doctor_user)
        response = self.client.get(reverse('accounts:doctor_reports'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_download'])
        self.assertContains(response, own_report.title)
        self.assertContains(response, self.download_url(own_report))
        for report in (another_doctor_report, legacy, mismatch):
            self.assertNotContains(response, report.title)
            self.assertNotContains(response, self.download_url(report))
        self.assertNotContains(response, self.delete_url(own_report))

    def test_consultation_page_scopes_reports_to_exact_consultation(self):
        own_report = self.create_report()
        second_visit = self.make_consultation(self.patient, self.doctor, 'completed')
        second_report = self.create_report(title='Another visit result', consultation=second_visit)
        self.client.force_login(self.doctor_user)
        response = self.client.get(reverse('accounts:consultation_reports', args=[self.consultation.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_report.title)
        self.assertNotContains(response, second_report.title)
        self.assertEqual(self.client.get(reverse('accounts:consultation_reports',
                         args=[self.other_doctor_consultation.pk])).status_code, 404)

    def test_non_doctors_cannot_access_doctor_report_pages(self):
        for user in (self.patient, self.hospital, self.receptionist, self.administrator, self.superuser):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                for url in (reverse('accounts:doctor_reports'),
                            reverse('accounts:consultation_reports', args=[self.consultation.pk])):
                    self.assertIn(self.client.get(url).status_code, (403, 404))

    def test_patient_and_treating_doctor_download_pdf_with_private_headers(self):
        report = self.create_report()
        for user in (self.patient, self.doctor_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(self.download_url(report))
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response['Content-Type'], 'application/pdf')
                    self.assertIn('attachment;', response['Content-Disposition'])
                    self.assertIn('blood-test.pdf', response['Content-Disposition'])
                    self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
                    self.assertIn('no-store', response['Cache-Control'])
                    self.assertEqual(b''.join(response.streaming_content), self.uploaded_file().read())
                finally:
                    response.close()

    def test_hospital_and_other_roles_cannot_download_actual_report(self):
        report = self.create_report()
        for user in (
            self.hospital, self.other_hospital, self.receptionist, self.administrator,
            self.superuser, self.other_patient, self.staff_patient, self.other_doctor_user,
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.download_url(report)).status_code, 404)

    def test_inline_pdf_preview_uses_the_same_patient_and_doctor_access(self):
        report = self.create_report()
        preview_url = self.download_url(report) + '?view=1'
        for user in (self.patient, self.doctor_user):
            with self.subTest(authorized_user=user.username):
                self.client.force_login(user)
                response = self.client.get(preview_url)
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response['Content-Type'], 'application/pdf')
                    self.assertIn('inline;', response['Content-Disposition'])
                    policy = response['Content-Security-Policy']
                    self.assertIn('sandbox;', policy)
                    self.assertNotIn('allow-same-origin', policy)
                    self.assertNotIn('allow-scripts', policy)
                    self.assertIn("default-src 'none'", policy)
                    self.assertEqual(response['Referrer-Policy'], 'no-referrer')
                    self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
                    self.assertIn('no-store', response['Cache-Control'])
                    self.assertEqual(b''.join(response.streaming_content), self.uploaded_file().read())
                finally:
                    response.close()
        for user in (self.hospital, self.other_doctor_user, self.other_patient):
            with self.subTest(unauthorized_user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(preview_url).status_code, 404)

    def test_doctor_access_requires_eligible_consultation_status(self):
        report = self.create_report()
        self.client.force_login(self.doctor_user)
        for status in ('scheduled', 'waiting', 'cancelled', 'no_show'):
            with self.subTest(status=status):
                Appointment.objects.filter(pk=self.consultation.pk).update(status=status)
                self.assertEqual(self.client.get(self.download_url(report)).status_code, 404)
                self.assertEqual(self.client.get(reverse('accounts:consultation_reports',
                                 args=[self.consultation.pk])).status_code, 404)
                self.assertNotContains(self.client.get(reverse('accounts:doctor_reports')), report.title)
        for status in ('in_consultation', 'completed'):
            with self.subTest(status=status):
                Appointment.objects.filter(pk=self.consultation.pk).update(status=status)
                response = self.client.get(self.download_url(report))
                try:
                    self.assertEqual(response.status_code, 200)
                finally:
                    response.close()

    def test_unlinked_and_mismatched_reports_never_grant_doctor_access(self):
        legacy = self.create_report(consultation=None)
        mismatch = self.create_report(consultation=self.other_patient_consultation)
        self.client.force_login(self.doctor_user)
        for report in (legacy, mismatch):
            self.assertEqual(self.client.get(self.download_url(report)).status_code, 404)
        self.client.force_login(self.patient)
        response = self.client.get(self.download_url(legacy))
        try:
            self.assertEqual(response.status_code, 200)
        finally:
            response.close()

    def test_doctor_access_rechecks_role_and_consultation_patient(self):
        report = self.create_report()
        self.client.force_login(self.doctor_user)
        UserProfile.objects.filter(user=self.doctor_user).update(role='hospital')
        self.assertEqual(self.client.get(self.download_url(report)).status_code, 404)
        self.assertIn(self.client.get(reverse('accounts:doctor_reports')).status_code, (403, 404))
        UserProfile.objects.filter(user=self.doctor_user).update(role='doctor')
        Appointment.objects.filter(pk=self.consultation.pk).update(patient=self.other_patient)
        self.assertEqual(self.client.get(self.download_url(report)).status_code, 404)
        self.assertNotContains(self.client.get(reverse('accounts:doctor_reports')), report.title)

    def test_missing_disk_file_returns_404_for_authorized_users(self):
        report = self.create_report()
        report.file.storage.delete(report.file.name)
        for user in (self.patient, self.doctor_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.download_url(report)).status_code, 404)

    def test_pdf_extension_is_case_insensitive_and_contents_are_preserved(self):
        self.client.force_login(self.hospital)
        content = self.pdf_document()
        response = self.client.post(self.upload_url(), self.upload_data(file=self.uploaded_file('LAB-RESULT.PDF', content)))
        self.assertEqual(response.status_code, 302)
        report = MedicalReport.objects.get()
        self.assertEqual(report.original_filename, 'LAB-RESULT.PDF')
        self.assertEqual(report.file.read(), content)
        report.file.close()

    def test_images_and_invalid_files_are_rejected_without_saving(self):
        self.client.force_login(self.hospital)
        invalid_files = (
            ('scan.png', b'\x89PNG\r\n\x1a\nimage-data'),
            ('scan.jpg', b'\xff\xd8\xff\xe0image-data\xff\xd9'),
            ('scan.jpeg', b'\xff\xd8\xff\xe1image-data\xff\xd9'),
            ('report.html', b'<html>Not a report</html>'),
            ('report.exe', b'%PDF-1.7\nwrong extension'),
            ('report.pdf', b'<html>Disguised document</html>'),
            ('report.pdf', b'%PDF-1.7\n<html>Header-only spoof</html>'),
            ('report.pdf', self.pdf_document().replace(b'%%EOF', b'broken')),
            ('report.pdf', self.pdf_document().replace(b'startxref\n', b'wrongxref\n')),
            ('report.pdf', b'%PDF-1.7\nxref\ntrailer\nstartxref\n999999\n%%EOF'),
            ('empty.pdf', b''),
            ('large.pdf', b'%PDF-' + b'x' * (10 * 1024 * 1024)),
        )
        for filename, content in invalid_files:
            with self.subTest(filename=filename, size=len(content)):
                response = self.client.post(self.upload_url(), self.upload_data(file=self.uploaded_file(filename, content)))
                self.assertEqual(response.status_code, 200)
                self.assertIn('file', response.context['form'].errors)
                self.assertFalse(MedicalReport.objects.exists())
                self.assertEqual(list(self.report_root.rglob('*')), [])

    def test_invalid_metadata_does_not_save_an_uploaded_file(self):
        self.client.force_login(self.hospital)
        for fields in ({'title': ''}, {'title': 'x' * 151}, {'report_date': 'not-a-date'}, {'notes': 'x' * 2001}):
            with self.subTest(fields=list(fields)):
                response = self.client.post(self.upload_url(), self.upload_data(**fields))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertFalse(MedicalReport.objects.exists())
                self.assertEqual(list(self.report_root.rglob('*')), [])

    def test_hospital_delete_requires_post_and_removes_file_after_commit(self):
        report = self.create_report()
        storage, filename = report.file.storage, report.file.name
        self.client.force_login(self.hospital)
        self.assertEqual(self.client.get(self.delete_url(report)).status_code, 405)
        self.assertTrue(MedicalReport.objects.filter(pk=report.pk).exists())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.delete_url(report))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(storage.exists(filename))
        self.assertFalse(MedicalReport.objects.filter(pk=report.pk).exists())
        self.assertFalse(storage.exists(filename))

    def test_only_uploading_hospital_can_delete_a_report(self):
        report = self.create_report()
        for user in (
            self.other_hospital, self.patient, self.other_patient, self.doctor_user,
            self.receptionist, self.administrator, self.staff_patient, self.superuser,
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertIn(self.client.post(self.delete_url(report)).status_code, (403, 404))
                self.assertTrue(MedicalReport.objects.filter(pk=report.pk).exists())
                self.assertTrue(report.file.storage.exists(report.file.name))

    def test_hospital_mutations_require_csrf_tokens(self):
        report = self.create_report()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hospital)
        self.assertEqual(csrf_client.post(self.upload_url(), self.upload_data()).status_code, 403)
        self.assertEqual(csrf_client.post(self.delete_url(report)).status_code, 403)
        self.assertEqual(MedicalReport.objects.count(), 1)

    def test_patient_account_deletion_cleans_up_report_file(self):
        report = self.create_report()
        storage, filename = report.file.storage, report.file.name
        with self.captureOnCommitCallbacks(execute=True):
            self.patient.delete()
            self.assertTrue(storage.exists(filename))
        self.assertFalse(MedicalReport.objects.filter(pk=report.pk).exists())
        self.assertFalse(storage.exists(filename))
