"""
Offline tests for the pipeline's parsing, filtering and validation logic.

No network access required — HTTP responses are stubbed with recorded-shape
fixtures. Run with:  python -m unittest discover -s tests -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import common  # noqa: E402
import queue_manager  # noqa: E402
import researcher  # noqa: E402
import retriever  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise retriever.requests.RequestException(f"HTTP {self.status_code}")


# The Met object that actually is the Mérode Altarpiece.
MERODE_OBJECT = {
    "title": "Annunciation Triptych (Merode Altarpiece)",
    "artistDisplayName": "Workshop of Robert Campin",
    "objectDate": "ca. 1427-32",
    "medium": "Oil on oak",
    "dimensions": "Overall (open): 25 3/8 x 46 3/8 in.",
    "department": "The Cloisters",
    "creditLine": "The Cloisters Collection, 1956",
    "objectURL": "https://www.metmuseum.org/art/collection/search/470304",
    "primaryImage": "https://images.metmuseum.org/CRDImages/cl/original/merode.jpg",
    "primaryImageSmall": "https://images.metmuseum.org/CRDImages/cl/web-large/merode.jpg",
    "additionalImages": ["https://images.metmuseum.org/CRDImages/cl/original/detail1.jpg"],
}

# The unrelated painting the old code returned for a "Mérode Altarpiece" query.
MEMLING_OBJECT = {
    "title": "The Annunciation",
    "artistDisplayName": "Hans Memling",
    "objectDate": "ca. 1465-70",
    "medium": "Oil on wood",
    "dimensions": "73 1/4 x 45 1/4 in. (186.1 x 114.9 cm)",
    "department": "European Paintings",
    "creditLine": "Gift of J. Pierpont Morgan, 1917",
    "objectURL": "https://www.metmuseum.org/art/collection/search/437490",
    "primaryImage": "https://images.metmuseum.org/CRDImages/ep/original/DP240360.jpg",
}


class TestMetRelevanceFilter(unittest.TestCase):
    """The Met search must not hand an unrelated artwork to the model."""

    def _patched_get(self, object_map, search_ids):
        def fake_get(url, params=None, headers=None, timeout=None):
            if url == retriever.MET_SEARCH_URL:
                return FakeResponse({"objectIDs": search_ids})
            for object_id, obj in object_map.items():
                if url.endswith(f"/{object_id}"):
                    return FakeResponse(obj)
            return FakeResponse({}, status_code=404)

        return fake_get

    def test_rejects_unrelated_first_hit_and_finds_real_match(self):
        # Memling is returned first, exactly as the live API did.
        object_map = {437490: MEMLING_OBJECT, 470304: MERODE_OBJECT}
        with mock.patch.object(
            retriever.requests, "get", self._patched_get(object_map, [437490, 470304])
        ):
            source, images = retriever.fetch_met_object("Mérode Altarpiece")

        self.assertIsNotNone(source, "should have found the real Mérode object")
        self.assertIn("Merode Altarpiece", source["raw_text"])
        self.assertNotIn("Memling", source["raw_text"])
        self.assertEqual(source["title_match_score"], 1.0)
        self.assertTrue(any(i["role"] == "full_resolution" for i in images))

    def test_drops_the_source_entirely_when_nothing_matches(self):
        object_map = {437490: MEMLING_OBJECT}
        with mock.patch.object(
            retriever.requests, "get", self._patched_get(object_map, [437490])
        ):
            source, images = retriever.fetch_met_object("Mérode Altarpiece")

        self.assertIsNone(source, "an unrelated object must not become a source")
        self.assertEqual(images, [])


class TestWikidataHardening(unittest.TestCase):
    def test_escapes_quotes_in_sparql_literal(self):
        escaped = retriever._escape_sparql_literal('Whistler\'s "Mother"')
        self.assertNotIn('"M', escaped.replace('\\"', ""))
        self.assertIn('\\"', escaped)

    def test_filters_skolemised_blank_nodes(self):
        genid = "http://www.wikidata.org/.well-known/genid/f1664f0be4208093"
        self.assertFalse(retriever._is_usable_value(genid))
        self.assertTrue(retriever._is_usable_value("Robert Campin"))

    def test_blank_node_creator_is_not_emitted(self):
        payload = {
            "results": {
                "bindings": [
                    {
                        "item": {"value": "http://www.wikidata.org/entity/Q285392"},
                        "creatorLabel": {
                            "value": "http://www.wikidata.org/.well-known/genid/abc123"
                        },
                        "mediumLabel": {"value": "oil paint"},
                    }
                ]
            }
        }
        with mock.patch.object(
            retriever.requests, "get", lambda *a, **k: FakeResponse(payload)
        ):
            source = retriever.fetch_wikidata("Mérode Altarpiece")

        self.assertIsNotNone(source)
        self.assertNotIn("genid", source["raw_text"])
        self.assertIn("Medium: oil paint", source["raw_text"])


class TestWikipediaImageCapture(unittest.TestCase):
    def test_lead_image_is_kept_not_discarded(self):
        payload = {
            "extract": "The Mérode Altarpiece is an oil on oak panel triptych.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Merode"}},
            "originalimage": {"source": "https://upload.wikimedia.org/full.jpg", "width": 3000, "height": 2000},
            "thumbnail": {"source": "https://upload.wikimedia.org/thumb.jpg", "width": 320, "height": 213},
        }
        with mock.patch.object(
            retriever.requests, "get", lambda *a, **k: FakeResponse(payload)
        ):
            source, images = retriever.fetch_wikipedia_summary("Mérode Altarpiece")

        self.assertIsNotNone(source)
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0]["url"], "https://upload.wikimedia.org/full.jpg")
        self.assertEqual(images[0]["role"], "full_resolution")


class TestReasoningStripping(unittest.TestCase):
    def test_strips_think_tags(self):
        raw = "<think>I should consider the sources.</think>\n# Mérode Altarpiece\n\ntext"
        self.assertTrue(researcher.strip_reasoning(raw).startswith("# Mérode Altarpiece"))

    def test_strips_unclosed_think_block(self):
        self.assertEqual(researcher.strip_reasoning("<think>never closed..."), "")

    def test_strips_unfenced_preamble_before_the_entry(self):
        raw = "Here's a thinking process:\n\n1. Analyze request\n\n# Mérode Altarpiece\n\n## 1. Basic Information"
        cleaned = researcher.strip_reasoning(raw)
        self.assertTrue(cleaned.startswith("# Mérode Altarpiece"))
        self.assertNotIn("thinking process", cleaned)

    def test_committed_broken_draft_is_now_rejected(self):
        """Regression: the pure chain-of-thought draft in the repo must not pass."""
        broken = REPO_ROOT / "archive" / "M_rode_Altarpiece" / "draft_entry.md"
        if not broken.exists():
            self.skipTest("sample draft not present")
        cleaned = researcher.strip_reasoning(broken.read_text(encoding="utf-8"))
        self.assertTrue(
            researcher.missing_sections(cleaned),
            "the reasoning-only draft must be reported as missing required sections",
        )


class TestSectionValidation(unittest.TestCase):
    def test_complete_entry_passes(self):
        entry = "# Art\n" + "\n".join(f"{s}\ncontent" for s in researcher.REQUIRED_SECTIONS)
        self.assertEqual(researcher.missing_sections(entry), [])

    def test_incomplete_entry_reports_gaps(self):
        entry = "# Art\n## 1. Basic Information\ncontent"
        self.assertEqual(len(researcher.missing_sections(entry)), 6)


class TestQueueManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "queue.csv"
        self.path.write_text(
            "artwork_name,status\nMérode Altarpiece,\nAnnunciation (Leonardo),\n",
            encoding="utf-8",
        )
        patcher = mock.patch.object(queue_manager, "QUEUE_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_queue_advances_after_marking_done(self):
        rows = queue_manager.load_rows()
        self.assertEqual(queue_manager.next_artwork(rows), "Mérode Altarpiece")

        self.assertTrue(queue_manager.mark_done(rows, "Mérode Altarpiece"))
        queue_manager.save_rows(rows)

        rows = queue_manager.load_rows()
        self.assertEqual(
            queue_manager.next_artwork(rows),
            "Annunciation (Leonardo)",
            "the queue must move on instead of repeating the first row forever",
        )

    def test_mark_done_matches_despite_accent_differences(self):
        rows = queue_manager.load_rows()
        self.assertTrue(queue_manager.mark_done(rows, "Merode Altarpiece"))

    def test_unknown_artwork_is_not_marked(self):
        rows = queue_manager.load_rows()
        self.assertFalse(queue_manager.mark_done(rows, "Some Other Painting"))

    def test_exhausted_queue_returns_none(self):
        rows = queue_manager.load_rows()
        for row in rows:
            queue_manager.mark_done(rows, row["artwork_name"])
        self.assertIsNone(queue_manager.next_artwork(rows))


class TestPathGuards(unittest.TestCase):
    def test_empty_name_never_writes_to_archive_root(self):
        for bad in ("", "   ", "!!!"):
            with self.assertRaises(ValueError):
                common.artwork_dir(bad)

    def test_valid_name_produces_nested_dir(self):
        self.assertEqual(
            common.artwork_dir("Mérode Altarpiece"),
            Path("archive") / "M_rode_Altarpiece",
        )

    def test_require_artwork_name_rejects_blank(self):
        with self.assertRaises(SystemExit):
            common.require_artwork_name(["retriever.py", "   "], "retriever.py")
        with self.assertRaises(SystemExit):
            common.require_artwork_name(["retriever.py"], "retriever.py")


if __name__ == "__main__":
    unittest.main()
