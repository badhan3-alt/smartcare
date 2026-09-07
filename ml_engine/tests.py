from django.test import TestCase, Client
from django.urls import reverse
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

