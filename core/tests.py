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

