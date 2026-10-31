import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ideas


class IdeasTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(Path(ideas.__file__).with_name('recipes.json').read_text())
        self.day = date(2026, 10, 31)
        self.profile = {
            'version': 1,
            'food': {'preferences_confirmed': True, 'allergies': [], 'dietary_exclusions': [],
                     'max_minutes': 20, 'meal': 'breakfast', 'disliked_ingredients': []},
            'activity': {'preferences_confirmed': True, 'cleared_for_general_activity': True,
                         'preferred_activities': ['walking']},
        }

    def test_source_linked_selection_and_time_filter(self):
        result = ideas.make_idea(self.profile, self.catalog, self.day)
        self.assertLessEqual(result['recipe']['minutes'], 20)
        self.assertIn(result['recipe']['url'], [r['url'] for r in self.catalog['recipes']])
        self.assertIn('прогулка', result['activity'])
        self.assertEqual(result, ideas.make_idea(self.profile, self.catalog, self.day))

    def test_allergy_and_exclusions_fail_closed(self):
        self.profile['food']['allergies'] = ['egg']
        self.assertIsNone(ideas.make_idea(self.profile, self.catalog, self.day)['recipe'])
        self.profile['food']['allergies'] = []
        self.profile['food']['dietary_exclusions'] = ['fish']
        self.assertIsNone(ideas.make_idea(self.profile, self.catalog, self.day)['recipe'])
        self.profile['activity']['cleared_for_general_activity'] = False
        self.assertIsNone(ideas.make_idea(self.profile, self.catalog, self.day)['activity'])

    def test_unconfirmed_preferences_and_private_file(self):
        self.assertIsNone(ideas.make_idea({}, self.catalog, self.day)['recipe'])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'profile.json'
            path.write_text(json.dumps(self.profile))
            os.chmod(path, 0o644)
            with self.assertRaises(PermissionError):
                ideas.read_private_profile(path)
            os.chmod(path, 0o600)
            self.assertEqual(ideas.read_private_profile(path), self.profile)

    def test_no_match_is_not_invented(self):
        self.profile['food']['disliked_ingredients'] = ['а']
        self.profile['food']['meal'] = 'snack'
        self.assertIsNone(ideas.make_idea(self.profile, self.catalog, self.day)['recipe'])


if __name__ == '__main__':
    unittest.main()
