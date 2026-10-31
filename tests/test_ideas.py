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
        self.profile['food']['allergies'] = None
        self.assertIsNone(ideas.make_idea(self.profile, self.catalog, self.day)['recipe'])
        self.profile['food']['allergies'] = []
        self.profile['food'].pop('dietary_exclusions')
        self.assertIsNone(ideas.make_idea(self.profile, self.catalog, self.day)['recipe'])
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
        self.profile['food']['max_minutes'] = 5
        self.profile['food']['meal'] = 'dinner'
        self.assertIsNone(ideas.make_idea(self.profile, self.catalog, self.day)['recipe'])

    def test_variety_uses_only_confirmed_delivered_offers(self):
        self.profile['food']['max_minutes'] = 40
        self.profile['food']['meal'] = 'any'
        first = ideas.make_idea(self.profile, self.catalog, self.day)['recipe']['id']
        history = {'offers': [{'date': self.day.isoformat(), 'recipe_id': first, 'delivered': True}]}
        next_day = date(2026, 11, 1)
        self.assertNotEqual(first, ideas.make_idea(self.profile, self.catalog, next_day, history)['recipe']['id'])
        history['offers'][0]['delivered'] = False
        self.assertNotIn('Все подходящие', ' '.join(ideas.make_idea(self.profile, self.catalog, next_day, history)['notes']))
        self.profile['food']['disliked_recipe_ids'] = [first]
        self.assertNotEqual(first, ideas.make_idea(self.profile, self.catalog, self.day)['recipe']['id'])

    def test_weekly_feedback_only_observed_meals(self):
        journal = {'version': 1, 'entries': [
            {'type': 'meal', 'date': '2026-10-24', 'name': 'Old'},
            {'type': 'meal', 'date': '2026-10-27', 'name': 'Оладьи из кабачков'},
            {'type': 'meal', 'date': '2026-10-28', 'name': 'Оладьи из кабачков'},
            {'type': 'workout', 'date': '2026-10-31', 'name': 'Walk'},
        ]}
        result = ideas.weekly_feedback_questions(journal, self.day)
        self.assertEqual(result['logged_food_names'], ['Оладьи из кабачков'])
        self.assertEqual(ideas.weekly_feedback_questions({'entries': []}, self.day)['logged_food_names'], [])

    def test_catalog_rejects_duplicate_and_bad_time(self):
        copy = json.loads(json.dumps(self.catalog))
        copy['recipes'].append(copy['recipes'][0])
        with self.assertRaises(ValueError):
            ideas.validate_catalog(copy)
        copy = json.loads(json.dumps(self.catalog))
        copy['recipes'][0]['cook_minutes'] = True
        with self.assertRaises(ValueError):
            ideas.validate_catalog(copy)

    def test_large_catalog_source_diversity_and_morning_wait_gate(self):
        from urllib.parse import urlparse
        self.assertGreaterEqual(len(self.catalog['recipes']), 40)
        self.assertGreaterEqual(len({urlparse(r['url']).hostname for r in self.catalog['recipes']}), 4)
        self.assertEqual(len({r['url'] for r in self.catalog['recipes']}), len(self.catalog['recipes']))
        self.profile['food']['meal'] = 'breakfast'
        self.profile['food']['max_minutes'] = 40
        for offset in range(14):
            from datetime import timedelta
            result = ideas.make_idea(self.profile, self.catalog, self.day + timedelta(days=offset))
            self.assertLessEqual(result['recipe']['ready_minutes'], 40)
        self.profile['food']['meal'] = 'breakfast'
        self.profile['food']['liked_recipe_ids'] = ['pickuplimes-vanilla-chia-pudding-with-mixed-fruit-289']
        evening = [ideas.make_idea(self.profile, self.catalog, self.day + timedelta(days=offset), occasion='evening')['recipe']['id'] for offset in range(7)]
        self.assertIn('pickuplimes-vanilla-chia-pudding-with-mixed-fruit-289', evening)

    def test_morning_time_limit_includes_passive_wait(self):
        short = {'version': 1, 'recipes': [{'id': 'rest45', 'title_ru': 'Ожидание',
                 'url': 'https://example.org/rest45', 'prep_minutes': 5,
                 'cook_minutes': 0, 'rest_minutes': 45, 'meal': ['breakfast'],
                 'ingredients_hint': ['вода']}]}
        self.profile['food']['max_minutes'] = 5
        self.assertIsNone(ideas.make_idea(self.profile, short, self.day)['recipe'])
        candidate = ideas.make_idea(self.profile, short, self.day, occasion='evening')['recipe']
        self.assertEqual(candidate['ready_minutes'], 50)
        self.assertEqual(candidate['minutes'], 5)


if __name__ == '__main__':
    unittest.main()
