import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import coach
import history_db

ROOT = Path(__file__).resolve().parents[1]


class HistoryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.journal = self.root / 'journal.json'
        self.db = self.root / 'journal.sqlite3'

    def call_coach(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            coach.main(['--data-dir', str(self.root), *args])

    def test_all_history_survives_new_process_and_correction(self):
        self.call_coach('meal', '--date', '2021-01-05', '--name', 'Old', '--kcal', '250', '--source', 'user', '--event-id', 'old:1')
        self.call_coach('meal', '--date', '2026-10-31', '--name', 'New', '--source', 'user', '--event-id', 'new:1')
        self.call_coach('workout', '--date', '2026-10-31', '--name', 'Walk', '--minutes', '30', '--event-id', 'walk:1')
        self.call_coach('weight', '--date', '2026-10-31', '--kg', '80', '--event-id', 'weight:1')
        self.call_coach('close-day', '--date', '2021-01-05', '--confirmed-by-user')
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        result = subprocess.run([sys.executable, str(ROOT / 'history_db.py'), '--data-dir', str(self.root),
                                 'history', '--limit', '2', '--offset', '2'], capture_output=True, text=True, check=True)
        page = json.loads(result.stdout)
        self.assertEqual(page['total'], 4)
        self.assertEqual(len(page['entries']), 2)
        self.assertFalse(page['has_more'])
        self.assertEqual(page['entries'][-1]['name'], 'Old')
        months = history_db.progress(self.db)['months']
        self.assertEqual(months[-1]['month'], '2021-01')
        self.assertEqual(months[-1]['avg_recorded_kcal_on_complete_days'], 250)
        self.assertEqual(months[0]['logged_workout_minutes'], 30)
        self.assertEqual(months[0]['last_recorded_weight_kg'], 80)
        self.call_coach('void-entry', '--event-id', 'old:1', '--correction-id', 'fix:1', '--reason', 'Wrong', '--confirmed-by-user')
        self.assertEqual(history_db.read_entries(self.db)['total'], 3)
        self.assertEqual(history_db.read_entries(self.db, include_voided=True)['total'], 4)
        self.assertEqual(history_db.read_corrections(self.db)['corrections'][0]['correction_id'], 'fix:1')
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM corrections').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM complete_days').fetchone()[0], 0)

    def test_json_recovers_database_index_after_interrupted_sync(self):
        self.call_coach('meal', '--date', '2026-10-31', '--name', 'First', '--source', 'user', '--event-id', 'first')
        data = coach.load(self.journal)
        data['entries'].append({'date': '2026-10-31', 'type': 'meal', 'name': 'Second', 'kcal': None, 'source': 'user', 'event_id': 'second'})
        with patch.object(history_db, 'sync', side_effect=OSError('simulated disk issue')):
            with self.assertRaises(OSError):
                coach.save(self.journal, data)
        self.assertEqual(history_db.read_entries(self.db)['total'], 1)
        self.assertEqual(json.loads(self.journal.read_text())['entries'][-1]['name'], 'Second')
        self.assertEqual(history_db.sync_from_json(self.journal), 2)
        self.assertEqual(history_db.read_entries(self.db)['total'], 2)

    def test_sqlite_is_private_and_not_a_session_or_public_repo(self):
        self.call_coach('meal', '--date', '2026-10-31', '--name', 'Synthetic', '--source', 'user', '--event-id', 'synthetic')
        self.assertEqual(self.db.parent, self.journal.parent)
        os.chmod(self.db, 0o644)
        with self.assertRaises(PermissionError):
            history_db.read_entries(self.db)
        os.chmod(self.db, 0o600)
        with self.assertRaises(ValueError):
            history_db.read_entries(self.db, limit=501)

    def test_existing_json_migrates_without_modifying_source(self):
        old = {'version': 1, 'targets': {}, 'food_complete_days': [], 'entries': [
            {'type': 'meal', 'date': '2020-01-01', 'name': 'Legacy', 'kcal': None, 'source': 'user'}]}
        self.journal.write_text(json.dumps(old))
        os.chmod(self.journal, 0o600)
        before = self.journal.read_bytes()
        self.assertFalse(self.db.exists())
        self.assertEqual(history_db.sync_from_json(self.journal), 1)
        self.assertEqual(self.journal.read_bytes(), before)
        self.assertEqual(history_db.read_entries(self.db)['entries'][0]['name'], 'Legacy')

    def test_corrupt_sqlite_quarantine_and_rebuild_from_json(self):
        self.call_coach('meal', '--date', '2026-10-31', '--name', 'Before', '--source', 'user', '--event-id', 'before')
        before = self.journal.read_bytes()
        self.db.write_bytes(b'not sqlite')
        os.chmod(self.db, 0o600)
        with self.assertRaises(sqlite3.DatabaseError):
            self.call_coach('meal', '--date', '2026-10-31', '--name', 'After', '--source', 'user', '--event-id', 'after')
        self.assertNotEqual(self.journal.read_bytes(), before)
        with self.assertRaises(SystemExit):
            history_db.main(['--data-dir', str(self.root), 'repair'])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            history_db.main(['--data-dir', str(self.root), 'repair', '--confirmed-by-user'])
        receipt = json.loads(out.getvalue())
        self.assertEqual(receipt['status'], 'rebuilt')
        self.assertEqual(receipt['indexed_entries'], 2)
        self.assertTrue(Path(receipt['quarantined']).is_file())
        self.assertEqual(history_db.read_entries(self.db)['total'], 2)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')


if __name__ == '__main__':
    unittest.main()
