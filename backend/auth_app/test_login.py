from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase


class LoginIdentifierTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='identifier-user',
            email='identifier@example.com',
            password='correct-horse-battery-staple',
        )

    def test_login_accepts_username(self):
        response = self.client.post('/api/auth/login/', {
            'username': self.user.username,
            'password': 'correct-horse-battery-staple',
            'device_id': 'test-username-device',
            'device_name': 'Automated test',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)
        self.assertEqual(response.data['user']['id'], self.user.id)

    def test_login_accepts_unique_email_case_insensitively(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'IDENTIFIER@EXAMPLE.COM',
            'password': 'correct-horse-battery-staple',
            'device_id': 'test-email-device',
            'device_name': 'Automated test',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)
        self.assertEqual(response.data['user']['username'], self.user.username)
