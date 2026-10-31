import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import automation_core as a


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        os.chmod(self.root, 0o700)
        self.state = self.root / 'automation.json'
        self.profile = self.root / 'profile.json'
        self.journal = self.root / 'journal.json'
        self.profile.write_text(json.dumps({'version': 1, 'food': {'preferences_confirmed': True,
            'allergies': [], 'dietary_exclusions': [], 'max_minutes': 25, 'meal': 'breakfast'},
            'activity': {'preferences_confirmed': False}}))
        self.journal.write_text(json.dumps({'version': 1, 'entries': []}))
        os.chmod(self.profile, 0o600)
        os.chmod(self.journal, 0o600)
        self.now = datetime(2026, 10, 31, 7, 5, tzinfo=timezone.utc)  # Berlin 08:05

    def spec(self, kind='morning'):
        return {'owner': 'synthetic-a', 'kind': kind, 'route': 'local', 'zone': 'Europe/Berlin',
                'local_time': '08:00', 'quiet_start': '22:00', 'quiet_end': '07:00',
                'profile': str(self.profile), 'journal': str(self.journal),
                'enabled': True, 'consented_at': '2026-10-30T00:00:00+00:00'}

    def test_morning_reserve_ack_dedupe_and_private_state(self):
        a.configure(self.state, self.spec())
        item = a.reserve(self.state, 'synthetic-a', 'morning', self.now)
        self.assertIn('https://', item['message'])
        self.assertEqual(item['route'], 'local')
        self.assertTrue(a.pre_send(self.state, item['nonce'], self.now))
        self.assertFalse(a.pre_send(self.state, item['nonce'], self.now))  # claimed once, competing worker loses
        self.assertFalse(a.pre_send(self.state, item['nonce'], datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc)))
        self.assertIsNone(a.reserve(self.state, 'synthetic-a', 'morning', self.now))
        self.assertTrue(a.acknowledge(self.state, item['nonce'], 'local', 'synthetic-message-1'))
        self.assertFalse(a.pre_send(self.state, item['nonce'], self.now))
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(a.read_state(self.state)['deliveries']), 1)

    def test_reminder_rechecks_journal_and_revoke(self):
        a.configure(self.state, self.spec('reminder'))
        self.journal.write_text(json.dumps({'version': 1, 'entries': [
            {'type': 'meal', 'date': '2026-10-31', 'name': 'Breakfast'}]}))
        self.assertIsNone(a.reserve(self.state, 'synthetic-a', 'reminder', self.now))
        self.journal.write_text(json.dumps({'version': 1, 'entries': []}))
        item = a.reserve(self.state, 'synthetic-a', 'reminder', self.now)
        self.assertIn('нет данных', item['message'])
        self.journal.write_text(json.dumps({'version': 1, 'entries': [
            {'type': 'meal', 'date': '2026-10-31', 'name': 'Late meal'}]}))
        self.assertFalse(a.pre_send(self.state, item['nonce'], self.now))
        self.assertTrue(a.revoke(self.state, 'synthetic-a', 'reminder'))
        self.assertFalse(a.pre_send(self.state, item['nonce'], self.now))
        self.assertIsNone(a.reserve(self.state, 'synthetic-a', 'reminder', self.now))

    def test_fail_closed_on_route_zone_time_and_private_files(self):
        for key, value in [('route', 'telegram:-1005:3'), ('route', 'origin'), ('zone', 'Wrong/Timezone'),
                           ('local_time', '23:00'), ('quiet_start', '08:00')]:
            with self.subTest(key=key, value=value):
                spec = self.spec()
                spec[key] = value
                with self.assertRaises(ValueError):
                    a.configure(self.state, spec)
        a.configure(self.state, self.spec())
        self.assertIsNone(a.reserve(self.state, 'synthetic-a', 'morning', datetime(2026,10,31,8,0,tzinfo=timezone.utc)))
        os.chmod(self.profile, 0o644)
        with self.assertRaises(PermissionError):
            a.reserve(self.state, 'synthetic-a', 'morning', self.now)
        self.assertEqual(a.read_state(self.state)['deliveries'], [])

    def test_ambiguous_reservation_is_not_retried_and_ack_requires_route(self):
        a.configure(self.state, self.spec())
        item = a.reserve(self.state, 'synthetic-a', 'morning', self.now)
        profile = json.loads(self.profile.read_text())
        profile['food']['allergies'] = ['peanuts']
        self.profile.write_text(json.dumps(profile))
        self.assertFalse(a.pre_send(self.state, item['nonce'], self.now))
        with self.assertRaises(ValueError):
            a.acknowledge(self.state, item['nonce'], 'telegram:123', 'message-1')
        self.assertIsNone(a.reserve(self.state, 'synthetic-a', 'morning', self.now))
        self.assertEqual(a.read_state(self.state)['deliveries'][0]['status'], 'reserved')

    def test_reconfiguration_cannot_revive_old_nonce_or_bypass_daily_cap(self):
        a.configure(self.state, self.spec())
        item = a.reserve(self.state, 'synthetic-a', 'morning', self.now)
        a.revoke(self.state, 'synthetic-a', 'morning')
        a.configure(self.state, self.spec())
        self.assertFalse(a.pre_send(self.state, item['nonce'], self.now))
        self.assertIsNone(a.reserve(self.state, 'synthetic-a', 'morning', self.now))
        changed = self.spec()
        changed['route'] = 'telegram:123'
        a.configure(self.state, changed)
        self.assertIsNone(a.reserve(self.state, 'synthetic-a', 'morning', self.now))

    def test_changed_food_or_activity_preference_invalidates_reserved_idea(self):
        a.configure(self.state, self.spec())
        item = a.reserve(self.state, 'synthetic-a', 'morning', self.now)
        profile = json.loads(self.profile.read_text())
        profile['food']['meal'] = 'dinner'
        self.profile.write_text(json.dumps(profile))
        self.assertFalse(a.pre_send(self.state, item['nonce'], self.now))
        self.assertEqual(a.read_state(self.state)['deliveries'][0]['status'], 'reserved')


if __name__ == '__main__':
    unittest.main()
