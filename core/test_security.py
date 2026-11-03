from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from config.middleware import RequestSizeLimitMiddleware


class RequestBoundaryTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = RequestSizeLimitMiddleware(lambda request: HttpResponse('OK'))

    @override_settings(SMARTCARE_MAX_REQUEST_BYTES=100)
    def test_oversized_body_is_rejected_before_processing(self):
        request = self.factory.post('/', data=b'payload', content_type='application/octet-stream')
        request.META['CONTENT_LENGTH'] = '101'
        self.assertEqual(self.middleware(request).status_code, 413)

    def test_invalid_or_negative_lengths_are_rejected(self):
        for value in ('-1', 'not-a-number'):
            with self.subTest(value=value):
                request = self.factory.get('/')
                request.META['CONTENT_LENGTH'] = value
                self.assertEqual(self.middleware(request).status_code, 400)

    def test_normal_requests_still_work(self):
        self.assertEqual(self.middleware(self.factory.get('/')).status_code, 200)

    @override_settings(DEBUG=False)
    def test_demo_seeder_cannot_run_in_production(self):
        with self.assertRaises(CommandError):
            call_command('seed_smartcare', allow_demo_data=True, stdout=StringIO())

    @override_settings(DEBUG=True)
    def test_demo_seeder_requires_explicit_opt_in(self):
        with self.assertRaises(CommandError):
            call_command('seed_smartcare', stdout=StringIO())
