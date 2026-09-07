from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from accounts.models import UserProfile
from ml_engine.ml_service import predict_consultation_duration, forecast_appointment_demand, get_staffing_recommendations

class MLEngineTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_duration_prediction(self):
        duration = predict_consultation_duration(
            patient_age=45,
            patient_gender='M',
            department='Cardiology',
            visit_type='first_visit',
            symptom_severity='moderate',
            has_chronic_condition=True,
            doctor_experience_years=10
        )
        self.assertIsInstance(duration, float)
        self.assertGreaterEqual(duration, 5.0)
        self.assertLessEqual(duration, 60.0)

    def test_demand_forecast(self):
        forecast = forecast_appointment_demand(days_ahead=7)
        self.assertIn('total_projected', forecast)
        self.assertGreater(forecast['total_projected'], 0)
        self.assertEqual(len(forecast['daily_summaries']), 7)

    def test_staffing_recommendations_are_generated(self):
        forecast = forecast_appointment_demand(days_ahead=7)
        recommendations = get_staffing_recommendations(forecast)
        self.assertTrue(recommendations)
        self.assertIn('title', recommendations[0])
        self.assertIn('message', recommendations[0])

    def test_api_predict_duration(self):
        response = self.client.get(reverse('api_predict_duration'), {
            'age': 30,
            'gender': 'F',
            'department': 'Pediatrics',
            'visit_type': 'first_visit',
            'severity': 'moderate'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('predicted_duration', data)
        self.assertGreater(data['predicted_duration'], 0)

    def test_admin_can_review_receptionist_requests(self):
        admin = User.objects.create_user(username='portal-admin', password='test-pass')
        UserProfile.objects.create(user=admin, role='admin', phone='01700000000')
        applicant = User.objects.create_user(
            username='pending-reception', email='pending@example.com',
            password='test-pass', is_active=False,
        )
        UserProfile.objects.create(user=applicant, role='receptionist', phone='01800000000')
        self.client.force_login(admin)

        response = self.client.get(reverse('admin_receptionist_requests'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pending-reception')

        response = self.client.post(reverse('approve_receptionist', args=[applicant.id]))
        self.assertRedirects(response, reverse('admin_receptionist_requests'))
        applicant.refresh_from_db()
        self.assertTrue(applicant.is_active)

    def test_admin_can_approve_doctor_requests(self):
        admin = User.objects.create_user(username='doctor-portal-admin', password='test-pass')
        UserProfile.objects.create(user=admin, role='admin', phone='01700000001')
        applicant = User.objects.create_user(
            username='pending-doctor', email='doctor@example.com',
            password='test-pass', is_active=False,
        )
        UserProfile.objects.create(user=applicant, role='doctor', phone='01800000001')
        self.client.force_login(admin)

        response = self.client.get(reverse('admin_receptionist_requests'))
        self.assertContains(response, 'pending-doctor')
        self.assertContains(response, 'Doctor')

        self.client.post(reverse('approve_receptionist', args=[applicant.id]))
        applicant.refresh_from_db()
        self.assertTrue(applicant.is_active)

    def test_doctor_requests_have_a_dedicated_admin_interface(self):
        admin = User.objects.create_user(username='doctor-reviewer', password='test-pass')
        UserProfile.objects.create(user=admin, role='admin', phone='01700000002')
        applicant = User.objects.create_user(
            username='doctor-request', email='doctor-request@example.com',
            password='test-pass', is_active=False,
        )
        UserProfile.objects.create(user=applicant, role='doctor', phone='01800000002')
        self.client.force_login(admin)

        response = self.client.get(reverse('admin_doctor_requests'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Doctor Approval Requests')
        self.assertContains(response, 'doctor-request')

        response = self.client.post(reverse('reject_doctor', args=[applicant.id]))
        self.assertRedirects(response, reverse('admin_doctor_requests'))
        self.assertFalse(User.objects.filter(id=applicant.id).exists())
