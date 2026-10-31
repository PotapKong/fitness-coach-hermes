import json
import contextlib
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock
import update_skill

ROOT = pathlib.Path(__file__).resolve().parents[1]


class UpdaterTests(unittest.TestCase):
    def test_check_has_no_local_filesystem_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / 'new-parent/fitness-coach-hermes'
            with mock.patch.object(update_skill, 'remote_sha', return_value='a' * 40), \
                 mock.patch.object(sys, 'argv', ['update_skill.py', '--check', '--target', str(target)]), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                update_skill.main()
            self.assertIn('upstream update available', output.getvalue())
            self.assertFalse(target.parent.exists())

    def test_catalog_and_package_are_valid(self):
        self.assertGreaterEqual(update_skill.validate(ROOT), 48)

    def test_install_preserves_backup_and_refuses_unmanaged_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / 'skills/fitness-coach-hermes'
            self.assertIsNone(update_skill.install(ROOT, target, 'a' * 40))
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve().parent, pathlib.Path(tmp) / 'skill-releases/fitness-coach-hermes')
            self.assertTrue((target / 'history_db.py').is_file())
            self.assertTrue((target / 'automation_core.py').is_file())
            self.assertEqual((target / update_skill.MARKER).read_text().strip(), 'a' * 40)
            backup = update_skill.install(ROOT, target, 'b' * 40)
            self.assertEqual(backup.parent, pathlib.Path(tmp) / 'skill-releases/fitness-coach-hermes')
            self.assertEqual((backup / update_skill.MARKER).read_text().strip(), 'a' * 40)
            self.assertEqual((target / update_skill.MARKER).read_text().strip(), 'b' * 40)
            (target / 'private-data').mkdir()
            with self.assertRaisesRegex(ValueError, 'extra files'):
                update_skill.install(ROOT, target, 'c' * 40)
            self.assertTrue((target / 'private-data').is_dir())
            self.assertEqual((target / update_skill.MARKER).read_text().strip(), 'b' * 40)

    def test_interrupted_pointer_swap_leaves_previous_skill_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / 'skills/fitness-coach-hermes'
            update_skill.install(ROOT, target, 'a' * 40)
            with mock.patch.object(update_skill.os, 'replace', side_effect=OSError('interrupted')):
                with self.assertRaisesRegex(OSError, 'interrupted'):
                    update_skill.install(ROOT, target, 'b' * 40)
            self.assertTrue(target.is_symlink())
            self.assertEqual((target / update_skill.MARKER).read_text().strip(), 'a' * 40)
            self.assertEqual((target / 'SKILL.md').read_text(), (ROOT / 'SKILL.md').read_text())

    def test_unmanaged_target_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / 'fitness-coach-hermes'
            target.mkdir()
            (target / 'keep.txt').write_text('private')
            with self.assertRaisesRegex(ValueError, 'not a managed link'):
                update_skill.install(ROOT, target, 'a' * 40)
            self.assertEqual((target / 'keep.txt').read_text(), 'private')

    def test_catalog_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp)
            for name in update_skill.FILES:
                (source / name).write_bytes((ROOT / name).read_bytes())
            catalog = json.loads((source / 'recipes.json').read_text())
            catalog['recipes'].append(catalog['recipes'][0])
            (source / 'recipes.json').write_text(json.dumps(catalog))
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                update_skill.validate(source)


if __name__ == '__main__':
    unittest.main()
