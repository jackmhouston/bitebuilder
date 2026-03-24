import unittest
from unittest.mock import patch
from bitebuilder import BiteBuilderError, build_validation_error

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

    def test_parse_transcript_endpoint_timecode_edge_structured_error(self):
        response = self.client.post("/api/parse-transcript", json={
            "transcript_text": (
                "00:00:00:24 - 00:00:01:00\nSpeaker 1\n"
                "Frame boundary is out of range for 24fps.\n"
            ),
            "xml_text": (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                "<xmeml version=\"4\"><sequence><media><video><track><clipitem>"
                "<file><name>Sample Interview.mov</name>"
                "<pathurl>file://localhost/C%3A/Projects/BiteBuilder/Sample%20Interview.mov</pathurl>"
                "</file></clipitem></track></video></media></sequence></xmeml>"
            ),
        })
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "TRANSCRIPT-TIMECODE-INVALID")
        self.assertEqual(payload["error"]["details"]["errors"][0]["field"], "timecode")

    def test_generate_missing_brief_returns_structured_error(self):
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
            "brief": "",
        })
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "BRIEF-MISSING")
        self.assertIn("expected_input_format", payload["error"])
        self.assertIn("next_action", payload["error"])

    def test_generate_invalid_xml_returns_structured_error(self):
        response = self.client.post("/api/generate", json={
            "transcript_text": (
                "00:00:00:00 - 00:00:05:00\nSpeaker 1\n"
                "Most shops think better nutrition sounds expensive.\n"
            ),
            "xml_text": "<not-xml>",
            "brief": "45 second proof of concept",
        })
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "XML-MALFORMED")

    @patch("webapp.run_pipeline", side_effect=BiteBuilderError({
        **build_validation_error(
            code="XML-MALFORMED",
            error_type="invalid_xml",
            message="Invalid Premiere XML content.",
            expected_input_format="Valid Premiere XML export text.",
            next_action="Export XML again from Premiere and retry.",
            stage="premiere_xml",
            recoverable=True,
            details={"cause": "malformed xml"},
        ),
    }))
    def test_generate_endpoint_invalid_xml_returns_structured_error(self, _run_pipeline):
        response = self.client.post("/api/generate", json={
            "transcript_text": (
                "00:00:00:00 - 00:00:05:00\nSpeaker 1\n"
                "Most shops think better nutrition sounds expensive.\n"
            ),
            "xml_text": (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?><xmeml><sequence><media></sequence></xmeml>"
            ),
            "brief": "45 second proof of concept",
        })
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "XML-MALFORMED")
        self.assertIn("recoverable", payload["error"])

    @patch("webapp.run_pipeline")
    def test_generate_endpoint_success_with_mocked_llm_response_payload_shape(self, mock_run_pipeline):
        segment = type(
            "Segment",
            (),
            {
                "tc_in": "00:00:00:00",
                "tc_out": "00:00:05:00",
                "speaker": "Speaker 1",
                "text": "Hook.",
            },
        )()
        mock_run_pipeline.return_value = {
            "segment_count": 1,
            "source": DummySource(),
            "thinking_mode": "auto",
            "target_duration_range": [45, 60],
            "validation_errors": [],
            "response": {
                "selection_status": "ok",
                "options": [{
                    "name": "Margin Story",
                    "description": "Opens with the objection and closes with a test invitation.",
                    "estimated_duration_seconds": 15.0,
                    "cuts": [{
                        "segment_index": 0,
                        "tc_in": "00:00:00:00",
                        "tc_out": "00:00:05:00",
                        "speaker": "Speaker 1",
                        "purpose": "HOOK",
                        "dialogue_summary": "Hook.",
                    }],
                }],
            },
            "segments": [segment],
            "debug_artifacts": {"candidate_shortlist": []},
            "debug_files": {},
            "output_files": [{
                "name": "Margin Story",
                "description": "Hook cut",
                "filename": "Margin_Story.xml",
                "path": "/tmp/Margin_Story.xml",
                "cut_count": 1,
                "actual_duration_seconds": 5.0,
                "estimated_duration_seconds": 5.0,
            }],
            "run_metadata": {
                "schema_version": "run-metadata/1",
                "timestamp": "2026-03-23T00:00:00Z",
                "input_descriptors": {
                    "transcript": {"sha256": "abc"},
                    "premiere_xml": {"sha256": "def"},
                },
                "parser_versions": {"transcript_parser": "transcript-parser/1"},
                "model": {"resolved_id": "qwen3:8b"},
            },
        }

        response = self.client.post("/api/generate", json={
            "transcript_text": (
                "00:00:00:00 - 00:00:05:00\nSpeaker 1\n"
                "Most shops think better nutrition sounds expensive.\n"
            ),
            "xml_text": (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                "<xmeml version=\"4\"><sequence><media><video><track><clipitem>"
                "<file><name>Sample Interview.mov</name>"
                "<pathurl>file://localhost/C%3A/clip.mov</pathurl>"
                "</file></clipitem></track></video></media></sequence></xmeml>"
            ),
            "brief": "45 second proof of concept",
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["thinking_mode"], "auto")
        self.assertIn("files", payload)
        self.assertEqual(payload["files"][0]["filename"], "Margin_Story.xml")
        self.assertEqual(payload["files"][0]["selected_cuts"][0]["segment_index"], 0)
        self.assertEqual(len(payload["options_detail"][0]["selected_cuts"]), 1)
        self.assertEqual(payload["run_metadata"]["model"]["resolved_id"], "qwen3:8b")
        self.assertEqual(payload["run_metadata"]["input_descriptors"]["transcript"]["sha256"], "abc")

    @patch("webapp.run_pipeline", side_effect=BiteBuilderError({
        **build_validation_error(
            code="TRANSCRIPT-TIMECODE-INVALID",
            error_type="invalid_transcript_content",
            message="Transcript timecodes are invalid.",
            expected_input_format="Timecoded transcript format.",
            next_action="Fix timecode formatting and order.",
            stage="transcript",
            recoverable=True,
            details={"errors": [{"field": "time_transition", "line": 3, "message": "bad transition"}]},
        ),
        "partial": {
            "status": "partial",
            "stage": "transcript",
        },
    }))
    def test_generate_endpoint_validation_failure_is_recoverable(self, _run_pipeline):
        response = self.client.post("/api/generate", json={
            "transcript_text": (
                "00:00:05:00 - 00:00:10:00\nSpeaker 1\n"
                "Bad order.\n"
            ),
            "xml_text": (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                "<xmeml version=\"4\"><sequence><media><video><track><clipitem>"
                "<file><name>Sample Interview.mov</name><pathurl>file://localhost/C%3A/clip.mov</pathurl>"
                "</file></clipitem></track></video></media></sequence></xmeml>"
            ),
            "brief": "45 second proof of concept",
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["error"]["code"], "TRANSCRIPT-TIMECODE-INVALID")

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
    @patch("webapp.parse_premiere_xml_safe", return_value=DummySource())
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
            "run_metadata": {
                "schema_version": "run-metadata/1",
                "timestamp": "2026-03-23T00:00:00Z",
                "input_descriptors": {
                    "transcript": {"sha256": "abc"},
                    "premiere_xml": {"sha256": "def"},
                },
                "parser_versions": {
                    "transcript_parser": "transcript-parser/1",
                    "transcript_validator": "transcript-validator/1",
                    "premiere_parser": "premiere-xml-parser/1",
                },
                "model": {"resolved_id": "qwen3.5:9b"},
            },
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
        self.assertEqual(payload["run_metadata"]["model"]["resolved_id"], "qwen3.5:9b")
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

    @patch("webapp.run_pipeline")
    def test_generate_returns_partial_when_recoverable(self, mock_run_pipeline):
        mock_run_pipeline.side_effect = BiteBuilderError({
            **build_validation_error(
                code="SELECTION-FAILED",
                error_type="runtime_selection_failed",
                message="Selection failed after XML parse.",
                expected_input_format="Transcript + XML + stable model output.",
                next_action="Retry generation after resolving model or temporary failure.",
                stage="selection",
                recoverable=True,
            ),
            "partial": {"status": "partial", "stage": "selection"},
        })
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
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["error"]["code"], "SELECTION-FAILED")

    @patch("webapp.generate_sequence", return_value="<xmeml version='4'></xmeml>")
    @patch("webapp.parse_premiere_xml_safe", return_value=DummySource())
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
