import contextlib
import csv
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import segment_history


class BytesResponse:
    def __init__(self, payload: bytes):
        self._payload = io.BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload.read()


class SegmentHistoryTest(unittest.TestCase):
    def test_parse_curl_headers_extracts_values(self):
        curl_text = """curl 'https://www.strava.com/athlete/segments/123/history' \\
  -H 'Cookie: foo=bar; baz=qux' \\
  -H 'X-CSRF-Token: csrf123' \\
  --header 'User-Agent: CustomAgent/1.0'"""

        headers = segment_history.parse_curl_headers(curl_text)

        self.assertEqual(headers["cookie"], "foo=bar; baz=qux")
        self.assertEqual(headers["x-csrf-token"], "csrf123")
        self.assertEqual(headers["user-agent"], "CustomAgent/1.0")

    def test_parse_curl_headers_extracts_cookie_flag(self):
        curl_text = """curl 'https://www.strava.com/athlete/segments/456/history' \\
  -b 'sp=abc; xp_session_identifier=xyz' \\
  -H 'X-CSRF-Token: csrf456'"""

        headers = segment_history.parse_curl_headers(curl_text)

        self.assertEqual(headers["cookie"], "sp=abc; xp_session_identifier=xyz")
        self.assertEqual(headers["x-csrf-token"], "csrf456")

    def test_parse_curl_headers_handles_windows_caret(self):
        curl_text = """curl "https://www.strava.com/athlete/segments/789/history" ^
  -H "X-CSRF-Token: caret-token" ^
  -b "caret-cookie=1" ^
  --header "User-Agent: WindowsTerminal/1.0" """

        headers = segment_history.parse_curl_headers(curl_text)

        self.assertEqual(headers["cookie"], "caret-cookie=1")
        self.assertEqual(headers["x-csrf-token"], "caret-token")
        self.assertEqual(headers["user-agent"], "WindowsTerminal/1.0")

    def test_write_results_csv_creates_file(self):
        header = ["År", "segment"]
        rows = [["2024", "alpha"], ["2023", "beta"]]
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        self.addCleanup(lambda: os.path.exists(temp_path) and os.remove(temp_path))

        segment_history._write_results_csv(header, rows, path=temp_path)

        with open(temp_path, newline="", encoding="utf-8") as csv_file:
            reader = list(csv.reader(csv_file))

        self.assertEqual(reader[0], header)
        self.assertEqual(reader[1:], rows)

    def test_build_headers_uses_curl_file(self):
        curl_text = """curl 'https://www.strava.com/athlete/segments/123/history' \\
  -H 'Cookie: cookie=1' \\
  -H 'X-CSRF-Token: token123' \\
  -H 'User-Agent: UA/99'"""

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as temp_file:
            temp_file.write(curl_text)
            temp_path = temp_file.name

        self.addCleanup(lambda: os.path.exists(temp_path) and os.remove(temp_path))
        original_path = segment_history.CURL_SNIPPET_PATH
        segment_history.CURL_SNIPPET_PATH = temp_path
        self.addCleanup(
            lambda: setattr(segment_history, "CURL_SNIPPET_PATH", original_path)
        )

        with mock.patch.dict(
            os.environ,
            {
                "STRAVA_COOKIE_HEADER": "",
                "STRAVA_CSRF_TOKEN": "",
                "STRAVA_USER_AGENT": "",
            },
            clear=False,
        ):
            headers = segment_history._build_headers(segment_id="99")

        self.assertEqual(headers["Cookie"], "cookie=1")
        self.assertEqual(headers["X-CSRF-Token"], "token123")
        self.assertEqual(headers["User-Agent"], "UA/99")

    def test_fetch_segment_history_returns_efforts(self):
        payload = {"efforts": [{"id": 1, "elapsed_time": 120}]}

        def fake_opener(req):
            self.assertEqual(
                req.full_url, segment_history._segment_history_url("987654")
            )
            headers = dict(req.header_items())
            self.assertTrue(headers["Cookie"])
            return BytesResponse(json_bytes)

        json_bytes = json.dumps(payload).encode("utf-8")

        with mock.patch.dict(
            os.environ,
            {
                "STRAVA_COOKIE_HEADER": "cookie=1",
                "STRAVA_CSRF_TOKEN": "token",
                "STRAVA_USER_AGENT": "UA/1",
            },
            clear=False,
        ):
            result = segment_history.fetch_segment_history(
                opener=fake_opener, segment_id="987654"
            )

        self.assertIn("efforts", result)
        self.assertEqual(result["efforts"], payload["efforts"])

    def test_efforts_to_sheet_rows_formats_columns(self):
        effort = {
            "start_date_local": "2024-05-01T10:00:00Z",
            "segment": {"id": 555},
            "elapsed_time": 83,
            "id": 8888,
            "avg_watts": 320.5,
            "average_hr": 152,
            "avg_cadence": 89.7,
        }

        segment_name_map = {"555": "soria"}

        rows = segment_history.efforts_to_sheet_rows(
            [effort], segment_name_map=segment_name_map, navn_value="Morten"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            "\t".join(
                [
                    "2024",
                    "soria",
                    "Morten",
                    "01:23",
                    "https://www.strava.com/segment_efforts/8888",
                    "321",
                    "152",
                    "90",
                ]
            ),
        )

    def test_efforts_to_sheet_rows_picks_fastest_per_year(self):
        efforts = [
            {
                "start_date_local": "2024-05-01T08:00:00Z",
                "segment": {"id": 123},
                "elapsed_time": 150,
                "id": 1,
            },
            {
                "start_date_local": "2024-06-01T08:00:00Z",
                "segment": {"id": 123},
                "elapsed_time": 120,
                "id": 2,
            },
            {
                "start_date_local": "2024-07-01T08:00:00Z",
                "segment": {"id": 999},
                "elapsed_time": 200,
                "id": 3,
            },
        ]

        rows = segment_history.efforts_to_sheet_rows(
            efforts,
            segment_name_map={"123": "alpha", "999": "beta"},
            navn_value="Test",
        )

        self.assertEqual(len(rows), 2)
        self.assertIn("alpha", rows[0])
        self.assertIn("02:00", rows[0])
        self.assertIn("segment_efforts/2", rows[0])
        self.assertIn("beta", rows[1])
        self.assertIn("03:20", rows[1])

    def test_build_segment_name_map(self):
        rows = [
            {
                "Id-navn": "soria",
                "Segment": "https://www.strava.com/segments/4580190",
            },
            {"Id-navn": "", "Segment": ""},
        ]

        mapping = segment_history.build_segment_name_map(rows)

        self.assertEqual(mapping["4580190"], "soria")

    def test_extract_segment_ids_preserves_order(self):
        rows = [
            {"Segment": "https://www.strava.com/segments/1"},
            {"Segment": "https://www.strava.com/segments/2?filter=overall"},
            {"Segment": "https://www.strava.com/segments/1"},
            {"Segment": "https://www.strava.com/segments/3"},
        ]

        result = segment_history.extract_segment_ids(rows)

        self.assertEqual(result, ["1", "2", "3"])

    def test_fetch_segment_metadata_reads_tsv(self):
        tsv = "Id-navn\tSegment\nsoria\thttps://www.strava.com/segments/4580190\n"

        def fake_opener(req):
            self.assertEqual(
                req.full_url, segment_history.GOOGLE_SHEET_EXPORT_URL
            )
            return BytesResponse(tsv.encode("utf-8"))

        rows = segment_history.fetch_segment_metadata(opener=fake_opener)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Id-navn"], "soria")
        self.assertEqual(
            rows[0]["Segment"], "https://www.strava.com/segments/4580190"
        )

    def test_load_or_prompt_navn_prefers_cached_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "navn.txt")
            with open(cache_path, "w", encoding="utf-8") as cache_file:
                cache_file.write("Cached")

            navn = segment_history.load_or_prompt_navn(
                cache_path=cache_path,
                input_func=lambda _: self.fail("should not prompt when cache exists"),
                suggested_names=["Ignored"],
            )

            self.assertEqual(navn, "Cached")

    def test_load_or_prompt_navn_prompts_and_persists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "navn.txt")
            with contextlib.redirect_stdout(io.StringIO()):
                navn = segment_history.load_or_prompt_navn(
                    cache_path=cache_path,
                    input_func=lambda _: "Fresh",
                    suggested_names=[],
                )

            self.assertEqual(navn, "Fresh")
            with open(cache_path, "r", encoding="utf-8") as cache_file:
                self.assertEqual(cache_file.read().strip(), "Fresh")

    def test_load_or_prompt_navn_supports_numeric_selection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "navn.txt")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                navn = segment_history.load_or_prompt_navn(
                    cache_path=cache_path,
                    input_func=lambda _: "3.",
                    suggested_names=["Ana", "Bob", "Cara"],
                )

            self.assertEqual(navn, "Cara")
            self.assertIn("1. Ana", buffer.getvalue())
            with open(cache_path, "r", encoding="utf-8") as cache_file:
                self.assertEqual(cache_file.read().strip(), "Cara")

    def test_fetch_athlete_names_returns_values(self):
        tsv = "Lag\tNavn\nA\tTor\nB\tLise\n"

        def fake_opener(req):
            self.assertEqual(
                req.full_url,
                segment_history.UTOEVERE_SHEET_EXPORT_URL,
            )
            return BytesResponse(tsv.encode("utf-8"))

        names = segment_history.fetch_athlete_names(limit=2, opener=fake_opener)

        self.assertEqual(names, ["Tor", "Lise"])


if __name__ == "__main__":
    unittest.main()
