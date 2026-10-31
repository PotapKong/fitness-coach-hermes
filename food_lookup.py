#!/usr/bin/env python3
"""USDA food lookup: explicitly select kcal, never confuse kJ with kcal."""
import argparse
import json
import os
import urllib.parse
import urllib.request


def food_nutrients(food):
    nutrients = food.get('foodNutrients', [])
    def pick(name, unit):
        values = [x.get('value') for x in nutrients if x.get('nutrientName') == name and str(x.get('unitName', '')).lower() == unit.lower() and isinstance(x.get('value'), (int, float))]
        return values[0] if values else None
    return {
        'fdcId': food.get('fdcId'),
        'description': food.get('description'),
        'per_100g': {
            'kcal': pick('Energy', 'kcal'),
            'protein_g': pick('Protein', 'g'),
            'fat_g': pick('Total lipid (fat)', 'g'),
            'carbs_g': pick('Carbohydrate, by difference', 'g'),
        },
    }


def search(query):
    params = urllib.parse.urlencode({'api_key': os.environ.get('USDA_API_KEY', 'DEMO_KEY'), 'query': query, 'pageSize': 5, 'dataType': 'Foundation,SR Legacy'})
    request = urllib.request.Request('https://api.nal.usda.gov/fdc/v1/foods/search?' + params, headers={'Accept': 'application/json', 'User-Agent': 'fitness-coach-hermes/0.1'})
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.load(response)
    return [food_nutrients(x) for x in payload.get('foods', [])]


def main():
    p = argparse.ArgumentParser(description='Search USDA FoodData Central by name (values per 100g)')
    p.add_argument('query')
    args = p.parse_args()
    for food in search(args.query):
        print(json.dumps(food, ensure_ascii=False))
    print('Verify food and weighed serving before logging. Missing values are null, not zero.')


if __name__ == '__main__':
    main()
