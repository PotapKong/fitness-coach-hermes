#!/usr/bin/env python3
"""USDA food lookup: explicitly select kcal, never confuse kJ with kcal."""
import argparse
import json
import math
import os
import urllib.parse
import urllib.error
import urllib.request

MICROS = {
    1087: ('calcium_mg', 'mg'), 1089: ('iron_mg', 'mg'),
    1090: ('magnesium_mg', 'mg'), 1092: ('potassium_mg', 'mg'),
    1093: ('sodium_mg', 'mg'), 1095: ('zinc_mg', 'mg'),
    1106: ('vitamin_a_rae_ug', 'µg'), 1114: ('vitamin_d_ug', 'µg'),
    1162: ('vitamin_c_mg', 'mg'), 1178: ('vitamin_b12_ug', 'µg'),
    1190: ('folate_dfe_ug', 'µg'), 1079: ('fiber_g', 'g'),
}


def fields(food):
    """Normalize nutrient shapes from both USDA search and detail endpoints."""
    for item in food.get('foodNutrients', []):
        nutrient = item.get('nutrient') or {}
        yield (item.get('nutrientId', nutrient.get('id')),
               item.get('nutrientName', nutrient.get('name')),
               str(item.get('unitName', nutrient.get('unitName', ''))).lower().replace('ug', 'µg'),
               item.get('value', item.get('amount')))


def food_nutrients(food):
    nutrients = list(fields(food))
    relevant = {'Energy', 'Protein', 'Total lipid (fat)', 'Carbohydrate, by difference'}
    for identifier, name, _, value in nutrients:
        if (identifier in MICROS or name in relevant) and value is not None:
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('USDA returned an invalid nutrient amount; nothing logged')
    def pick(name, unit):
        values = [value for _, n, u, value in nutrients if n == name and u == unit.lower() and isinstance(value, (int, float))]
        return values[0] if values else None
    micros = {}
    for identifier, _, unit, value in nutrients:
        if identifier in MICROS and unit == MICROS[identifier][1].lower() and isinstance(value, (int, float)):
            micros[MICROS[identifier][0]] = value
    return {
        'fdcId': food.get('fdcId'),
        'description': food.get('description'),
        'per_100g': {
            'kcal': pick('Energy', 'kcal'),
            'protein_g': pick('Protein', 'g'),
            'fat_g': pick('Total lipid (fat)', 'g'),
            'carbs_g': pick('Carbohydrate, by difference', 'g'),
            'micros': micros,
        },
    }


def fetch_json(url):
    try:
        request = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'fitness-coach-hermes/0.1'})
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'USDA HTTP {exc.code}; check the food ID, key or rate limit') from None
    except urllib.error.URLError:
        raise RuntimeError('USDA network unavailable; nothing was logged') from None


def search(query):
    params = urllib.parse.urlencode({'api_key': os.environ.get('USDA_API_KEY', 'DEMO_KEY'), 'query': query, 'pageSize': 5, 'dataType': 'Foundation,SR Legacy'})
    payload = fetch_json('https://api.nal.usda.gov/fdc/v1/foods/search?' + params)
    return [food_nutrients(x) for x in payload.get('foods', [])]


def by_id(fdc_id):
    params = urllib.parse.urlencode({'api_key': os.environ.get('USDA_API_KEY', 'DEMO_KEY')})
    return food_nutrients(fetch_json(f'https://api.nal.usda.gov/fdc/v1/food/{int(fdc_id)}?' + params))


def main():
    p = argparse.ArgumentParser(description='Search USDA FoodData Central by name (values per 100g)')
    p.add_argument('query')
    args = p.parse_args()
    for food in search(args.query):
        print(json.dumps(food, ensure_ascii=False))
    print('Verify food and weighed serving before logging. Missing values are null, not zero.')


if __name__ == '__main__':
    main()
