import json
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserProfile
from predictor.models import Prediction


class InsurancePredictionSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.patient = User.objects.create_user(username='insurance-patient')
        UserProfile.objects.create(user=cls.patient, role='patient', phone='01711223344')

    def setUp(self):
        cache.clear()
        self.client.force_login(self.patient)
        self.model = Mock()
        self.model.predict.return_value = [1234.567]
        self.scaler = Mock()
        self.scaler.transform.side_effect = lambda frame: frame
        patcher = patch('predictor.views._get_model_and_scaler', return_value=(self.model, self.scaler))
        self.load_artifacts = patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def data(**kwargs):
        return {'age': 35, 'sex': 'female', 'bmi': 24.5, 'children': 2,
                'smoker': 'no', 'region': 'northeast', **kwargs}

    def post(self, data=None, client=None, path=None):
        return (client or self.client).post(
            path or reverse('predict'), json.dumps(data if data is not None else self.data()),
            content_type='application/json',
        )

    def test_anonymous_users_cannot_open_estimator_or_use_either_api_alias(self):
        anonymous = Client()
        self.assertEqual(anonymous.get(reverse('insurance_home')).status_code, 302)
        for path in ('/insurance/predict/', '/insurance/api/predict/'):
            with self.subTest(path=path):
                self.assertEqual(self.post(client=anonymous, path=path).status_code, 403)
        self.load_artifacts.assert_not_called()

    def test_session_api_requires_csrf_and_accepts_the_page_token(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.patient)
        self.assertEqual(self.post(client=browser).status_code, 403)
        response = browser.get(reverse('insurance_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'X-CSRFToken')
        self.assertContains(response, reverse('predict'))
        token = browser.cookies['csrftoken'].value
        response = browser.post(reverse('predict'), json.dumps(self.data()),
                                content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': True, 'predicted_charge': 1234.57})

    def test_valid_prediction_does_not_persist_sensitive_inputs(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['predicted_charge'], 1234.57)
        self.assertFalse(Prediction.objects.exists())
        self.assertIn('no-store', response['Cache-Control'])

    def test_numeric_and_category_bounds_are_validated_before_model_loading(self):
        values = (
            {'age': 0}, {'age': 121}, {'age': 'not a number'}, {'age': True},
            {'bmi': 0}, {'bmi': 101}, {'bmi': 'NaN'}, {'bmi': 'Infinity'},
            {'bmi': '-Infinity'}, {'children': -1}, {'children': 21},
            {'sex': '<script>alert(1)</script>'}, {'smoker': 'sometimes'},
            {'region': 'unknown'},
        )
        for fields in values:
            with self.subTest(fields=fields):
                self.assertEqual(self.post(self.data(**fields)).status_code, 400)
        self.load_artifacts.assert_not_called()

    def test_missing_fields_and_nonobject_json_are_invalid(self):
        self.assertEqual(self.post({}).status_code, 400)
        self.assertEqual(self.post([]).status_code, 400)
        self.load_artifacts.assert_not_called()

    def test_malformed_and_excessively_nested_json_return_errors(self):
        for payload in ('{not json}', '[' * 1500 + '0' + ']' * 1500):
            with self.subTest(length=len(payload)):
                response = self.client.post(reverse('predict'), payload, content_type='application/json')
                self.assertEqual(response.status_code, 400)
                self.assertNotIn('Traceback', response.content.decode())
        self.load_artifacts.assert_not_called()

    def test_request_size_is_bounded_before_json_decoding(self):
        response = self.post(self.data(padding='x' * 9000))
        self.assertEqual(response.status_code, 413)
        self.load_artifacts.assert_not_called()

    def test_only_json_post_requests_are_accepted(self):
        self.assertEqual(self.client.get(reverse('predict')).status_code, 405)
        self.assertEqual(self.client.post(reverse('predict'), self.data()).status_code, 415)
        self.load_artifacts.assert_not_called()

    def test_model_loading_errors_return_generic_unavailability(self):
        self.load_artifacts.side_effect = OSError('PRIVATE-MODEL-PATH details')
        with self.assertLogs('predictor.views', level='WARNING') as logs:
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['success'])
        self.assertNotIn('PRIVATE-MODEL-PATH', response.content.decode())
        self.assertNotIn('PRIVATE-MODEL-PATH', '\n'.join(logs.output))
        self.assertNotIn('Traceback', response.content.decode())

    def test_invalid_model_outputs_return_generic_unavailability(self):
        for value in (float('nan'), float('inf'), -1):
            with self.subTest(value=value), self.assertLogs('predictor.views', level='WARNING'):
                self.model.predict.return_value = [value]
                self.assertEqual(self.post().status_code, 503)

    def test_predictions_are_throttled_per_authenticated_user(self):
        for _ in range(30):
            self.assertEqual(self.post().status_code, 200)
        response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.model.predict.call_count, 30)
        self.assertIn('Retry-After', response)
