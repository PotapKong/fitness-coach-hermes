#!/usr/bin/env python3
"""Private, dependency-free coach log and Telegram-ready progress reports."""
import argparse
import json
import math
import os
from datetime import date, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile


def store_path(args):
    return Path(args.data_dir).expanduser().resolve() / 'journal.json'


def load(path):
    if not path.exists():
        return {'version': 1, 'targets': {}, 'entries': []}
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('version') != 1 or not isinstance(value.get('entries'), list):
        raise ValueError('Unsupported journal format')
    return value


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        os.chmod(tmp, 0o600)
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save_png(path, image):
    """Write a private card atomically; never leave health data world-readable."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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


def day(value):
    return date.fromisoformat(value).isoformat()


def aggregate(data, end, days=7):
    start = end - timedelta(days=days - 1)
    rows = {str(start + timedelta(days=i)): {'kcal': 0, 'protein': 0, 'fat': 0, 'carbs': 0, 'known': {'kcal': 0, 'protein': 0, 'fat': 0, 'carbs': 0}, 'micros': {}, 'micro_known': {}, 'meals': 0, 'workouts': 0, 'workout_minutes': 0, 'sets': 0, 'volume_kg': 0, 'weight': None} for i in range(days)}
    for e in data['entries']:
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
    header = f"📊 {end.isoformat()} · " + (f"записано {today['kcal']:.0f} ккал" if today['meals'] else 'нет записей о еде')
    if target and today['meals']:
        header += f" / {target:.0f} ккал (план, не медицинское назначение)"
    macro = lambda k: f"{today[k]:.0f}" if today['known'][k] == today['meals'] and today['meals'] else '—'
    lines = [header, f"Б {macro('protein')} г · Ж {macro('fat')} г · У {macro('carbs')} г", '', 'Последние 7 дней:']
    scale = max([r['kcal'] for r in rows.values()] + ([target] if target else [1]))
    for d, r in rows.items():
        blocks = min(12, round(12 * r['kcal'] / scale)) if r['kcal'] else 0
        mark = '█' * blocks + '░' * (12 - blocks)
        lines.append(f"{d[5:]}  {mark}  " + (f"{r['kcal']:.0f} ккал" if r['meals'] else 'нет записей') + (' · 🏋️' if r['workouts'] else ''))
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
    return {'start': next(iter(rows)), 'end': end.isoformat(), 'days': days,
            'logged_food_days': intake_days,
            'avg_logged_kcal': round(sum(r['kcal'] for r in rows.values() if r['meals']) / intake_days, 1) if intake_days else None,
            'weight_delta_kg': round(measured[-1] - measured[0], 2) if len(measured) > 1 else None,
            'training_days': sum(bool(r['workouts']) for r in rows.values()),
            'training_minutes': sum(r['workout_minutes'] for r in rows.values()),
            'series': [{'date': d, 'logged_kcal': r['kcal'] if r['meals'] else None,
                        'meals': r['meals'], 'macros_g': {k: r[k] if r['known'][k] == r['meals'] and r['meals'] else None for k in ('protein', 'fat', 'carbs')},
                        'micros': {k: {'amount': value, 'known_meals': r['micro_known'][k], 'total_meals': r['meals']} for k, value in r['micros'].items()},
                        'training_minutes': r['workout_minutes'] if r['workouts'] else None, 'weight_kg': r['weight']} for d, r in rows.items()]}


def render_png(data, end, path, view='nutrition', nutrient='iron_mg'):
    """Render exact logged values, not a generative approximation."""
    from PIL import Image, ImageDraw, ImageFont
    rows = aggregate(data, end)
    im = Image.new('RGB', (1080, 1080), '#101827')
    draw = ImageDraw.Draw(im)
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font = lambda size: ImageFont.truetype(font_path, size)
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
    draw.text((75, 205), (f"Записано: {today['kcal']:.0f} ккал" if today['meals'] else 'Сегодня нет записей о еде') + (f" / план {target:.0f}" if target and today['meals'] else ''), font=font(32), fill='#42d49b')
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
        draw.text((810, y), f"{r['kcal']:.0f}" if r['meals'] else 'нет записи', font=font(19 if not r['meals'] else 24), fill='white' if r['meals'] else '#aab8c8')
        if r['workouts']:
            draw.text((970, y), '●', font=font(22), fill='#ffb454')
    if today['micros']:
        draw.text((75, 920), f"Микро (записано): {len(today['micros'])} показателей", font=font(22), fill='#aab8c8')
    if target:
        draw.text((75, 960), f'План: {target:.0f} ккал/день', font=font(22), fill='#aab8c8')
    draw.text((75, 1000), 'Только записанные данные · оценка питания не диагноз', font=font(20), fill='#8092a6')
    save_png(path, im)


def main(argv=None):
    p = argparse.ArgumentParser(description='Personal fitness journal; no network, no automatic messages')
    p.add_argument('--data-dir', default=os.environ.get('COACH_DATA_DIR', './private-data'))
    sub = p.add_subparsers(dest='command', required=True)
    t = sub.add_parser('target', help='Set user-approved daily kcal goal')
    t.add_argument('--kcal', required=True, type=lambda s: number(s, positive=True))
    m = sub.add_parser('meal', help='Log a confirmed meal estimate')
    m.add_argument('--date', type=day, default=date.today().isoformat())
    m.add_argument('--name', required=True)
    m.add_argument('--kcal', required=True, type=number)
    for macro in ('protein', 'fat', 'carbs'):
        m.add_argument('--' + macro, type=number)
    m.add_argument('--source', choices=('label', 'usda', 'user', 'photo-estimate'), required=True)
    f = sub.add_parser('food', help='Log a weighed USDA item by FDC ID')
    f.add_argument('--date', type=day, default=date.today().isoformat())
    f.add_argument('--fdc-id', type=int, required=True)
    f.add_argument('--grams', type=lambda s: number(s, positive=True), required=True)
    w = sub.add_parser('workout')
    w.add_argument('--date', type=day, default=date.today().isoformat())
    w.add_argument('--name', required=True)
    w.add_argument('--minutes', type=lambda s: number(s, positive=True), required=True)
    w.add_argument('--sets', type=int)
    w.add_argument('--reps', type=int)
    w.add_argument('--load-kg', type=number)
    wt = sub.add_parser('weight')
    wt.add_argument('--date', type=day, default=date.today().isoformat())
    wt.add_argument('--kg', type=lambda s: number(s, positive=True), required=True)
    for cmd in ('report', 'card', 'trends'):
        r = sub.add_parser(cmd)
        r.add_argument('--date', type=day, default=date.today().isoformat())
        if cmd == 'trends':
            r.add_argument('--days', type=int, choices=(7, 14, 28, 90), default=28)
        if cmd == 'card':
            r.add_argument('--output', type=Path, required=True)
            r.add_argument('--view', choices=('nutrition', 'activity', 'micros', 'micro-trend'), default='nutrition')
            from food_lookup import MICROS
            r.add_argument('--nutrient', choices=[key for key, _ in MICROS.values()], default='iron_mg')
    args = p.parse_args(argv)
    path = store_path(args)
    data = load(path)
    if args.command == 'target':
        data['targets']['kcal'] = args.kcal
    elif args.command == 'meal':
        if not args.name.strip():
            p.error('Meal name cannot be blank')
        data['entries'].append({'type': 'meal', 'date': args.date, 'name': args.name.strip(), 'kcal': args.kcal, 'protein': args.protein, 'fat': args.fat, 'carbs': args.carbs, 'source': args.source})
    elif args.command == 'food':
        if args.fdc_id < 1 or args.grams > 10000:
            p.error('Check FDC ID and serving grams')
        from food_lookup import by_id
        item = by_id(args.fdc_id)
        values = item['per_100g']
        if values['kcal'] is None or not item['description']:
            p.error('USDA item has no usable kcal or description; nothing logged')
        factor = args.grams / 100
        data['entries'].append({'type': 'meal', 'date': args.date, 'name': item['description'], 'fdc_id': args.fdc_id, 'grams': args.grams, 'source': 'usda', 'kcal': values['kcal'] * factor, 'protein': values['protein_g'] * factor if values['protein_g'] is not None else None, 'fat': values['fat_g'] * factor if values['fat_g'] is not None else None, 'carbs': values['carbs_g'] * factor if values['carbs_g'] is not None else None, 'micros': {key: value * factor for key, value in values['micros'].items()}})
    elif args.command == 'workout':
        if not args.name.strip():
            p.error('Workout name cannot be blank')
        strength = (args.sets, args.reps, args.load_kg)
        if any(x is not None for x in strength) and (any(x is None for x in strength) or args.sets < 1 or args.reps < 1):
            p.error('For strength work provide positive --sets, --reps and nonnegative --load-kg together')
        data['entries'].append({'type': 'workout', 'date': args.date, 'name': args.name.strip(), 'minutes': args.minutes, 'sets': args.sets, 'reps': args.reps, 'load_kg': args.load_kg})
    elif args.command == 'weight':
        if args.kg > 500:
            p.error('Check weight units (expected kg)')
        data['entries'].append({'type': 'weight', 'date': args.date, 'kg': args.kg})
    elif args.command == 'report':
        print(telegram_text(data, date.fromisoformat(args.date)))
        return
    elif args.command == 'trends':
        print(json.dumps(trends(data, date.fromisoformat(args.date), args.days), ensure_ascii=False, indent=2))
        return
    elif args.command == 'card':
        render_png(data, date.fromisoformat(args.date), args.output, args.view, args.nutrient)
        print(args.output.resolve())
        return
    save(path, data)
    print(f"Recorded {args.command} in {path}")


if __name__ == '__main__':
    main()
