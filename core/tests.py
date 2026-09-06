from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from accounts.models import UserProfile

class HomeViewSessionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='Password123!'
        )
        UserProfile.objects.create(user=self.user, role='patient')

    def test_entering_site_at_home_forgets_previous_login(self):
        # Log the user in
        login_success = self.client.login(username='testuser', password='Password123!')
        self.assertTrue(login_success)

        # Confirm the client session is currently authenticated
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirects to role-specific dashboard

        # Enter into the site (home page '/')
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

        # Confirm user is now logged out
        self.assertFalse(response.context['user'].is_authenticated)

        # Visiting dashboard now redirects to login instead of allowing access
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_visiting_login_forgets_previous_login(self):
        self.client.login(username='testuser', password='Password123!')
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['user'].is_authenticated)

