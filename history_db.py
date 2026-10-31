#!/usr/bin/env python3
"""Private SQLite index of the durable JSON journal, never a chat-session memory.

The journal JSON is authoritative. SQLite stores the entire latest document and
queryable rows. A failed index update leaves JSON intact; the next sync repairs it.
"""
import argparse
from contextlib import closing
from datetime import date
import json
import os
import secrets
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1


def private_path(path):
    path = Path(path).expanduser().absolute()
    if not path.parent.is_dir() or stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise PermissionError('Private data directory must be mode 0700')
    if path.is_symlink():
        raise PermissionError('Refusing symlinked database or journal')
    if path.exists() and (not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077):
        raise PermissionError('Database and journal files must be mode 0600')
    return path


def connect(db, *, create=False):
    db = private_path(db)
    if not create and not db.is_file():
        raise FileNotFoundError('No SQLite history yet; sync the private journal first')
    fd = os.open(db, (os.O_CREAT if create else 0) | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    os.close(fd)
    db.chmod(0o600)
    connection = sqlite3.connect(db, timeout=15)
    try:
        connection.execute('PRAGMA journal_mode=DELETE')
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('PRAGMA busy_timeout=15000')
        connection.executescript('''
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS entries (
          ordinal INTEGER PRIMARY KEY, event_id TEXT, day TEXT NOT NULL,
          kind TEXT NOT NULL, name TEXT, kcal REAL, protein REAL, fat REAL,
          carbs REAL, minutes REAL, weight_kg REAL, voided INTEGER NOT NULL,
          source TEXT, payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS entries_day ON entries(day, ordinal);
        CREATE INDEX IF NOT EXISTS entries_kind_day ON entries(kind, day);
        CREATE TABLE IF NOT EXISTS corrections (
          ordinal INTEGER PRIMARY KEY, correction_id TEXT NOT NULL,
          event_id TEXT, at_utc TEXT, payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS complete_days (day TEXT PRIMARY KEY);
        ''')
        schema = connection.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        if schema and schema[0] != str(SCHEMA):
            raise ValueError('Unsupported SQLite history schema; refusing downgrade')
    except BaseException:
        connection.close()
        raise
    return connection


def sync(db, data):
    """Rebuild indexed rows in one transaction; retain a full recoverable document."""
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('entries'), list):
        raise ValueError('Unsupported journal for database sync')
    connection = connect(db, create=True)
    try:
        document = json.dumps(data, ensure_ascii=False, allow_nan=False, sort_keys=True)
        with connection:
            connection.execute('DELETE FROM entries')
            connection.execute('DELETE FROM corrections')
            connection.execute('DELETE FROM complete_days')
            for index, e in enumerate(data['entries']):
                connection.execute('''INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (index, e.get('event_id'), e['date'], e['type'], e.get('name'),
                     e.get('kcal'), e.get('protein'), e.get('fat'), e.get('carbs'),
                     e.get('minutes'), e.get('kg'), int(bool(e.get('voided'))), e.get('source'),
                     json.dumps(e, ensure_ascii=False, allow_nan=False)))
            for index, c in enumerate(data.get('corrections', [])):
                connection.execute('INSERT INTO corrections VALUES (?,?,?,?,?)',
                    (index, c['correction_id'], c.get('event_id'), c.get('at_utc'),
                     json.dumps(c, ensure_ascii=False, allow_nan=False)))
            for day in data.get('food_complete_days', []):
                connection.execute('INSERT INTO complete_days VALUES (?)', (day,))
            connection.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('schema', str(SCHEMA)))
            connection.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('journal_json', document))
        return len(data['entries'])
    finally:
        connection.close()


def sync_from_json(journal):
    journal = private_path(journal)
    if not journal.is_file():
        raise FileNotFoundError('No journal JSON; refusing to replace the database with an empty document')
    data = json.loads(journal.read_text(encoding='utf8'))
    return sync(journal.with_suffix('.sqlite3'), data)


def repair_from_json(journal):
    """Explicit, non-destructive corrupt-index quarantine; call under journal write lock."""
    journal = private_path(journal)
    if not journal.is_file():
        raise FileNotFoundError('Cannot repair without the authoritative private journal JSON')
    db = private_path(journal.with_suffix('.sqlite3'))
    quarantined = None
    if db.exists():
        try:
            with closing(connect(db)) as connection:
                status = connection.execute('PRAGMA quick_check').fetchone()[0]
                if status != 'ok':
                    raise sqlite3.DatabaseError('database disk image is malformed')
            return {'status': 'healthy', 'indexed_entries': sync_from_json(journal), 'quarantined': None}
        except sqlite3.DatabaseError as exc:
            if not any(token in str(exc).lower() for token in ('malformed', 'not a database', 'file is encrypted')):
                raise  # locked, disk-full or an unsupported schema is not a corrupt index
            suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(4)
            quarantined = db.with_name(db.name + '.corrupt-' + suffix)
            os.replace(db, quarantined)  # preserve forensic/recovery copy; never unlink it
            fd = os.open(db.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    count = sync_from_json(journal)
    return {'status': 'rebuilt', 'indexed_entries': count, 'quarantined': str(quarantined) if quarantined else None}


def read_entries(db, *, start=None, end=None, kind=None, include_voided=False, limit=50, offset=0):
    if limit < 1 or limit > 500 or offset < 0:
        raise ValueError('Use limit 1..500 and nonnegative offset')
    with closing(connect(db)) as connection:
        filters, values = ([] if include_voided else ['voided=0']), []
        if start:
            filters.append('day>=?')
            values.append(start)
        if end:
            filters.append('day<=?')
            values.append(end)
        if kind:
            filters.append('kind=?')
            values.append(kind)
        where = (' WHERE ' + ' AND '.join(filters)) if filters else ''
        total = connection.execute('SELECT COUNT(*) FROM entries' + where, values).fetchone()[0]
        rows = connection.execute('SELECT payload_json FROM entries' + where +
                                  ' ORDER BY day DESC, ordinal DESC LIMIT ? OFFSET ?', values + [limit, offset]).fetchall()
        return {'total': total, 'offset': offset, 'has_more': offset + len(rows) < total,
                'entries': [json.loads(row[0]) for row in rows]}


def read_corrections(db, *, limit=50, offset=0):
    if limit < 1 or limit > 500 or offset < 0:
        raise ValueError('Use limit 1..500 and nonnegative offset')
    with closing(connect(db)) as connection:
        total = connection.execute('SELECT COUNT(*) FROM corrections').fetchone()[0]
        rows = connection.execute('SELECT payload_json FROM corrections ORDER BY ordinal DESC LIMIT ? OFFSET ?',
                                  (limit, offset)).fetchall()
        return {'total': total, 'offset': offset, 'has_more': offset + len(rows) < total,
                'corrections': [json.loads(row[0]) for row in rows]}


def progress(db, *, limit=12, offset=0):
    if limit < 1 or limit > 120 or offset < 0:
        raise ValueError('Use limit 1..120 months and nonnegative offset')
    with closing(connect(db)) as connection:
        complete = connection.execute('''
          SELECT e.day, SUM(e.kcal) FROM entries e JOIN complete_days c ON e.day=c.day
          WHERE e.kind='meal' AND e.voided=0 GROUP BY e.day
          HAVING COUNT(*)=COUNT(e.kcal)
        ''').fetchall()
        complete_by_month = {}
        for day, kcal in complete:
            complete_by_month.setdefault(day[:7], []).append(kcal)
        weights_by_month = {}
        for day, weight in connection.execute('''
          SELECT day, weight_kg FROM entries WHERE kind='weight' AND voided=0
          ORDER BY day, ordinal
        '''):
            weights_by_month.setdefault(day[:7], []).append(weight)
        rows = connection.execute('''
          SELECT substr(day,1,7) AS month,
                 SUM(kind='meal'), SUM(kind='meal' AND kcal IS NOT NULL),
                 SUM(CASE WHEN kind='meal' THEN kcal ELSE 0 END),
                 SUM(kind='workout'), SUM(CASE WHEN kind='workout' THEN minutes ELSE 0 END),
                 SUM(kind='weight')
          FROM entries WHERE voided=0 GROUP BY month ORDER BY month DESC LIMIT ? OFFSET ?
        ''', (limit, offset)).fetchall()
        all_months = connection.execute("SELECT COUNT(DISTINCT substr(day,1,7)) FROM entries WHERE voided=0").fetchone()[0]
        return {'months_total': all_months, 'offset': offset, 'has_more': offset + len(rows) < all_months,
                'months': [{'month': month, 'logged_meals': meals, 'meals_with_known_kcal': known,
                            'known_kcal_subtotal': kcal if known else None,
                            'logged_workouts': workouts, 'logged_workout_minutes': minutes if workouts else None,
                            'weight_records': weights,
                            'first_recorded_weight_kg': weights_by_month.get(month, [None])[0],
                            'last_recorded_weight_kg': weights_by_month.get(month, [None])[-1],
                            'complete_food_days_with_known_kcal': len(complete_by_month.get(month, [])),
                            'avg_recorded_kcal_on_complete_days':
                                round(sum(complete_by_month[month]) / len(complete_by_month[month]), 1)
                                if complete_by_month.get(month) else None,
                            'note': 'These are recorded partial totals, not all consumption or a medical assessment.'}
                           for month, meals, known, kcal, workouts, minutes, weights in rows]}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Search all private journal history; no network')
    parser.add_argument('--data-dir', default=os.environ.get('COACH_DATA_DIR', '~/.local/share/fitness-coach-hermes'))
    sub = parser.add_subparsers(dest='command', required=True)
    history = sub.add_parser('history')
    history.add_argument('--from-date')
    history.add_argument('--to-date')
    history.add_argument('--type', choices=('meal', 'workout', 'weight'))
    history.add_argument('--include-voided', action='store_true')
    history.add_argument('--limit', type=int, default=50)
    history.add_argument('--offset', type=int, default=0)
    stats = sub.add_parser('progress')
    stats.add_argument('--limit', type=int, default=12)
    stats.add_argument('--offset', type=int, default=0)
    corrections = sub.add_parser('corrections')
    corrections.add_argument('--limit', type=int, default=50)
    corrections.add_argument('--offset', type=int, default=0)
    sub.add_parser('sync')
    repair = sub.add_parser('repair')
    repair.add_argument('--confirmed-by-user', action='store_true', required=True)
    args = parser.parse_args(argv)
    if args.command == 'history':
        for raw in (args.from_date, args.to_date):
            if raw is not None:
                try:
                    if date.fromisoformat(raw).isoformat() != raw:
                        raise ValueError
                except ValueError:
                    parser.error('Use ISO YYYY-MM-DD dates')
        if args.from_date and args.to_date and args.from_date > args.to_date:
            parser.error('Start date must not exceed end date')
    journal = Path(args.data_dir).expanduser().absolute() / 'journal.json'
    from coach import write_lock
    with write_lock(journal):
        if args.command == 'repair':
            print(json.dumps(repair_from_json(journal), ensure_ascii=False))
            return
        count = sync_from_json(journal)
        if args.command == 'sync':
            print(json.dumps({'indexed_entries': count, 'database': str(journal.with_suffix('.sqlite3'))}, ensure_ascii=False))
            return
        if args.command == 'history':
            result = read_entries(journal.with_suffix('.sqlite3'), start=args.from_date,
                                  end=args.to_date, kind=args.type, include_voided=args.include_voided,
                                  limit=args.limit, offset=args.offset)
        elif args.command == 'progress':
            result = progress(journal.with_suffix('.sqlite3'), limit=args.limit, offset=args.offset)
        else:
            result = read_corrections(journal.with_suffix('.sqlite3'), limit=args.limit, offset=args.offset)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
