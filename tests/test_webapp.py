import unittest
from unittest.mock import patch

from webapp import create_app


class DummySource:
    def to_dict(self):
        return {
            "source_name": "Sample Interview.mov",
            "source_path": "C:/Projects/BiteBuilder/Sample Interview.mov",
            "pathurl": "file://localhost/C%3A/Projects/BiteBuilder/Sample%20Interview.mov",
            "timebase": 24,
            "ntsc": False,
            "duration": 2400,
            "width": 1920,
            "height": 1080,
            "audio_depth": 16,
            "audio_samplerate": 48000,
            "audio_channels": 2,
            "actual_fps": 24.0,
            "duration_seconds": 100.0,
        }


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()

    def test_shell_routes(self):
        for path in [
            "/",
            "/project/intake",
            "/project/brief",
            "/project/context",
            "/project/chat",
            "/project/copilot",
            "/project/generate",
            "/project/output",
            "/project/export",
            "/project/logs",
        ]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"BiteBuilder", response.data)

    def test_repo_file_route(self):
        response = self.client.get("/repo-file/testing/solar-project-cut-down-1/context.prd.md")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Solar Project Cut Down 1", response.data)
        response.close()

    @patch("webapp.resolve_host", return_value=("http://127.0.0.1:11435", ["qwen3:8b", "qwen3.5:9b"]))
    def test_models_endpoint(self, _resolve_host):
        response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["connected"])
        self.assertEqual(payload["default_model"], "qwen3:8b")
        self.assertIn(payload["default_thinking_mode"], {"auto", "on", "off"})
        self.assertEqual(len(payload["models"]), 2)

    def test_presets_endpoint(self):
        response = self.client.get("/api/presets")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["presets"][0]["id"], "solar-project-cut-down-1")

    def test_preset_detail_endpoint(self):
        response = self.client.get("/api/presets/solar-project-cut-down-1")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["name"], "Solar Project Cut Down 1")
        self.assertIn("solar panel company innovation", payload["brief"])
        self.assertEqual(payload["transcript_name"], "Solar Project Cut Down 1.txt")
        self.assertEqual(payload["thinking_mode"], "on")

    @patch("webapp.resolve_host", return_value=("http://127.0.0.1:11435", ["qwen3:8b"]))
    @patch("webapp.generate_text", return_value="[0] 00:00:00:00 - 00:00:05:00 Lead with the objection, then pivot to proof.")
    def test_chat_endpoint(self, _generate_text, _resolve_host):
        response = self.client.post("/api/chat", json={
            "transcript_text": (
                "00:00:00:00 - 00:00:05:00\nSpeaker 1\n"
                "Most shops think better nutrition sounds expensive.\n"
            ),
            "brief": "45 second proof of concept",
            "project_context": "B2B nutrition software",
            "model": "qwen3:8b",
            "messages": [{"role": "user", "content": "How should this open?"}],
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("Lead with the objection", payload["reply"])
        self.assertEqual(payload["segment_count"], 1)
        self.assertEqual(payload["suggested_plan"]["opening_segment_index"], 0)
        self.assertEqual(payload["suggested_plan"]["must_include_segment_indexes"], [0])

    def test_parse_transcript_endpoint(self):
        response = self.client.post("/api/parse-transcript", json={
            "transcript_text": (
                "00:00:00:00 - 00:00:05:00\nSpeaker 1\n"
                "Most shops think better nutrition sounds expensive.\n"
            ),
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["segment_count"], 1)
        self.assertEqual(payload["segments"][0]["segment_index"], 0)
        self.assertGreater(payload["segments"][0]["duration_seconds"], 0)

    @patch("webapp.build_candidate_shortlist", return_value=[{
        "segment_index": 0,
        "tc_in": "00:00:00:00",
        "tc_out": "00:00:05:00",
        "speaker": "Speaker 1",
        "text": "Hook line.",
        "duration_seconds": 5.0,
        "score": 12.0,
        "roles": ["HOOK"],
        "reasons": ["pinned"],
    }])
    @patch("webapp.parse_premiere_xml_string", return_value=DummySource())
    def test_preview_shortlist_endpoint(self, _parse_source, _build_candidate_shortlist):
        response = self.client.post("/api/preview-shortlist", json={
            "transcript_text": (
                "00:00:00:00 - 00:00:05:00\nSpeaker 1\n"
                "Hook line.\n"
            ),
            "xml_text": "<xmeml version='4'></xmeml>",
            "brief": "Hooky cut",
            "accepted_plan": {"opening_segment_index": 0},
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["candidates"][0]["segment_index"], 0)
        self.assertEqual(_build_candidate_shortlist.call_args.kwargs["accepted_plan"]["opening_segment_index"], 0)

    @patch("webapp.run_pipeline")
    def test_generate_endpoint(self, mock_run_pipeline):
        mock_run_pipeline.return_value = {
            "segment_count": 5,
            "source": DummySource(),
            "thinking_mode": "on",
            "target_duration_range": [45, 60],
            "validation_errors": [],
            "response": {
                "options": [{
                    "name": "Margin Story",
                    "description": "Opens with the objection and closes with a test invitation.",
                    "estimated_duration_seconds": 15.0,
                    "cuts": [{
                        "tc_in": "00:00:00:00",
                        "tc_out": "00:00:05:00",
                        "speaker": "Speaker 1",
                        "purpose": "HOOK",
                        "dialogue_summary": "Hook.",
                    }],
                }],
            },
            "segments": [],
            "debug_artifacts": {"candidate_shortlist": []},
            "debug_files": {},
            "output_files": [
                {
                    "name": "Margin Story",
                    "description": "Opens with the objection and closes with a test invitation.",
                    "filename": "Margin_Story.xml",
                    "cut_count": 3,
                    "actual_duration_seconds": 15.0,
                    "estimated_duration_seconds": 15.0,
                }
            ],
        }

        response = self.client.post("/api/generate", json={
            "transcript_text": (
                "00:00:00:00 - 00:00:05:00\nSpeaker 1\n"
                "Most shops think better nutrition sounds expensive.\n"
            ),
            "xml_text": (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                "<xmeml version=\"4\"><sequence><media><video><track><clipitem>"
                "<file><name>Sample Interview.mov</name><pathurl>file://localhost/C%3A/clip.mov</pathurl>"
                "</file></clipitem></track></video></media></sequence></xmeml>"
            ),
            "brief": "45 second proof of concept",
            "project_context": "B2B nutrition software",
            "messages": [{"role": "user", "content": "Make it whacky."}],
            "accepted_plan": {"opening_segment_index": 0, "must_include_segment_indexes": [0]},
            "model": "qwen3.5:9b",
            "options": 2,
        })

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["segment_count"], 5)
        self.assertEqual(payload["files"][0]["filename"], "Margin_Story.xml")
        self.assertEqual(payload["thinking_mode"], "on")
        self.assertIn("/api/output/", payload["files"][0]["download_url"])
        self.assertEqual(
            mock_run_pipeline.call_args.kwargs["editorial_messages"],
            [{"role": "user", "content": "Make it whacky."}],
        )
        self.assertEqual(mock_run_pipeline.call_args.kwargs["accepted_plan"]["opening_segment_index"], 0)

    @patch("webapp.run_pipeline")
    def test_generate_job_endpoint(self, mock_run_pipeline):
        mock_run_pipeline.return_value = {
            "segment_count": 1,
            "source": DummySource(),
            "thinking_mode": "on",
            "target_duration_range": [45, 60],
            "validation_errors": [],
            "response": {"options": []},
            "segments": [],
            "debug_artifacts": {"candidate_shortlist": []},
            "debug_files": {},
            "output_files": [],
        }
        response = self.client.post("/api/generate-jobs", json={
            "transcript_text": (
                "00:00:00:00 - 00:00:05:00\nSpeaker 1\n"
                "Hook line.\n"
            ),
            "xml_text": "<xmeml version='4'></xmeml>",
            "brief": "Hooky cut",
            "model": "qwen3:8b",
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("job_id", payload)

    @patch("webapp.generate_sequence", return_value="<xmeml version='4'></xmeml>")
    @patch("webapp.parse_premiere_xml_string", return_value=DummySource())
    def test_render_xml_endpoint(self, _parse_source, _generate_sequence):
        response = self.client.post("/api/render-xml", json={
            "transcript_text": (
                "00:00:00:00 - 00:00:05:00\nSpeaker 1\n"
                "Hook line.\n"
            ),
            "xml_text": "<xmeml version='4'></xmeml>",
            "name": "Manual Test",
            "cuts": [{"segment_index": 0}],
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["files"][0]["name"], "Manual Test")
