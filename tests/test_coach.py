import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

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
        self.invoke('target', '--kcal', '2200')
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
        self.assertFalse((self.root / 'journal.json').exists())

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


if __name__ == '__main__':
    unittest.main()
