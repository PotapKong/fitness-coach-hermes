import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coach
import food_lookup


class CoachTests(unittest.TestCase):
    def invoke(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            coach.main(['--data-dir', str(self.root), *argv])
        return output.getvalue()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_logging_report_and_png(self):
        self.invoke('target', '--kcal', '2200', '--confirmed-by-user')
        self.invoke('meal', '--date', '2026-10-31', '--name', 'Synthetic meal', '--kcal', '550', '--protein', '32', '--fat', '15', '--carbs', '70', '--source', 'user')
        self.invoke('workout', '--date', '2026-10-31', '--name', 'Walk', '--minutes', '30')
        self.invoke('weight', '--date', '2026-10-31', '--kg', '80')
        report = self.invoke('report', '--date', '2026-10-31')
        self.assertIn('записано 550 ккал / 2200 ккал', report)
        self.assertIn('10-30  ░░░░░░░░░░░░  нет записей', report)
        self.assertIn('Б 32 г · Ж 15 г · У 70 г', report)
        self.assertIn('Вес: 80.0 кг', report)
        from PIL import Image
        image = self.root / 'weekly.png'
        self.invoke('card', '--date', '2026-10-31', '--output', str(image))
        with Image.open(image) as preview:
            self.assertEqual(preview.size, (1080, 1080))
        self.assertEqual(image.stat().st_mode & 0o777, 0o600)
        journal = json.loads((self.root / 'journal.json').read_text())
        self.assertEqual(len(journal['entries']), 3)
        self.assertEqual(journal['entries'][0]['source'], 'user')

    def test_invalid_and_missing_values(self):
        self.assertEqual(coach.aggregate({'entries': [], 'targets': {}}, date(2026, 10, 31))['2026-10-31']['kcal'], 0)
        with self.assertRaises(ValueError):
            coach.day('not-a-date')
        with self.assertRaises(Exception):
            coach.number('nan')
        with self.assertRaises(SystemExit):
            self.invoke('weight', '--kg', '800')
        with self.assertRaises(SystemExit):
            self.invoke('target', '--kcal', '1', '--confirmed-by-user')
        with self.assertRaises(SystemExit):
            self.invoke('target', '--kcal', '2000')
        self.assertFalse((self.root / 'journal.json').exists())

    def test_exclusive_write_lock_and_private_directory(self):
        path = self.root / 'journal.json'
        with coach.write_lock(path):
            with self.assertRaises(RuntimeError):
                self.invoke('meal', '--name', 'Duplicate writer', '--kcal', '200', '--source', 'user')
        self.assertFalse((self.root / '.journal.lock').exists())
        self.invoke('meal', '--name', 'After lock', '--kcal', '200', '--source', 'user')
        self.assertEqual(len(coach.load(path)['entries']), 1)

    def test_retry_event_id_cannot_double_log(self):
        args = ('meal', '--date', '2026-10-31', '--name', 'Breakfast', '--kcal', '320', '--source', 'user', '--event-id', 'tg:42:7')
        self.invoke(*args)
        with self.assertRaises(RuntimeError):
            self.invoke(*args)
        self.assertEqual(len(coach.load(self.root / 'journal.json')['entries']), 1)
        self.assertFalse((self.root / '.journal.lock').exists())

    def test_entry_day_week_snapshots_and_reopen(self):
        self.invoke('meal', '--date', '2026-10-31', '--name', 'Example', '--kcal', '600', '--protein', '30', '--source', 'user')
        entry = json.loads(self.invoke('snapshot', '--date', '2026-10-31', '--scope', 'entry'))
        self.assertEqual(entry['latest_entry']['kcal'], 600)
        self.assertFalse(entry['food_complete'])
        self.invoke('close-day', '--date', '2026-10-31', '--confirmed-by-user')
        day = json.loads(self.invoke('snapshot', '--date', '2026-10-31', '--scope', 'day'))
        self.assertTrue(day['food_complete'])
        self.assertEqual(day['macros_g']['protein'], 30)
        self.assertIsNone(day['macros_g']['fat'])
        self.assertEqual(day['week_to_date']['confirmed_complete_food_days'], 1)
        week = json.loads(self.invoke('snapshot', '--date', '2026-10-31', '--scope', 'week'))
        self.assertEqual(week['start'], '2026-10-26')
        self.assertEqual(week['end'], '2026-11-01')
        self.assertEqual(week['confirmed_complete_food_days'], 1)
        self.assertEqual(week['average_logged_kcal_on_complete_days'], 600)
        self.assertEqual(week['days'][0]['logged_kcal'], None)
        self.invoke('meal', '--date', '2026-10-31', '--name', 'Later meal', '--kcal', '300', '--source', 'user')
        self.assertFalse(json.loads(self.invoke('snapshot', '--date', '2026-10-31', '--scope', 'day'))['food_complete'])
        with self.assertRaises(SystemExit):
            self.invoke('close-day', '--date', '2026-10-30', '--confirmed-by-user')

    def test_weekly_user_range_requires_seven_complete_days(self):
        self.invoke('target', '--kcal', '2000', '--weekly-avg-min', '1900', '--weekly-avg-max', '2100', '--confirmed-by-user')
        for day in range(26, 33):
            d = f'2026-10-{day}' if day <= 31 else '2026-11-01'
            self.invoke('meal', '--date', d, '--name', 'Synthetic day', '--kcal', '2000', '--source', 'label', '--event-id', f'demo:{d}')
            if day <= 31:
                self.invoke('close-day', '--date', d, '--confirmed-by-user')
        week = json.loads(self.invoke('snapshot', '--date', '2026-11-01', '--scope', 'week'))
        self.assertIsNone(week['weekly_range_status'])
        self.invoke('close-day', '--date', '2026-11-01', '--confirmed-by-user')
        week = json.loads(self.invoke('snapshot', '--date', '2026-11-01', '--scope', 'week'))
        self.assertEqual(week['weekly_range_status'], 'within_user_range')
        self.invoke('meal', '--date', '2026-11-01', '--name', 'Late meal', '--kcal', '100', '--source', 'photo-estimate')
        self.assertIsNone(json.loads(self.invoke('snapshot', '--date', '2026-11-01', '--scope', 'week'))['weekly_range_status'])

    def test_usda_energy_units(self):
        sample = {'fdcId': 171287, 'description': 'Egg, whole, raw, fresh', 'foodNutrients': [
            {'nutrientName': 'Energy', 'unitName': 'kcal', 'value': 143.0},
            {'nutrientName': 'Energy', 'unitName': 'kJ', 'value': 599.0},
            {'nutrientName': 'Protein', 'unitName': 'g', 'value': 12.6},
        ]}
        result = food_lookup.food_nutrients(sample)
        self.assertEqual(result['per_100g']['kcal'], 143)
        self.assertEqual(result['per_100g']['protein_g'], 12.6)
        self.assertIsNone(result['per_100g']['fat_g'])
        sample['foodNutrients'] = [sample['foodNutrients'][1]]
        self.assertIsNone(food_lookup.food_nutrients(sample)['per_100g']['kcal'])

    def test_usda_invalid_number_cannot_enter_journal(self):
        for bad in (float('nan'), float('inf'), -1, True):
            with self.subTest(bad=bad):
                food = {'fdcId': 1, 'description': 'bad', 'foodNutrients': [
                    {'nutrientName': 'Energy', 'unitName': 'kcal', 'value': bad}]}
                with patch.object(food_lookup, 'by_id', side_effect=lambda _: food_lookup.food_nutrients(food)):
                    with self.assertRaises(ValueError):
                        self.invoke('food', '--fdc-id', '1', '--grams', '100')
        self.assertFalse((self.root / 'journal.json').exists())

    def test_weighed_food_micros_activity_and_missing_macros(self):
        fixture = {'fdcId': 171287, 'description': 'Egg, whole, raw, fresh', 'foodNutrients': [
            {'nutrient': {'id': 1008, 'name': 'Energy', 'unitName': 'kcal'}, 'amount': 143},
            {'nutrient': {'id': 1062, 'name': 'Energy', 'unitName': 'kJ'}, 'amount': 599},
            {'nutrient': {'id': 1089, 'name': 'Iron, Fe', 'unitName': 'mg'}, 'amount': 1.75},
        ]}
        with patch.object(food_lookup, 'by_id', return_value=food_lookup.food_nutrients(fixture)):
            self.invoke('food', '--date', '2026-10-31', '--fdc-id', '171287', '--grams', '120')
        self.invoke('meal', '--date', '2026-10-31', '--name', 'Unspecified macros', '--kcal', '100', '--source', 'user')
        self.invoke('workout', '--date', '2026-10-31', '--name', 'Squats', '--minutes', '30', '--sets', '3', '--reps', '8', '--load-kg', '40')
        report = self.invoke('report', '--date', '2026-10-31')
        self.assertIn('записано 272 ккал', report)
        self.assertIn('Б — г', report)
        self.assertIn('iron_mg: 2.1 (частично)', report)
        self.assertIn('960 кг·повт.', report)
        history = json.loads(self.invoke('trends', '--date', '2026-10-31', '--days', '7'))
        self.assertEqual(history['logged_food_days'], 1)
        self.assertEqual(history['training_minutes'], 30)
        self.assertEqual(history['series'][-2]['logged_kcal'], None)
        self.assertEqual(history['series'][-1]['micros']['iron_mg']['known_meals'], 1)
        from PIL import Image
        for view in ('nutrition', 'activity', 'micros', 'micro-trend'):
            image = self.root / f'{view}.png'
            self.invoke('card', '--date', '2026-10-31', '--view', view, '--output', str(image))
            with Image.open(image) as preview:
                self.assertEqual(preview.size, (1080, 1080))
            self.assertEqual(image.stat().st_mode & 0o777, 0o600)

    def test_usda_errors_do_not_expose_key(self):
        with patch.object(food_lookup.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError('https://example.test/?api_key=PRIVATE', 429, 'rate limit', {}, None)):
            with self.assertRaises(RuntimeError) as caught:
                food_lookup.fetch_json('https://example.test/?api_key=PRIVATE')
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertIn('429', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
