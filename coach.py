#!/usr/bin/env python3
"""Private, dependency-free coach log and Telegram-ready progress reports."""
import argparse
import contextlib
import json
import math
import os
import stat
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile


def store_path(args):
    return Path(args.data_dir).expanduser().resolve() / 'journal.json'


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError('Data directory must be private (chmod 700)')


@contextlib.contextmanager
def write_lock(path):
    """Exclusive lock around the entire read/modify/write cycle."""
    private_directory(path.parent)
    lock = path.parent / '.journal.lock'
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise RuntimeError('Journal is locked by another writer; check before retrying') from None
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink()


def load(path):
    if not path.exists():
        return {'version': 1, 'targets': {}, 'entries': [], 'food_complete_days': []}
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('version') != 1 or not isinstance(value.get('entries'), list):
        raise ValueError('Unsupported journal format')
    value.setdefault('food_complete_days', [])
    return value


def save(path, value):
    private_directory(path.parent)
    with NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        os.chmod(tmp, 0o600)
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    if path.name == 'journal.json':
        # JSON remains the recovery source; SQLite is a private queryable mirror.
        # If indexing fails, the JSON write already committed and a later sync repairs it.
        from history_db import sync
        sync(path.with_suffix('.sqlite3'), value)


def save_png(path, image):
    """Write a private card atomically; never leave health data world-readable."""
    private_directory(path.parent)
    with NamedTemporaryFile('wb', suffix='.png', dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        os.chmod(tmp, 0o600)
    try:
        image.save(tmp, 'PNG')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def number(value, *, positive=False):
    n = float(value)
    if not math.isfinite(n) or n < 0 or (positive and n == 0):
        raise argparse.ArgumentTypeError('Use a finite positive value' if positive else 'Use a finite nonnegative value')
    return n


def add_entry(data, entry, event_id=None):
    if event_id is None:
        event_id = f'local:{uuid.uuid4().hex}'
    if not event_id or len(event_id) > 128 or any(ord(char) < 33 or ord(char) > 126 for char in event_id):
        raise ValueError('Event ID must be nonempty printable ASCII without spaces (max 128)')
    if any(e.get('event_id') == event_id for e in data['entries']):
        raise RuntimeError('Event ID already recorded; no duplicate was added')
    entry['event_id'] = event_id
    data['entries'].append(entry)

ENTRY_LIMITS = {'kcal': 10000, 'protein': 1500, 'fat': 1500, 'carbs': 1500,
                'grams': 10000, 'minutes': 1440, 'sets': 1000, 'reps': 10000,
                'load_kg': 2000, 'kg': 500}
ENTRY_FIELDS = {'meal': {'name', 'grams', 'kcal', 'protein', 'fat', 'carbs'},
                'workout': {'name', 'minutes', 'sets', 'reps', 'load_kg'},
                'weight': {'kg'}}

def validate_entry_limits(entry):
    for field, limit in ENTRY_LIMITS.items():
        value = entry.get(field)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0 or value > limit):
            raise ValueError(f'Check {field}; conservative input limit is {limit} (not a health target)')
    for field in ('minutes', 'grams', 'kg'):
        if field in entry and entry[field] is not None and entry[field] == 0:
            raise ValueError(f'{field} must be positive')
    strength = (entry.get('sets'), entry.get('reps'), entry.get('load_kg'))
    if entry['type'] == 'workout' and any(v is not None for v in strength):
        if any(v is None for v in strength) or any(type(v) is not int or v < 1 for v in strength[:2]):
            raise ValueError('Strength fields require positive sets/reps and nonnegative load together')

def revise_entry(data, event_id, correction_id, *, field=None, value=None, reason=None):
    """One locked revision or void; preserve before-image for private audit."""
    if (not event_id or not correction_id or len(correction_id) > 128
            or any(ord(char) < 33 or ord(char) > 126 for char in correction_id)):
        raise ValueError('Existing event ID and unique correction ID are required')
    history = data.setdefault('corrections', [])
    if any(item['correction_id'] == correction_id for item in history):
        raise RuntimeError('Correction ID already applied; nothing changed')
    matches = [entry for entry in data['entries'] if entry.get('event_id') == event_id]
    if len(matches) != 1 or matches[0].get('voided'):
        raise ValueError('Active entry not found by exact event ID')
    entry = matches[0]
    if field is None:
        if not reason or not reason.strip():
            raise ValueError('Voiding requires a short owner-confirmed reason')
        after = {**entry, 'voided': True}
    else:
        if field not in ENTRY_FIELDS[entry['type']]:
            raise ValueError('Field cannot be corrected for this entry type')
        if entry['type'] == 'meal' and entry.get('source') == 'usda':
            raise ValueError('USDA entries must be voided and re-logged with a verified food and portion')
        if field == 'name':
            if not value or not value.strip() or len(value) > 200:
                raise ValueError('Name must be nonempty (max 200 characters)')
            parsed = value.strip()
        elif field in ('sets', 'reps'):
            parsed = int(value)
            if str(parsed) != value or parsed < 1:
                raise ValueError('Sets/reps must be positive integers')
        else:
            parsed = None if value == 'unknown' else number(value, positive=field in ('grams', 'minutes', 'kg'))
            if parsed is None and field in ('minutes', 'kg'):
                raise ValueError('Required value cannot be unknown')
        after = {**entry, field: parsed}
        validate_entry_limits(after)
    before = dict(entry)
    entry.clear()
    entry.update(after)
    history.append({'correction_id': correction_id, 'event_id': event_id,
                    'at_utc': datetime.now(timezone.utc).isoformat(),
                    'reason': reason.strip() if reason else None,
                    'before': before, 'after': dict(entry)})
    if entry['type'] == 'meal':
        data['food_complete_days'] = [d for d in data['food_complete_days'] if d != entry['date']]


def day(value):
    return date.fromisoformat(value).isoformat()


def aggregate(data, end, days=7):
    start = end - timedelta(days=days - 1)
    rows = {str(start + timedelta(days=i)): {'kcal': 0, 'protein': 0, 'fat': 0, 'carbs': 0, 'known': {'kcal': 0, 'protein': 0, 'fat': 0, 'carbs': 0}, 'micros': {}, 'micro_known': {}, 'meals': 0, 'workouts': 0, 'workout_minutes': 0, 'sets': 0, 'volume_kg': 0, 'weight': None} for i in range(days)}
    for e in data['entries']:
        if e.get('voided'):
            continue
        d = e['date']
        if d not in rows:
            continue
        r = rows[d]
        if e['type'] == 'meal':
            r['meals'] += 1
            for key in ('kcal', 'protein', 'fat', 'carbs'):
                if e.get(key) is not None:
                    r[key] += e[key]
                    r['known'][key] += 1
            for key, value in e.get('micros', {}).items():
                r['micros'][key] = r['micros'].get(key, 0) + value
                r['micro_known'][key] = r['micro_known'].get(key, 0) + 1
        elif e['type'] == 'workout':
            r['workouts'] += 1
            r['workout_minutes'] += e['minutes']
            r['sets'] += e.get('sets') or 0
            r['volume_kg'] += (e.get('sets') or 0) * (e.get('reps') or 0) * (e.get('load_kg') or 0)
        elif e['type'] == 'weight':
            r['weight'] = e['kg']
    return rows


def telegram_text(data, end):
    rows = aggregate(data, end)
    today = rows[end.isoformat()]
    target = data['targets'].get('kcal')
    known = today['known']['kcal']
    header = f"📊 {end.isoformat()} · " + (f"записано {today['kcal']:.0f} ккал" if known else ('еда записана, калорийность неизвестна' if today['meals'] else 'нет записей о еде'))
    if known and known < today['meals']:
        header += f" (по {known} из {today['meals']} записей)"
    if target and known == today['meals'] and end.isoformat() in data.get('food_complete_days', []):
        header += f" / {target:.0f} ккал (план, не медицинское назначение)"
    macro = lambda k: f"{today[k]:.0f}" if today['known'][k] == today['meals'] and today['meals'] else '—'
    lines = [header, f"Б {macro('protein')} г · Ж {macro('fat')} г · У {macro('carbs')} г", '', 'Последние 7 дней:']
    scale = max([r['kcal'] for r in rows.values()] + ([target] if target else [1]))
    for d, r in rows.items():
        blocks = min(12, round(12 * r['kcal'] / scale)) if r['kcal'] else 0
        mark = '█' * blocks + '░' * (12 - blocks)
        label = (f"{r['kcal']:.0f} ккал" + (f" (по {r['known']['kcal']}/{r['meals']})" if r['known']['kcal'] < r['meals'] else '')) if r['known']['kcal'] else ('калорийность неизвестна' if r['meals'] else 'нет записей')
        lines.append(f"{d[5:]}  {mark}  {label}" + (' · 🏋️' if r['workouts'] else ''))
    weights = [(d, r['weight']) for d, r in rows.items() if r['weight'] is not None]
    if weights:
        lines.append(f"Вес: {weights[-1][1]:.1f} кг ({weights[-1][0]})")
    training_days = sum(bool(r['workouts']) for r in rows.values())
    minutes = sum(r['workout_minutes'] for r in rows.values())
    lines.append(f"Тренировки: {training_days} дн. с записями, {minutes:.0f} мин за 7 дней")
    weighted = sum(r['volume_kg'] for r in rows.values())
    if weighted:
        lines.append(f"Объём записанных силовых подходов: {weighted:.0f} кг·повт. (не показатель качества тренировки)")
    if today['micros']:
        items = ', '.join(f"{key}: {value:.1f}" + (' (частично)' if today['micro_known'][key] < today['meals'] else '') for key, value in sorted(today['micros'].items()))
        lines.append('Микронутриенты из записанных продуктов: ' + items)
        lines.append('Без сравнения с нормой: она зависит от человека, а неполный дневник и база не показывают весь рацион.')
    lines.append('Учтены только записанные приёмы пищи; фото и порции без веса — оценка.')
    return '\n'.join(lines)


def trends(data, end, days=28):
    """Machine-readable observed history; absent readings stay null."""
    rows = aggregate(data, end, days)
    measured = [r['weight'] for r in rows.values() if r['weight'] is not None]
    intake_days = sum(bool(r['meals']) for r in rows.values())
    complete = set(data.get('food_complete_days', []))
    full_rows = [r for d, r in rows.items() if d in complete and r['meals'] and r['known']['kcal'] == r['meals']]
    return {'start': next(iter(rows)), 'end': end.isoformat(), 'days': days,
            'logged_food_days': intake_days,
            'complete_food_days_with_known_kcal': len(full_rows),
            'avg_logged_kcal': round(sum(r['kcal'] for r in full_rows) / len(full_rows), 1) if full_rows else None,
            'weight_delta_kg': round(measured[-1] - measured[0], 2) if len(measured) > 1 else None,
            'training_days': sum(bool(r['workouts']) for r in rows.values()),
            'training_minutes': sum(r['workout_minutes'] for r in rows.values()),
            'series': [{'date': d, 'logged_kcal': r['kcal'] if r['known']['kcal'] else None,
                        'kcal_known_meals': r['known']['kcal'], 'food_complete': d in complete and bool(r['meals']),
                        'meals': r['meals'], 'macros_g': {k: r[k] if r['known'][k] == r['meals'] and r['meals'] else None for k in ('protein', 'fat', 'carbs')},
                        'micros': {k: {'amount': value, 'known_meals': r['micro_known'][k], 'total_meals': r['meals']} for k, value in r['micros'].items()},
                        'training_minutes': r['workout_minutes'] if r['workouts'] else None, 'weight_kg': r['weight']} for d, r in rows.items()]}


def snapshot(data, end, scope, event_id=None):
    """Canonical facts for distinct Telegram cards; no inferred health grades."""
    def food_items(entries):
        """Observed meal labels only; names are not parsed into ingredients."""
        return [{'date': e['date'], 'name': e['name'], 'grams': e.get('grams'),
                 'source': e.get('source'), 'logged_kcal': e.get('kcal')}
                for e in entries if e['type'] == 'meal']

    def workout_items(entries):
        return [{'date': e['date'], 'name': e['name'], 'minutes': e['minutes']}
                for e in entries if e['type'] == 'workout']

    if scope == 'week':
        start = end - timedelta(days=end.weekday())
        finish = start + timedelta(days=6)
        rows = aggregate(data, finish, 7)
        complete = set(data.get('food_complete_days', []))
        complete_rows = [r for d, r in rows.items() if d in complete and r['meals'] and r['known']['kcal'] == r['meals']]
        week_entries = [e for e in data['entries'] if not e.get('voided') and start.isoformat() <= e['date'] <= finish.isoformat()]
        estimated = sum(e['type'] == 'meal' and e.get('source') == 'photo-estimate' for e in week_entries)
        mean = round(sum(r['kcal'] for r in complete_rows) / len(complete_rows), 1) if complete_rows else None
        bounds = data.get('targets', {}).get('weekly_avg_kcal_range')
        status = None
        if bounds and len(complete_rows) == 7 and not estimated:
            status = 'within_user_range' if bounds[0] <= mean <= bounds[1] else 'outside_user_range'
        return {'kind': 'week', 'start': start.isoformat(), 'end': finish.isoformat(),
                'recorded_food_days': sum(bool(r['meals']) for r in rows.values()),
                'confirmed_complete_food_days': sum(d in complete and bool(r['meals']) for d, r in rows.items()),
                'complete_food_days_with_known_kcal': len(complete_rows), 'days_in_period': 7,
                'average_logged_kcal_on_complete_days': mean,
                'estimated_food_entries': estimated,
                'user_weekly_average_kcal_range': bounds,
                'weekly_range_status': status,
                'training_minutes_recorded': sum(r['workout_minutes'] for r in rows.values()),
                'training_days_recorded': sum(bool(r['workouts']) for r in rows.values()),
                'recorded_food_items': food_items(week_entries),
                'recorded_workout_items': workout_items(week_entries),
                'visual_preferences': data.get('visual_preferences'),
                'weights_kg': [{'date': d, 'kg': r['weight']} for d, r in rows.items() if r['weight'] is not None],
                'days': [{'date': d, 'logged_kcal': r['kcal'] if r['known']['kcal'] else None,
                          'kcal_known_meals': r['known']['kcal'], 'food_entries': r['meals'],
                          'food_complete': d in complete and bool(r['meals']), 'workout_minutes': r['workout_minutes'] if r['workouts'] else None} for d, r in rows.items()],
                'note': 'Activity intensity and full-week coverage unverified; no clinical or diet-quality grade.'}
    d = end.isoformat()
    day_entries = [e for e in data['entries'] if not e.get('voided') and e['date'] == d]
    row = aggregate(data, end, 1)[d]
    base = {'kind': scope, 'date': d, 'logged_kcal': row['kcal'] if row['known']['kcal'] else None,
            'kcal_known_meals': row['known']['kcal'],
            'macros_g': {k: row[k] if row['meals'] and row['known'][k] == row['meals'] else None for k in ('protein', 'fat', 'carbs')},
            'micros_recorded': {k: {'amount': v, 'known_meals': row['micro_known'][k], 'total_meals': row['meals']} for k, v in row['micros'].items()},
            'food_entries': row['meals'], 'food_complete': d in data.get('food_complete_days', []),
            'recorded_food_items': food_items(day_entries),
            'recorded_workout_items': workout_items(day_entries),
            'visual_preferences': data.get('visual_preferences'),
            'estimated_food_entries': sum(e['type'] == 'meal' and e.get('source') == 'photo-estimate' for e in day_entries),
            'training_minutes_recorded': row['workout_minutes'] if row['workouts'] else None,
            'weight_kg': row['weight'], 'note': 'Only recorded values; missing is unknown, not zero.'}
    if scope == 'day':
        week_rows = aggregate(data, end, end.weekday() + 1)
        base['week_to_date'] = {'start': next(iter(week_rows)), 'end': d,
                                'logged_food_days': sum(bool(r['meals']) for r in week_rows.values()),
                                'confirmed_complete_food_days': sum(day in data.get('food_complete_days', []) for day in week_rows),
                                'training_minutes_recorded': sum(r['workout_minutes'] for r in week_rows.values())}
    if scope == 'entry':
        latest = next((e for e in day_entries if e.get('event_id') == event_id), None) if event_id else (day_entries[-1] if day_entries else None)
        if event_id and latest is None:
            raise ValueError('Event ID not found for this date; no receipt created')
        base['latest_entry'] = {k: latest.get(k) for k in ('type', 'name', 'grams', 'kcal', 'minutes', 'kg', 'source') if k in latest} if latest else None
    return base


def render_png(data, end, path, view='nutrition', nutrient='iron_mg'):
    """Render exact logged values, not a generative approximation."""
    from PIL import Image, ImageDraw, ImageFont
    rows = aggregate(data, end)
    im = Image.new('RGB', (1080, 1080), '#101827')
    draw = ImageDraw.Draw(im)
    font_path = os.environ.get('COACH_FONT_PATH') or next((p for p in (
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/Library/Fonts/Arial Unicode.ttf',
        'C:/Windows/Fonts/arial.ttf',
        'DejaVuSans.ttf',
    ) if Path(p).exists() or p == 'DejaVuSans.ttf'), 'DejaVuSans.ttf')
    try:
        font = lambda size: ImageFont.truetype(font_path, size)
        font(24)
    except OSError:
        raise RuntimeError('No Cyrillic font found; set COACH_FONT_PATH to a local TTF') from None
    draw.text((75, 60), 'Питание и тренировки', font=font(48), fill='white')
    draw.text((75, 130), f'Неделя до {end.isoformat()}', font=font(29), fill='#aab8c8')
    target = data['targets'].get('kcal')
    today = rows[end.isoformat()]
    if view == 'micro-trend':
        from food_lookup import MICROS
        names = {'calcium_mg': 'Кальций', 'iron_mg': 'Железо', 'magnesium_mg': 'Магний', 'potassium_mg': 'Калий', 'sodium_mg': 'Натрий', 'zinc_mg': 'Цинк', 'vitamin_a_rae_ug': 'Витамин A (RAE)', 'vitamin_d_ug': 'Витамин D', 'vitamin_c_mg': 'Витамин C', 'vitamin_b12_ug': 'Витамин B12', 'folate_dfe_ug': 'Фолат (DFE)', 'fiber_g': 'Клетчатка'}
        labels = {key: (names[key], {'µg': 'мкг', 'mg': 'мг', 'g': 'г'}[unit]) for key, unit in MICROS.values()}
        label, unit = labels[nutrient]
        draw.text((75, 220), f'Динамика: {label}', font=font(34), fill='#42d49b')
        scale = max([r['micros'].get(nutrient, 0) for r in rows.values()] + [1])
        for i, (d, r) in enumerate(rows.items()):
            y = 310 + i * 77
            known = r['micro_known'].get(nutrient, 0)
            draw.text((75, y), d[5:], font=font(25), fill='#dbe7f0')
            draw.rounded_rectangle((205, y + 4, 790, y + 33), radius=12, fill='#27384b')
            width = round(585 * r['micros'].get(nutrient, 0) / scale)
            if width:
                draw.rounded_rectangle((205, y + 4, 205 + width, y + 33), radius=min(12, width // 2), fill='#42d49b')
            draw.text((810, y), f"{r['micros'][nutrient]:.1f} {unit}" if known else 'нет данных', font=font(20), fill='white' if known else '#aab8c8')
        draw.text((75, 925), 'Шкала по максимуму записей, не по норме', font=font(23), fill='#aab8c8')
        draw.text((75, 1000), 'Неполный дневник ≠ дефицит · без назначения добавок', font=font(20), fill='#8092a6')
        save_png(path, im)
        return
    if view == 'activity':
        draw.text((75, 220), 'Активность по дням', font=font(35), fill='#42d49b')
        scale = max([r['workout_minutes'] for r in rows.values()] + [1])
        for i, (d, r) in enumerate(rows.items()):
            y = 300 + i * 78
            draw.text((75, y), d[5:], font=font(27), fill='#dbe7f0')
            draw.rounded_rectangle((205, y + 4, 790, y + 35), radius=12, fill='#27384b')
            width = round(585 * r['workout_minutes'] / scale)
            if width:
                draw.rounded_rectangle((205, y + 4, 205 + width, y + 35), radius=min(12, width // 2), fill='#ffb454')
            draw.text((810, y), f"{r['workout_minutes']:.0f} мин" if r['workouts'] else 'нет записи', font=font(20), fill='white' if r['workouts'] else '#aab8c8')
        weights = [(d, r['weight']) for d, r in rows.items() if r['weight'] is not None]
        msg = ('Вес (записи): ' + ' → '.join(f'{v:.1f}' for _, v in weights) + ' кг') if weights else 'Вес: нет записей за неделю'
        draw.text((75, 880), msg[:55], font=font(25), fill='#dbe7f0')
        draw.text((75, 935), 'Нет записей ≠ отсутствовала активность', font=font(23), fill='#aab8c8')
        draw.text((75, 1000), 'Только записанные данные · без медицинских выводов', font=font(20), fill='#8092a6')
        save_png(path, im)
        return
    if view == 'micros':
        draw.text((75, 220), 'Нутриенты из записанной еды', font=font(34), fill='#42d49b')
        labels = [('fiber_g', 'Клетчатка', 'г'), ('calcium_mg', 'Кальций', 'мг'), ('iron_mg', 'Железо', 'мг'), ('magnesium_mg', 'Магний', 'мг'), ('potassium_mg', 'Калий', 'мг'), ('vitamin_d_ug', 'Витамин D', 'мкг'), ('vitamin_b12_ug', 'Витамин B12', 'мкг')]
        for i, (key, title, unit) in enumerate(labels):
            y = 310 + i * 81
            known = today['micro_known'].get(key, 0)
            status = f"{today['micros'][key]:.1f} {unit}" if known else 'нет данных'
            draw.text((75, y), title, font=font(27), fill='white')
            draw.text((600, y), status, font=font(26), fill='#42d49b' if known else '#aab8c8')
            if known and known < today['meals']:
                draw.text((75, y + 36), f"данные по {known} из {today['meals']} записанных блюд", font=font(18), fill='#aab8c8')
        draw.text((75, 920), 'Нет данных ≠ дефицит; запись дня может быть неполной', font=font(20), fill='#aab8c8')
        draw.text((75, 1000), 'Без персональной нормы и назначения добавок', font=font(20), fill='#8092a6')
        save_png(path, im)
        return
    today_kcal = (f"Записано: {today['kcal']:.0f} ккал" + (f" ({today['known']['kcal']}/{today['meals']})" if today['known']['kcal'] < today['meals'] else '')) if today['known']['kcal'] else ('Калорийность неизвестна' if today['meals'] else 'Сегодня нет записей о еде')
    draw.text((75, 205), today_kcal + (f" / план {target:.0f}" if target and today['meals'] == today['known']['kcal'] and end.isoformat() in data.get('food_complete_days', []) else ''), font=font(32), fill='#42d49b')
    macro = lambda k: f"{today[k]:.0f}" if today['known'][k] == today['meals'] and today['meals'] else '—'
    draw.text((75, 265), f"Б {macro('protein')} г    Ж {macro('fat')} г    У {macro('carbs')} г" if today['meals'] else 'Пустой день не означает голодание', font=font(26), fill='white')
    draw.text((75, 345), 'Калории по дням', font=font(31), fill='white')
    scale = max([r['kcal'] for r in rows.values()] + ([target] if target else [1]))
    for i, (d, r) in enumerate(rows.items()):
        y = 410 + i * 74
        draw.text((75, y), d[5:], font=font(25), fill='#dbe7f0')
        draw.rounded_rectangle((205, y + 4, 790, y + 32), radius=12, fill='#27384b')
        width = round(585 * r['kcal'] / scale)
        if width:
            draw.rounded_rectangle((205, y + 4, 205 + width, y + 32), radius=min(12, width // 2), fill='#42d49b')
        draw.text((810, y), (f"{r['kcal']:.0f}" + ('*' if r['known']['kcal'] < r['meals'] else '')) if r['known']['kcal'] else ('нет kcal' if r['meals'] else 'нет записи'), font=font(19 if not r['known']['kcal'] else 24), fill='white' if r['known']['kcal'] else '#aab8c8')
        if r['workouts']:
            draw.text((970, y), '●', font=font(22), fill='#ffb454')
    if today['micros']:
        draw.text((75, 920), f"Микро (записано): {len(today['micros'])} показателей", font=font(22), fill='#aab8c8')
    if target:
        draw.text((75, 960), f'План: {target:.0f} ккал/день', font=font(22), fill='#aab8c8')
    draw.text((75, 1000), '* Частичные kcal · нет данных ≠ ноль · не диагноз', font=font(20), fill='#aab8c8')
    save_png(path, im)


def main(argv=None):
    p = argparse.ArgumentParser(description='Personal fitness journal; no network, no automatic messages')
    p.add_argument('--data-dir', default=os.environ.get('COACH_DATA_DIR', '~/.local/share/fitness-coach-hermes'))
    sub = p.add_subparsers(dest='command', required=True)
    t = sub.add_parser('target', help='Set user-approved daily kcal goal')
    t.add_argument('--kcal', required=True, type=lambda s: number(s, positive=True))
    t.add_argument('--weekly-avg-min', type=lambda s: number(s, positive=True))
    t.add_argument('--weekly-avg-max', type=lambda s: number(s, positive=True))
    t.add_argument('--confirmed-by-user', action='store_true', required=True, help='Only after explicit owner confirmation; not a medical recommendation')
    vp = sub.add_parser('visual-profile', help='Store owner-chosen visual style, not inferred gender or body type')
    vp.add_argument('--style', choices=('adaptive', 'bold-athletic', 'high-energy', 'editorial', 'minimal'), required=True)
    vp.add_argument('--food-scene', choices=('literal', 'playful', 'abstract'), required=True)
    vp.add_argument('--confirmed-by-user', action='store_true', required=True)
    m = sub.add_parser('meal', help='Log a confirmed meal estimate')
    m.add_argument('--date', type=day, default=date.today().isoformat())
    m.add_argument('--name', required=True)
    m.add_argument('--kcal', type=number, help='Optional; omit if unknown, explicit 0 only if verified')
    for macro in ('protein', 'fat', 'carbs'):
        m.add_argument('--' + macro, type=number)
    m.add_argument('--source', choices=('label', 'usda', 'user', 'photo-estimate'), required=True)
    m.add_argument('--grams', type=lambda s: number(s, positive=True), help='Confirmed food mass; never infer from calories')
    m.add_argument('--event-id', help='Stable external message ID; rejects retries')
    f = sub.add_parser('food', help='Log a weighed USDA item by FDC ID')
    f.add_argument('--date', type=day, default=date.today().isoformat())
    f.add_argument('--fdc-id', type=int, required=True)
    f.add_argument('--grams', type=lambda s: number(s, positive=True), required=True)
    f.add_argument('--event-id', help='Stable external message ID; rejects retries')
    w = sub.add_parser('workout')
    w.add_argument('--date', type=day, default=date.today().isoformat())
    w.add_argument('--name', required=True)
    w.add_argument('--minutes', type=lambda s: number(s, positive=True), required=True)
    w.add_argument('--sets', type=int)
    w.add_argument('--reps', type=int)
    w.add_argument('--load-kg', type=number)
    w.add_argument('--event-id', help='Stable external message ID; rejects retries')
    wt = sub.add_parser('weight')
    wt.add_argument('--date', type=day, default=date.today().isoformat())
    wt.add_argument('--kg', type=lambda s: number(s, positive=True), required=True)
    wt.add_argument('--event-id', help='Stable external message ID; rejects retries')
    close = sub.add_parser('close-day', help='Confirm all food for a date was logged')
    close.add_argument('--date', type=day, default=date.today().isoformat())
    close.add_argument('--confirmed-by-user', action='store_true', required=True)
    correction = sub.add_parser('correct-entry', help='Owner-approved exact-field correction, with private audit history')
    correction.add_argument('--event-id', required=True)
    correction.add_argument('--correction-id', required=True, help='Stable unique ID for retry safety')
    correction.add_argument('--field', required=True, choices=sorted(set().union(*ENTRY_FIELDS.values())))
    correction.add_argument('--value', required=True, help='New value; use unknown for optional numeric fields')
    correction.add_argument('--reason', help='Owner-confirmed reason; stays private')
    correction.add_argument('--confirmed-by-user', action='store_true', required=True)
    void = sub.add_parser('void-entry', help='Mark mistaken entry void, retaining a private audit record')
    void.add_argument('--event-id', required=True)
    void.add_argument('--correction-id', required=True)
    void.add_argument('--reason', required=True)
    void.add_argument('--confirmed-by-user', action='store_true', required=True)
    migrate = sub.add_parser('migrate-legacy-ids', help='Owner-approved immutable IDs for older records without IDs')
    migrate.add_argument('--confirmed-by-user', action='store_true', required=True)
    for cmd in ('report', 'card', 'trends', 'snapshot'):
        r = sub.add_parser(cmd)
        r.add_argument('--date', type=day, default=date.today().isoformat())
        if cmd == 'trends':
            r.add_argument('--days', type=int, choices=(7, 14, 28, 90), default=28)
        if cmd == 'card':
            r.add_argument('--output', type=Path, required=True)
            r.add_argument('--view', choices=('nutrition', 'activity', 'micros', 'micro-trend'), default='nutrition')
            from food_lookup import MICROS
            r.add_argument('--nutrient', choices=[key for key, _ in MICROS.values()], default='iron_mg')
        if cmd == 'snapshot':
            r.add_argument('--scope', choices=('entry', 'day', 'week'), required=True)
            r.add_argument('--event-id', help='Select the exact new entry, not simply the last record on that date')
    args = p.parse_args(argv)
    path = store_path(args)
    if args.command in ('target', 'visual-profile', 'meal', 'food', 'workout', 'weight', 'close-day', 'correct-entry', 'void-entry', 'migrate-legacy-ids'):
        with write_lock(path):
            return execute(p, args, path)
    return execute(p, args, path)


def execute(p, args, path):
    data = load(path)
    if args.command == 'target':
        if not 1200 <= args.kcal <= 5000:
            p.error('Target outside conservative adult input range; consult a qualified professional. This range is not a prescription.')
        if (args.weekly_avg_min is None) != (args.weekly_avg_max is None):
            p.error('Set both weekly-average bounds or neither')
        if args.weekly_avg_min is not None and not (1200 <= args.weekly_avg_min <= args.weekly_avg_max <= 5000):
            p.error('Check owner-selected weekly-average range; these limits are not a prescription')
        data['targets']['kcal'] = args.kcal
        data['targets']['weekly_avg_kcal_range'] = [args.weekly_avg_min, args.weekly_avg_max] if args.weekly_avg_min is not None else None
    elif args.command == 'visual-profile':
        data['visual_preferences'] = {'style': args.style, 'food_scene': args.food_scene}
    elif args.command == 'meal':
        if not args.name.strip():
            p.error('Meal name cannot be blank')
        if args.grams is not None and args.grams > 10000:
            p.error('Check serving grams')
        entry = {'type': 'meal', 'date': args.date, 'name': args.name.strip(), 'grams': args.grams, 'kcal': args.kcal, 'protein': args.protein, 'fat': args.fat, 'carbs': args.carbs, 'source': args.source}
        validate_entry_limits(entry)
        add_entry(data, entry, args.event_id)
        data['food_complete_days'] = [d for d in data['food_complete_days'] if d != args.date]
    elif args.command == 'food':
        if args.fdc_id < 1 or args.grams > 10000:
            p.error('Check FDC ID and serving grams')
        from food_lookup import by_id
        item = by_id(args.fdc_id)
        values = item['per_100g']
        if values['kcal'] is None or not item['description']:
            p.error('USDA item has no usable kcal or description; nothing logged')
        factor = args.grams / 100
        entry = {'type': 'meal', 'date': args.date, 'name': item['description'], 'fdc_id': args.fdc_id, 'grams': args.grams, 'source': 'usda', 'kcal': values['kcal'] * factor, 'protein': values['protein_g'] * factor if values['protein_g'] is not None else None, 'fat': values['fat_g'] * factor if values['fat_g'] is not None else None, 'carbs': values['carbs_g'] * factor if values['carbs_g'] is not None else None, 'micros': {key: value * factor for key, value in values['micros'].items()}}
        validate_entry_limits(entry)
        add_entry(data, entry, args.event_id)
        data['food_complete_days'] = [d for d in data['food_complete_days'] if d != args.date]
    elif args.command == 'workout':
        if not args.name.strip():
            p.error('Workout name cannot be blank')
        strength = (args.sets, args.reps, args.load_kg)
        if any(x is not None for x in strength) and (any(x is None for x in strength) or args.sets < 1 or args.reps < 1):
            p.error('For strength work provide positive --sets, --reps and nonnegative --load-kg together')
        entry = {'type': 'workout', 'date': args.date, 'name': args.name.strip(), 'minutes': args.minutes, 'sets': args.sets, 'reps': args.reps, 'load_kg': args.load_kg}
        validate_entry_limits(entry)
        add_entry(data, entry, args.event_id)
    elif args.command == 'weight':
        if args.kg > 500:
            p.error('Check weight units (expected kg)')
        entry = {'type': 'weight', 'date': args.date, 'kg': args.kg}
        validate_entry_limits(entry)
        add_entry(data, entry, args.event_id)
    elif args.command in ('correct-entry', 'void-entry'):
        try:
            revise_entry(data, args.event_id, args.correction_id,
                         field=args.field if args.command == 'correct-entry' else None,
                         value=args.value if args.command == 'correct-entry' else None,
                         reason=args.reason)
        except (ValueError, argparse.ArgumentTypeError) as exc:
            p.error(str(exc))
    elif args.command == 'migrate-legacy-ids':
        assigned = []
        existing = {e.get('event_id') for e in data['entries'] if e.get('event_id')}
        for index, entry in enumerate(data['entries']):
            if not entry.get('event_id'):
                event_id = f'legacy:{uuid.uuid4().hex}'
                while event_id in existing:
                    event_id = f'legacy:{uuid.uuid4().hex}'
                entry['event_id'] = event_id
                existing.add(event_id)
                assigned.append({'index': index, 'date': entry['date'], 'type': entry['type'], 'event_id': event_id})
    elif args.command == 'close-day':
        if not any(e['type'] == 'meal' and not e.get('voided') and e['date'] == args.date for e in data['entries']):
            p.error('Cannot close a day without food records; missing is unknown')
        data['food_complete_days'] = sorted(set(data['food_complete_days']) | {args.date})
    elif args.command == 'report':
        print(telegram_text(data, date.fromisoformat(args.date)))
        return
    elif args.command == 'trends':
        print(json.dumps(trends(data, date.fromisoformat(args.date), args.days), ensure_ascii=False, indent=2))
        return
    elif args.command == 'snapshot':
        print(json.dumps(snapshot(data, date.fromisoformat(args.date), args.scope, args.event_id), ensure_ascii=False, indent=2, allow_nan=False))
        return
    elif args.command == 'card':
        render_png(data, date.fromisoformat(args.date), args.output, args.view, args.nutrient)
        print(args.output.resolve())
        return
    save(path, data)
    if args.command == 'migrate-legacy-ids':
        print(json.dumps({'assigned': assigned, 'note': 'Keep mapping private; verify the exact record before correction.'}, ensure_ascii=False))
        return
    if args.command in ('meal', 'food', 'workout', 'weight'):
        print(f"Event ID: {entry['event_id']}")
    print(f"Recorded {args.command} in {path}")


if __name__ == '__main__':
    main()
