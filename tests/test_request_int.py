import unittest
from pathlib import Path

import bitebuilder
import webapp


class RequestIntTests(unittest.TestCase):
    def test_import_resolves_to_top_level_module(self):
        self.assertEqual(Path(bitebuilder.__file__).name, 'bitebuilder.py')

    def test_uses_default_for_missing_value(self):
        value = bitebuilder.coerce_request_int(None, field_name='timeout', default=30, code='TEST')
        self.assertEqual(value, 30)

    def test_rejects_non_integer(self):
        with self.assertRaises(bitebuilder.BiteBuilderError) as ctx:
            bitebuilder.coerce_request_int('abc', field_name='timeout', default=30, code='TEST')
        error = ctx.exception.error
        self.assertEqual(error['code'], 'TEST')
        self.assertEqual(error['type'], 'invalid_numeric_input')
        self.assertEqual(error['stage'], 'input')
        self.assertEqual(error['details']['field'], 'timeout')
        self.assertEqual(error['details']['value'], 'abc')

    def test_rejects_below_minimum(self):
        with self.assertRaises(bitebuilder.BiteBuilderError) as ctx:
            bitebuilder.coerce_request_int('0', field_name='options', default=3, code='TEST', minimum=1)
        error = ctx.exception.error
        self.assertEqual(error['type'], 'invalid_numeric_input')
        self.assertIn('at least 1', error['message'])
        self.assertEqual(error['details'], {'field': 'options', 'value': '0'})


VALID_TRANSCRIPT = """00:00:00:00 - 00:00:02:00
Speaker 1
Hello there.
"""


class RequestIntFlaskTests(unittest.TestCase):
    def setUp(self):
        self.client = webapp.create_app().test_client()

    def assert_invalid_numeric_response(self, response, expected_code, expected_field):
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertEqual(payload['status'], 'error')
        error = payload['error']
        self.assertEqual(error['code'], expected_code)
        self.assertEqual(error['type'], 'invalid_numeric_input')
        self.assertEqual(error['details']['field'], expected_field)

    def test_generate_rejects_invalid_options_before_runtime_work(self):
        response = self.client.post('/api/generate', json={'options': 'many'})
        self.assert_invalid_numeric_response(response, 'GENERATE-OPTIONS-INVALID', 'options')

    def test_generate_rejects_timeout_below_minimum_before_runtime_work(self):
        response = self.client.post('/api/generate', json={'timeout': '0'})
        self.assert_invalid_numeric_response(response, 'GENERATE-TIMEOUT-INVALID', 'timeout')

    def test_generate_jobs_rejects_invalid_options_before_runtime_work(self):
        response = self.client.post('/api/generate-jobs', json={'options': 'many'})
        self.assert_invalid_numeric_response(response, 'GENERATE-JOB-OPTIONS-INVALID', 'options')

    def test_generate_jobs_rejects_invalid_timeout_before_runtime_work(self):
        response = self.client.post('/api/generate-jobs', json={'timeout': 'soon'})
        self.assert_invalid_numeric_response(response, 'GENERATE-JOB-TIMEOUT-INVALID', 'timeout')

    def test_chat_rejects_invalid_timeout_after_transcript_validation(self):
        response = self.client.post('/api/chat', json={
            'transcript_text': VALID_TRANSCRIPT,
            'timeout': 'later',
        })
        self.assert_invalid_numeric_response(response, 'CHAT-TIMEOUT-INVALID', 'timeout')

if __name__ == '__main__':
    unittest.main()
