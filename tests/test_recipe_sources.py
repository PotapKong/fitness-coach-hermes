import json
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import recipe_sources


class SourcesTests(unittest.TestCase):
    def test_jsonld_candidate_and_time(self):
        body = '''<html><script type="application/ld+json">{"@graph": [{"@type": "Recipe", "name": "Zucchini fritters", "prepTime": "PT10M", "cookTime": "PT20M", "totalTime": "PT30M"}]}</script></html>'''
        result = recipe_sources.stage('https://example.org/recipes/fritters', ['example.org'], lambda _: body)
        self.assertEqual(result['source_title'], 'Zucchini fritters')
        self.assertEqual(result['total_minutes'], 30)
        self.assertEqual(result['status'], 'candidate_needs_human_review')

    def test_reject_untrusted_url_and_bad_data(self):
        self.assertFalse(recipe_sources.hostname_allowed('https://example.org.evil.test/path', ['example.org']))
        self.assertFalse(recipe_sources.hostname_allowed('http://example.org/path', ['example.org']))
        self.assertFalse(recipe_sources.hostname_allowed('https://user@example.org/path', ['example.org']))
        with self.assertRaises(ValueError):
            recipe_sources.stage('http://localhost/secret', ['example.org'], lambda _: '')
        self.assertIsNone(recipe_sources.minutes('not-a-duration'))
        self.assertEqual(recipe_sources.minutes('PT12H30M'), 750)
        with self.assertRaises(ValueError):
            recipe_sources.stage('https://example.org/a', ['example.org'], lambda _: '<html>no schema</html>')


if __name__ == '__main__':
    unittest.main()
