from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from doctors.models import Department, DoctorProfile

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

