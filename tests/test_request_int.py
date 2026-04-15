import unittest
from pathlib import Path
from unittest.mock import patch

import bitebuilder
import webapp


class RequestIntTests(unittest.TestCase):
    def test_import_resolves_to_top_level_module(self):
        self.assertEqual(Path(bitebuilder.__file__).name, 'bitebuilder.py')

    def test_workspace_css_uses_times_new_roman_and_no_gradients(self):
        css = Path('static/app.css').read_text()
        self.assertIn('font-family: "Times New Roman"', css)
        self.assertNotIn('linear-gradient', css)
        self.assertNotIn('radial-gradient', css)

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

XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<xmeml version="4">
  <sequence>
    <name>{name}</name>
    <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
    <media>
      <video>
        <track>
          <clipitem>
            <name>{source_name}</name>
            <start>0</start>
            <end>48</end>
            <in>{clip_in}</in>
            <out>{clip_out}</out>
            <file>
              <name>{source_name}</name>
              <pathurl>{pathurl}</pathurl>
              <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
              <duration>240</duration>
              <media>
                <video><samplecharacteristics><width>1920</width><height>1080</height></samplecharacteristics></video>
                <audio>
                  <channelcount>2</channelcount>
                  <samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics>
                </audio>
              </media>
            </file>
          </clipitem>
        </track>
      </video>
    </media>
  </sequence>
</xmeml>
"""


def xml_fixture(*, clip_in=0, clip_out=48, pathurl='file:///Volumes/Test/clip.mov', name='Interview', source_name='clip.mov'):
    return XML_TEMPLATE.format(
        clip_in=clip_in,
        clip_out=clip_out,
        pathurl=pathurl,
        name=name,
        source_name=source_name,
    )


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

    def test_workspace_route_renders(self):
        response = self.client.get('/workspace')
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('Selection-first edit board', page)
        self.assertIn('Transcript browser', page)
        self.assertIn('Selected lane', page)
        self.assertIn('Save snapshot', page)
        self.assertIn('Saved drafts', page)
        self.assertIn('Saved from model', page)
        self.assertIn('Click numbered bite chips', page)
        self.assertNotIn('Load solar demo', page)

    def test_root_redirects_to_workspace(self):
        response = self.client.get('/', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/workspace')

    def test_parse_transcript_combines_source_pairs_with_secondary_offset(self):
        response = self.client.post('/api/parse-transcript', json={
            'source_pairs': [
                {
                    'transcript_text': VALID_TRANSCRIPT,
                    'xml_text': xml_fixture(name='CEO Interview', clip_in=0, clip_out=48),
                },
                {
                    'transcript_text': """00:00:00:00 - 00:00:02:00
Speaker 2
Secondary hello.
""",
                    'xml_text': xml_fixture(name='Technician Interview', clip_in=48, clip_out=96),
                },
            ],
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['segment_count'], 2)
        self.assertEqual(payload['segments'][0]['text'], 'Hello there.')
        self.assertEqual(payload['segments'][1]['text'], 'Secondary hello.')
        self.assertEqual(payload['segments'][1]['tc_in'], '00:00:02:00')

    def test_generate_uses_combined_source_pairs_payload(self):
        fake_result = {
            'output_files': [],
            'response': {'options': []},
            'debug_artifacts': {'candidate_shortlist': []},
            'debug_files': {},
            'segments': [],
            'segment_count': 2,
            'run_metadata': {},
            'source': bitebuilder.parse_premiere_xml_safe(xml_fixture()),
            'thinking_mode': 'auto',
            'target_duration_range': [30, 60],
            'validation_errors': [],
        }
        with patch('webapp.run_pipeline', return_value=fake_result) as run_pipeline:
            response = self.client.post('/api/generate', json={
                'brief': 'Innovation-forward open, technical middle, optimistic close.',
                'model': 'gemma3:4b',
                'source_pairs': [
                    {
                        'transcript_text': VALID_TRANSCRIPT,
                        'xml_text': xml_fixture(name='CEO Interview', clip_in=0, clip_out=48),
                    },
                    {
                        'transcript_text': """00:00:00:00 - 00:00:02:00
Speaker 2
Secondary hello.
""",
                        'xml_text': xml_fixture(name='Technician Interview', clip_in=48, clip_out=96),
                    },
                ],
            })
        self.assertEqual(response.status_code, 200)
        kwargs = run_pipeline.call_args.kwargs
        self.assertIn('Hello there.', kwargs['transcript_text'])
        self.assertIn('Secondary hello.', kwargs['transcript_text'])
        self.assertIn('00:00:02:00', kwargs['transcript_text'])

if __name__ == '__main__':
    unittest.main()
