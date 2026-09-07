import datetime

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from accounts.models import UserProfile
from doctors.models import Department, DoctorProfile
from doctors.recommendation_service import get_recommended_doctors

class DoctorsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Pediatrics", code="pediatrics")
        self.doc_user = User.objects.create_user(username="dr.pediatrician", password="password123")
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.dept,
            qualification="MBBS, DCH",
            specialization="Child Health",
            experience_years=8,
            consultation_fee=500.0,
            room_number="Room 201"
        )

    def test_doctor_list_page(self):
        response = self.client.get(reverse('doctor_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dr.pediatrician")

    def test_doctor_detail_page(self):
        response = self.client.get(reverse('doctor_detail', kwargs={'doctor_id': self.doctor.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MBBS, DCH")

    def test_recommended_doctors_are_ranked_for_patient(self):
        patient = User.objects.create_user(username="patient_ali", password="secret123")
        UserProfile.objects.create(user=patient, role='patient', gender='M')

        second_doctor = DoctorProfile.objects.create(
            user=User.objects.create_user(username="dr.second", password="secret123"),
            department=self.dept,
            qualification="MD, Cardiology",
            specialization="Heart Care",
            experience_years=12,
            consultation_fee=600.0,
            room_number="Room 202",
        )

        recommendations = get_recommended_doctors(
            patient,
            DoctorProfile.objects.filter(is_available=True),
            department_id=self.dept.id,
            appointment_date=datetime.date.today(),
            limit=2,
        )

        self.assertGreater(recommendations[0]['score'], recommendations[1]['score'])
        self.assertTrue(recommendations[0]['reasons'])
        self.assertIn('Matches your specialty', recommendations[0]['reasons'])

