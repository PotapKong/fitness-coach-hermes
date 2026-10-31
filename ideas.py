#!/usr/bin/env python3
"""Local, read-only candidate for a consented morning brief; never sends messages."""
import argparse
import json
import stat
from datetime import date
from pathlib import Path


def read_private_profile(path):
    path = Path(path).expanduser().resolve()
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError('Profile must be private (chmod 600)')
    profile = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(profile, dict) or profile.get('version') != 1:
        raise ValueError('Unsupported profile version')
    return profile


def make_idea(profile, catalog, for_date):
    """Return an optional recipe and activity, never a health prescription."""
    food = profile.get('food', {})
    exercise = profile.get('activity', {})
    out = {'date': for_date.isoformat(), 'recipe': None, 'activity': None,
           'notes': ['Подборка — идея, не назначение; проверьте состав, аллергию и доступность продуктов.']}
    if not food.get('preferences_confirmed'):
        out['notes'].append('Для рецептов сначала уточните вкусы, исключения, время и возможные аллергии.')
    elif food.get('allergies') or food.get('dietary_exclusions'):
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
            recipes = [r for r in catalog['recipes'] if r['prep_minutes'] + r['cook_minutes'] <= max_minutes
                       and (meal == 'any' or meal in r['meal'])
                       and not any(x in ingredient.casefold() for x in excluded for ingredient in r['ingredients_hint'])]
            if recipes:
                recipe = recipes[for_date.toordinal() % len(recipes)]
                out['recipe'] = {'id': recipe['id'], 'title': recipe['title_ru'],
                                 'url': recipe['url'], 'minutes': recipe['prep_minutes'] + recipe['cook_minutes'],
                                 'ingredients_hint': recipe['ingredients_hint'],
                                 'caution': 'Состав и оборудование уточните на странице источника; совместимость при аллергии не гарантирована.'}
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
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--date', type=date.fromisoformat, default=date.today())
    parser.add_argument('--catalog', type=Path, default=Path(__file__).with_name('recipes.json'))
    args = parser.parse_args(argv)
    profile = read_private_profile(args.profile)
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    if catalog.get('version') != 1 or not isinstance(catalog.get('recipes'), list):
        raise ValueError('Unsupported recipe catalog')
    print(json.dumps(make_idea(profile, catalog, args.date), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
