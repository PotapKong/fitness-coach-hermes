#!/usr/bin/env python3
"""Stage public recipe-page metadata; manual review required before catalog import."""
import argparse
import html
import json
import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.collecting = False
        self.scripts = []
        self.current = ''

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('type', '').lower() == 'application/ld+json':
            self.collecting = True
            self.current = ''

    def handle_data(self, data):
        if self.collecting:
            self.current += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.collecting:
            self.scripts.append(self.current)
            self.collecting = False


def hostname_allowed(url, domains):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    return parsed.scheme == 'https' and not parsed.username and not parsed.password and any(host == d or host.endswith('.' + d) for d in domains)


class SafeRedirect(HTTPRedirectHandler):
    def __init__(self, domains):
        self.domains = domains

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not hostname_allowed(newurl, self.domains):
            raise ValueError('Redirect escaped reviewed source domains')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def minutes(iso):
    if not iso:
        return None
    matched = re.fullmatch(r'P(?:0D|(?:(\d+)D))?T(?:(\d+)H)?(?:(\d+)M)?', iso)
    if not matched or not any(x is not None for x in matched.groups()):
        return None
    days, hours, mins = (int(x or 0) for x in matched.groups())
    return days * 1440 + hours * 60 + mins


def recipes_in_html(text):
    parser = ScriptParser()
    parser.feed(text)
    def nodes(value):
        if isinstance(value, list):
            for node in value:
                yield from nodes(node)
        elif isinstance(value, dict):
            if value.get('@type') == 'Recipe' or 'Recipe' in value.get('@type', []):
                yield value
            for child in value.get('@graph', []):
                yield from nodes(child)
    for raw in parser.scripts:
        try:
            yield from nodes(json.loads(raw))
        except (ValueError, TypeError):
            continue


def stage(url, domains, fetch=None):
    if not hostname_allowed(url, domains):
        raise ValueError('URL must be HTTPS on a reviewed source domain')
    if fetch is None:
        opener = build_opener(SafeRedirect(domains))
        def fetch(u):
            with opener.open(Request(u, headers={'User-Agent': 'fitness-coach-hermes-curator/0.1'}), timeout=12) as response:
                if not hostname_allowed(response.url, domains):
                    raise ValueError('Unexpected final source domain')
                return response.read(2_000_001).decode('utf-8', 'replace')
    text = fetch(url)
    if len(text) > 2_000_000:
        raise ValueError('Page too large for safe staging')
    for recipe in recipes_in_html(text):
        prep, cook, total = (minutes(recipe.get(key)) for key in ('prepTime', 'cookTime', 'totalTime'))
        name = recipe.get('name')
        if not isinstance(name, str) or not name.strip():
            continue
        return {'canonical_url_to_review': url, 'source_title': html.unescape(name.strip()),
                'prep_minutes': prep, 'cook_minutes': cook, 'total_minutes': total,
                'checked_on': date.today().isoformat(), 'status': 'candidate_needs_human_review',
                'note': 'Check ingredients, equipment, copyright, redirect URL and time semantics; no health/allergy claim.'}
    raise ValueError('No parseable Recipe JSON-LD; review page manually or reject')


def main(argv=None):
    p = argparse.ArgumentParser(description='Fetch public recipe metadata for manual curation; never auto-publish')
    p.add_argument('urls', nargs='+')
    p.add_argument('--allow-domain', action='append', required=True, help='Review each first-party source before allowing it')
    args = p.parse_args(argv)
    results = []
    for url in args.urls:
        try:
            results.append(stage(url, [d.lower() for d in args.allow_domain]))
        except (ValueError, OSError) as error:
            results.append({'url': url, 'status': 'rejected', 'error': str(error)[:200]})
    print(json.dumps({'candidates': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
