#!/usr/bin/env python3
"""Local, read-only candidate for a consented morning brief; never sends messages."""
import argparse
import json
import stat
from datetime import date, timedelta
from pathlib import Path


def read_private_profile(path):
    path = Path(path).expanduser().resolve()
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError('Profile must be private (chmod 600)')
    profile = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(profile, dict) or profile.get('version') != 1:
        raise ValueError('Unsupported profile version')
    return profile


def validate_catalog(catalog):
    """Prevent broken/unreviewed catalog entries from being silently recommended."""
    from urllib.parse import urlparse
    if catalog.get('version') != 1 or not isinstance(catalog.get('recipes'), list):
        raise ValueError('Unsupported recipe catalog')
    ids = set()
    for recipe in catalog['recipes']:
        rid = recipe.get('id')
        url = recipe.get('url', '')
        parsed = urlparse(url)
        if not isinstance(rid, str) or not rid or rid in ids or parsed.scheme != 'https' or not parsed.netloc:
            raise ValueError('Recipe needs unique ID and canonical HTTPS source URL')
        ids.add(rid)
        for key in ('prep_minutes', 'cook_minutes'):
            value = recipe.get(key)
            if type(value) is not int or value < 0 or value > 1440:
                raise ValueError(f'Invalid {key} for {rid}')
        if not recipe.get('title_ru') or not isinstance(recipe.get('ingredients_hint'), list) or not recipe.get('meal'):
            raise ValueError(f'Incomplete recipe {rid}')
        if type(recipe.get('rest_minutes', 0)) is not int or recipe.get('rest_minutes', 0) < 0:
            raise ValueError(f'Invalid rest time for {rid}')
    return catalog


def weekly_feedback_questions(journal, end):
    """Ask only about foods explicitly logged in the prior seven days."""
    start = end - timedelta(days=6)
    names = list(dict.fromkeys(e['name'] for e in journal.get('entries', [])
                               if e.get('type') == 'meal' and start.isoformat() <= e.get('date', '') <= end.isoformat()
                               and isinstance(e.get('name'), str) and e['name'].strip()))
    return {'start': start.isoformat(), 'end': end.isoformat(), 'logged_food_names': names,
            'question': 'Что из записанного на этой неделе понравилось больше? Что хотелось бы повторить или, наоборот, исключить?',
            'note': 'Названия из журнала — не доказательство, что рецепт из каталога был приготовлен или понравился. Сохранить предпочтение только после ответа владельца.'}


def make_idea(profile, catalog, for_date, history=None, occasion='morning'):
    """Return an optional recipe and activity, never a health prescription."""
    validate_catalog(catalog)
    if occasion not in ('morning', 'evening'):
        raise ValueError('Invalid occasion')
    history = history or {}
    food = profile.get('food', {})
    exercise = profile.get('activity', {})
    out = {'date': for_date.isoformat(), 'recipe': None, 'activity': None,
           'notes': ['Подборка — идея, не назначение; проверьте состав, аллергию и доступность продуктов.']}
    if not food.get('preferences_confirmed'):
        out['notes'].append('Для рецептов сначала уточните вкусы, исключения, время и возможные аллергии.')
    elif type(food.get('allergies')) is not list or type(food.get('dietary_exclusions')) is not list:
        out['notes'].append('Перед подбором явно подтвердите список аллергий и пищевых исключений, даже если оба пусты.')
    elif food['allergies'] or food['dietary_exclusions']:
        # Ingredient hints are intentionally not exhaustive; never infer allergen safety.
        out['notes'].append('При аллергии или пищевых исключениях автоподбор отключён: нужна проверка полного состава источника и упаковок.')
    else:
        max_minutes = food.get('max_minutes')
        if not isinstance(max_minutes, int) or isinstance(max_minutes, bool) or not 5 <= max_minutes <= 240:
            out['notes'].append('Для отбора рецептов укажите время готовки от 5 до 240 минут.')
        else:
            meal = food.get('meal', 'any')
            if meal not in ('any', 'breakfast', 'lunch', 'dinner', 'snack'):
                raise ValueError('Invalid meal preference')
            disliked = food.get('disliked_ingredients', [])
            if not isinstance(disliked, list) or any(not isinstance(x, str) for x in disliked):
                raise ValueError('Invalid disliked ingredients')
            excluded = [x.casefold() for x in disliked]
            if not isinstance(food.get('disliked_recipe_ids', []), list) or not isinstance(food.get('preferred_tags', []), list) or not isinstance(food.get('liked_recipe_ids', []), list):
                raise ValueError('Invalid preference list')
            rejected = set(food.get('disliked_recipe_ids', []))
            if any(not isinstance(x, str) for x in rejected):
                raise ValueError('Invalid disliked recipe IDs')
            preferred = set(food.get('preferred_tags', []))
            if any(not isinstance(x, str) for x in preferred) or any(not isinstance(x, str) for x in food.get('liked_recipe_ids', [])):
                raise ValueError('Invalid preferred tags')
            recipes = [r for r in catalog['recipes'] if r['id'] not in rejected
                       and r['prep_minutes'] + r['cook_minutes'] + (r.get('rest_minutes', 0) if occasion == 'morning' else 0) <= max_minutes
                       and (meal == 'any' or meal in r['meal'])
                       and not any(x in ingredient.casefold() for x in excluded for ingredient in r['ingredients_hint'])]
            if recipes:
                if not isinstance(history, dict):
                    raise ValueError('Invalid offer history')
                offers = history.get('offers', [])
                if not isinstance(offers, list):
                    raise ValueError('Invalid offer history')
                recent = {o['recipe_id'] for o in offers if isinstance(o, dict) and o.get('delivered') is True
                          and isinstance(o.get('recipe_id'), str) and isinstance(o.get('date'), str)
                          and (for_date - timedelta(days=7)).isoformat() <= o['date'] < for_date.isoformat()}
                fresh = [r for r in recipes if r['id'] not in recent]
                pool = fresh or recipes
                liked = set(food.get('liked_recipe_ids', []))
                # Include enough alternatives even if one item is liked: avoid repeating a single favorite every day.
                pool.sort(key=lambda r: (-3 * (r['id'] in liked) - len(preferred.intersection(r.get('tags', []))), r['id']))
                finalists = pool[:min(7, len(pool))]
                recipe = finalists[for_date.toordinal() % len(finalists)]
                out['recipe'] = {'id': recipe['id'], 'title': recipe['title_ru'],
                                 'url': recipe['url'], 'minutes': recipe['prep_minutes'] + recipe['cook_minutes'],
                                 'ready_minutes': recipe['prep_minutes'] + recipe['cook_minutes'] + recipe.get('rest_minutes', 0),
                                 'rest_minutes': recipe.get('rest_minutes', 0),
                                 'tags': recipe.get('tags', []),
                                 'ingredients_hint': recipe['ingredients_hint'],
                                 'caution': 'Состав и оборудование уточните на странице источника; совместимость при аллергии не гарантирована.'}
                if not fresh:
                    out['notes'].append('Все подходящие идеи уже предлагались недавно; повтор можно заменить новым проверенным рецептом.')
            else:
                out['notes'].append('Подтверждённых рецептов под эти фильтры в каталоге пока нет; предложите владельцу дополнить его.')
    if exercise.get('preferences_confirmed') and exercise.get('cleared_for_general_activity') is True:
        choices = exercise.get('preferred_activities', [])
        if 'walking' in choices:
            out['activity'] = 'Если комфортно, короткая прогулка в удобном темпе; время и нагрузку выберите сами.'
        elif 'mobility' in choices:
            out['activity'] = 'Если комфортно, лёгкая подвижность без боли; остановитесь при дискомфорте.'
    elif exercise.get('preferences_confirmed'):
        out['notes'].append('Идею активности пока не предлагаю: ограничения и безопасность не подтверждены.')
    else:
        out['notes'].append('Для идеи активности сначала уточните предпочтения и ограничения.')
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only local candidate; no scheduling or delivery')
    parser.add_argument('--profile', type=Path, help='Private preference profile; required for recipe ideas')
    parser.add_argument('--date', type=date.fromisoformat, default=date.today())
    parser.add_argument('--catalog', type=Path, default=Path(__file__).with_name('recipes.json'))
    parser.add_argument('--history', type=Path, help='Optional private 0600 JSON with delivered offers; read-only')
    parser.add_argument('--occasion', choices=('morning', 'evening'), default='morning', help='Evening may include make-ahead recipes')
    parser.add_argument('--weekly-feedback', action='store_true', help='Ask about actually logged meal names from the prior week')
    parser.add_argument('--journal', type=Path, help='Private journal for --weekly-feedback only')
    args = parser.parse_args(argv)
    if args.weekly_feedback:
        if not args.journal:
            parser.error('--weekly-feedback requires --journal')
        journal = read_private_profile(args.journal)
        print(json.dumps(weekly_feedback_questions(journal, args.date), ensure_ascii=False, indent=2))
    else:
        if not args.profile:
            parser.error('Recipe ideas require --profile')
        profile = read_private_profile(args.profile)
        catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
        history = read_private_profile(args.history) if args.history else None
        print(json.dumps(make_idea(profile, catalog, args.date, history, args.occasion), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
