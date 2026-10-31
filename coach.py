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


def number(value, *, positive=False):
    n = float(value)
    if not math.isfinite(n) or n < 0 or (positive and n == 0):
        raise argparse.ArgumentTypeError('Use a finite positive value' if positive else 'Use a finite nonnegative value')
    return n


def day(value):
    return date.fromisoformat(value).isoformat()


def aggregate(data, end, days=7):
    start = end - timedelta(days=days - 1)
    rows = {str(start + timedelta(days=i)): {'kcal': 0, 'protein': 0, 'fat': 0, 'carbs': 0, 'meals': 0, 'workouts': 0, 'weight': None} for i in range(days)}
    for e in data['entries']:
        d = e['date']
        if d not in rows:
            continue
        r = rows[d]
        if e['type'] == 'meal':
            r['meals'] += 1
            for key in ('kcal', 'protein', 'fat', 'carbs'):
                r[key] += e[key]
        elif e['type'] == 'workout':
            r['workouts'] += 1
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
    lines = [header, f"Б {today['protein']:.0f} г · Ж {today['fat']:.0f} г · У {today['carbs']:.0f} г", '', 'Последние 7 дней:']
    scale = max([r['kcal'] for r in rows.values()] + ([target] if target else [1]))
    for d, r in rows.items():
        blocks = min(12, round(12 * r['kcal'] / scale)) if r['kcal'] else 0
        mark = '█' * blocks + '░' * (12 - blocks)
        lines.append(f"{d[5:]}  {mark}  " + (f"{r['kcal']:.0f} ккал" if r['meals'] else 'нет записей') + (' · 🏋️' if r['workouts'] else ''))
    weights = [(d, r['weight']) for d, r in rows.items() if r['weight'] is not None]
    if weights:
        lines.append(f"Вес: {weights[-1][1]:.1f} кг ({weights[-1][0]})")
    lines.append('Учтены только записанные приёмы пищи; фото и порции без веса — оценка.')
    return '\n'.join(lines)


def render_png(data, end, path):
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
    draw.text((75, 205), (f"Записано: {today['kcal']:.0f} ккал" if today['meals'] else 'Сегодня нет записей о еде') + (f" / план {target:.0f}" if target and today['meals'] else ''), font=font(32), fill='#42d49b')
    draw.text((75, 265), f"Б {today['protein']:.0f} г    Ж {today['fat']:.0f} г    У {today['carbs']:.0f} г" if today['meals'] else 'Пустой день не означает голодание', font=font(26), fill='white')
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
    if target:
        draw.text((75, 950), f'План: {target:.0f} ккал/день', font=font(24), fill='#aab8c8')
    draw.text((75, 1000), 'Только записанные данные · оценка питания не диагноз', font=font(20), fill='#8092a6')
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, 'PNG')


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
        m.add_argument('--' + macro, type=number, default=0.0)
    m.add_argument('--source', choices=('label', 'usda', 'user', 'photo-estimate'), required=True)
    w = sub.add_parser('workout')
    w.add_argument('--date', type=day, default=date.today().isoformat())
    w.add_argument('--name', required=True)
    w.add_argument('--minutes', type=lambda s: number(s, positive=True), required=True)
    wt = sub.add_parser('weight')
    wt.add_argument('--date', type=day, default=date.today().isoformat())
    wt.add_argument('--kg', type=lambda s: number(s, positive=True), required=True)
    for cmd in ('report', 'card'):
        r = sub.add_parser(cmd)
        r.add_argument('--date', type=day, default=date.today().isoformat())
        if cmd == 'card':
            r.add_argument('--output', type=Path, required=True)
    args = p.parse_args(argv)
    path = store_path(args)
    data = load(path)
    if args.command == 'target':
        data['targets']['kcal'] = args.kcal
    elif args.command == 'meal':
        if not args.name.strip():
            p.error('Meal name cannot be blank')
        data['entries'].append({'type': 'meal', 'date': args.date, 'name': args.name.strip(), 'kcal': args.kcal, 'protein': args.protein, 'fat': args.fat, 'carbs': args.carbs, 'source': args.source})
    elif args.command == 'workout':
        if not args.name.strip():
            p.error('Workout name cannot be blank')
        data['entries'].append({'type': 'workout', 'date': args.date, 'name': args.name.strip(), 'minutes': args.minutes})
    elif args.command == 'weight':
        if args.kg > 500:
            p.error('Check weight units (expected kg)')
        data['entries'].append({'type': 'weight', 'date': args.date, 'kg': args.kg})
    elif args.command == 'report':
        print(telegram_text(data, date.fromisoformat(args.date)))
        return
    elif args.command == 'card':
        render_png(data, date.fromisoformat(args.date), args.output)
        print(args.output.resolve())
        return
    save(path, data)
    print(f"Recorded {args.command} in {path}")


if __name__ == '__main__':
    main()
