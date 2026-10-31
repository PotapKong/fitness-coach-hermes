#!/usr/bin/env python3
"""Consent and delivery state machine. No transport: a caller must send and read back."""
import argparse
import hashlib
import json
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import re
import secrets
import stat
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coach import private_directory, save, write_lock
from ideas import make_idea

KINDS = ('morning', 'reminder')
ROUTE = re.compile(r'^(local|telegram:[1-9][0-9]*(?::[1-9][0-9]*)?)$')


def clock(value):
    if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', value):
        raise ValueError('Use 24-hour HH:MM')
    return time.fromisoformat(value)


def validate(spec):
    if spec.get('kind') not in KINDS or not isinstance(spec.get('owner'), str) or not spec['owner'].strip():
        raise ValueError('Kind and an explicit owner identifier are required')
    if not isinstance(spec.get('route'), str) or not ROUTE.fullmatch(spec['route']):
        raise ValueError('Explicit local or private Telegram route required; no inferred chat/group')
    try:
        ZoneInfo(spec['zone'])
    except (KeyError, TypeError, ZoneInfoNotFoundError):
        raise ValueError('Valid IANA timezone required') from None
    send = clock(spec['local_time'])
    quiet_start, quiet_end = clock(spec['quiet_start']), clock(spec['quiet_end'])
    if quiet_start == quiet_end or within_quiet(send, quiet_start, quiet_end):
        raise ValueError('Send time must be outside nonempty quiet hours')
    for key in ('profile', 'journal'):
        path = Path(spec[key]).expanduser()
        if not path.is_absolute() or path.is_symlink():
            raise ValueError(f'{key} path must be absolute and not a symlink')
        if path.resolve().is_relative_to(Path(__file__).resolve().parent):
            raise ValueError(f'{key} cannot live in the public skill directory')
    if spec.get('enabled') is not True or not spec.get('consented_at'):
        raise ValueError('Explicit opt-in required')
    if not re.fullmatch(r'[0-9a-f]{32}', spec.get('consent_generation', '')):
        raise ValueError('Subscription consent generation missing; reconfigure with fresh consent')
    return spec


def within_quiet(instant, start, end):
    return start <= instant < end if start < end else instant >= start or instant < end


def read_state(path):
    private_directory(path.parent)
    if not path.exists():
        return {'version': 1, 'subscriptions': {}, 'deliveries': []}
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError('Automation state must be a private regular file (0600)')
    data = json.loads(path.read_text(encoding='utf8'))
    if data.get('version') != 1 or not isinstance(data.get('subscriptions'), dict) or not isinstance(data.get('deliveries'), list):
        raise ValueError('Unsupported automation state')
    return data


def key(owner, kind):
    return f'{owner}:{kind}'


def configure(path, spec):
    spec = {**spec, 'consent_generation': secrets.token_hex(16)}
    validate(spec)
    private_json(spec['journal'])
    private_json(spec['profile'])
    if path.resolve().is_relative_to(Path(__file__).resolve().parent):
        raise ValueError('Automation state cannot be stored in the public repository')
    with write_lock(path):
        state = read_state(path)
        state['subscriptions'][key(spec['owner'], spec['kind'])] = spec
        save(path, state)
    return {'kind': spec['kind'], 'route': spec['route'], 'enabled': True}


def revoke(path, owner, kind):
    with write_lock(path):
        state = read_state(path)
        item = state['subscriptions'].get(key(owner, kind))
        if item is None:
            return False
        item['enabled'] = False
        item['revoked_at'] = datetime.now(timezone.utc).isoformat()
        save(path, state)
    return True


def private_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError('Private profile/journal must be a regular 0600 file')
    if stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise PermissionError('Private profile/journal parent must be 0700')
    return json.loads(path.read_text(encoding='utf8'))


def candidate(state, owner, kind, now=None):
    spec = state['subscriptions'].get(key(owner, kind))
    if not spec or not spec.get('enabled'):
        return None
    validate(spec)
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(spec['zone']))
    start = local.replace(hour=clock(spec['local_time']).hour, minute=clock(spec['local_time']).minute, second=0, microsecond=0)
    if not start <= local < start + timedelta(minutes=15):
        return None  # no catch-up after downtime or DST skips
    if within_quiet(local.time(), clock(spec['quiet_start']), clock(spec['quiet_end'])):
        return None
    day = local.date().isoformat()
    route = spec['route']
    if any(d['owner'] == owner and d['kind'] == kind and d['date'] == day for d in state['deliveries']):
        return None  # ambiguous reservations are NEVER automatically retried
    if kind == 'reminder':
        journal = private_json(spec['journal'])
        if any(e.get('type') == 'meal' and not e.get('voided') and e.get('date') == day for e in journal.get('entries', [])):
            return None
        message = 'Если удобно, можно отметить, что сегодня было из еды. Нет записи — это просто нет данных.'
        recipe_id = None
        activity_included = False
    else:
        profile = private_json(spec['profile'])
        if not isinstance(profile, dict) or profile.get('version') != 1:
            raise ValueError('Unsupported private profile version')
        history = {'offers': [{'date': d['date'], 'recipe_id': d['recipe_id'], 'delivered': True}
                              for d in state['deliveries'] if d['owner'] == owner and d['kind'] == 'morning' and d['status'] == 'delivered' and d.get('recipe_id')]}
        catalog_bytes = Path(__file__).with_name('recipes.json').read_bytes()
        catalog = json.loads(catalog_bytes)
        idea = make_idea(profile, catalog, local.date(), history)
        if idea['recipe'] is None and idea['activity'] is None:
            return None
        recipe_id = idea['recipe']['id'] if idea['recipe'] else None
        activity_included = idea['activity'] is not None
        pieces = []
        if idea['recipe']:
            pieces.append(f"Идея блюда: {idea['recipe']['title']} · {idea['recipe']['url']}. Время до готовности: {idea['recipe']['ready_minutes']} мин. Проверьте полный состав на сайте источника.")
        if idea['activity']:
            pieces.append(idea['activity'])
        message = '\n'.join(pieces)
    item = {'owner': owner, 'kind': kind, 'date': day, 'route': route,
            'consent_generation': spec['consent_generation'],
            'recipe_id': recipe_id, 'activity_included': activity_included, 'message': message}
    if kind == 'morning':
        item['profile_digest'] = hashlib.sha256(json.dumps(profile, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        item['catalog_digest'] = hashlib.sha256(catalog_bytes).hexdigest()
    return item


def reserve(path, owner, kind, now=None):
    with write_lock(path):
        state = read_state(path)
        item = candidate(state, owner, kind, now)
        if item is None:
            return None
        nonce = secrets.token_hex(16)
        state['deliveries'].append({k: v for k, v in item.items() if k != 'message'} |
                                   {'nonce': nonce, 'status': 'reserved', 'reserved_at': datetime.now(timezone.utc).isoformat()})
        save(path, state)
    public_item = {k: v for k, v in item.items() if k not in ('consent_generation', 'profile_digest', 'catalog_digest')}
    return {'nonce': nonce, **public_item, 'warning': 'Reservation only: atomically claim with pre-send once, then verify exact destination and acknowledge. Never auto-retry an ambiguous send.'}


def _eligible(state, nonce, now=None):
    entry = next((d for d in state['deliveries'] if d['nonce'] == nonce), None)
    if not entry or entry['status'] != 'reserved':
        return False
    spec = state['subscriptions'].get(key(entry['owner'], entry['kind']))
    if (not spec or not spec.get('enabled') or spec['route'] != entry['route']
            or spec.get('consent_generation') != entry.get('consent_generation')):
        return False
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(spec['zone']))
    if local.date().isoformat() != entry['date'] or within_quiet(local.time(), clock(spec['quiet_start']), clock(spec['quiet_end'])):
        return False
    start = local.replace(hour=clock(spec['local_time']).hour, minute=clock(spec['local_time']).minute, second=0, microsecond=0)
    if not start <= local < start + timedelta(minutes=15):
        return False
    if entry['kind'] == 'reminder':
        journal = private_json(spec['journal'])
        return not any(e.get('type') == 'meal' and not e.get('voided') and e.get('date') == entry['date'] for e in journal.get('entries', []))
    if entry['kind'] == 'morning':
        profile = private_json(spec['profile'])
        if hashlib.sha256(json.dumps(profile, sort_keys=True, ensure_ascii=False).encode()).hexdigest() != entry.get('profile_digest'):
            return False
        if hashlib.sha256(Path(__file__).with_name('recipes.json').read_bytes()).hexdigest() != entry.get('catalog_digest'):
            return False
    return True

def pre_send(path, nonce, now=None):
    """Single-use atomic send claim; True means this caller alone may attempt once."""
    with write_lock(path):
        state = read_state(path)
        if not _eligible(state, nonce, now):
            return False
        entry = next(d for d in state['deliveries'] if d['nonce'] == nonce)
        entry.update(status='claimed', claimed_at=datetime.now(timezone.utc).isoformat())
        save(path, state)
    return True


def acknowledge(path, nonce, route, message_id):
    if not message_id or not isinstance(message_id, str):
        raise ValueError('Verified external message ID required')
    with write_lock(path):
        state = read_state(path)
        entry = next((d for d in state['deliveries'] if d['nonce'] == nonce), None)
        if entry is None or entry['status'] != 'claimed' or entry['route'] != route:
            raise ValueError('No matching claimed delivery and exact route')
        entry.update(status='delivered', message_id=message_id, acknowledged_at=datetime.now(timezone.utc).isoformat())
        save(path, state)
    return True


def main(argv=None):
    p = argparse.ArgumentParser(description='Private consent/dedupe engine; NEVER sends messages')
    p.add_argument('--state', type=Path, default=Path.home() / '.local/share/fitness-coach-hermes/automation.json')
    sub = p.add_subparsers(dest='action', required=True)
    cfg = sub.add_parser('configure')
    cfg.add_argument('--owner', required=True)
    cfg.add_argument('--kind', choices=KINDS, required=True)
    cfg.add_argument('--route', required=True)
    cfg.add_argument('--zone', required=True)
    cfg.add_argument('--local-time', required=True)
    cfg.add_argument('--quiet-start', required=True)
    cfg.add_argument('--quiet-end', required=True)
    cfg.add_argument('--profile', required=True)
    cfg.add_argument('--journal', required=True)
    cfg.add_argument('--confirmed-by-user', action='store_true', required=True)
    for action in ('revoke', 'reserve'):
        q = sub.add_parser(action)
        q.add_argument('--owner', required=True)
        q.add_argument('--kind', choices=KINDS, required=True)
    check = sub.add_parser('pre-send')
    check.add_argument('--nonce', required=True)
    ack = sub.add_parser('ack')
    ack.add_argument('--nonce', required=True)
    ack.add_argument('--route', required=True)
    ack.add_argument('--message-id', required=True)
    args = p.parse_args(argv)
    path = args.state.expanduser().absolute()
    if args.action == 'configure':
        spec = {'owner': args.owner, 'kind': args.kind, 'route': args.route, 'zone': args.zone,
                'local_time': args.local_time, 'quiet_start': args.quiet_start, 'quiet_end': args.quiet_end,
                'profile': args.profile, 'journal': args.journal, 'enabled': True,
                'consented_at': datetime.now(timezone.utc).isoformat()}
        result = configure(path, spec)
    elif args.action == 'revoke':
        result = {'revoked': revoke(path, args.owner, args.kind)}
    elif args.action == 'reserve':
        result = reserve(path, args.owner, args.kind)
    elif args.action == 'pre-send':
        result = {'safe_to_attempt_send': pre_send(path, args.nonce)}
    else:
        result = {'acknowledged': acknowledge(path, args.nonce, args.route, args.message_id)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
