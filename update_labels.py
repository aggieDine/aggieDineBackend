import json
import re
import os

filepath = r'c:\Users\cbabi\OneDrive\Desktop\repos\aggieDineBackend\app\services\locations.py'
with open(filepath, 'r') as f:
    text = f.read()

m = re.search(r'ALL_FOOD_LOCATIONS = (\[.*\])', text, re.DOTALL)
if m:
    data = eval(m.group(1))
    for loc in data:
        diet = []
        if loc.get('restriction') == 'vegan':
            diet.extend(['Vegan', 'Vegetarian', 'Dairy-Free'])
        elif loc.get('restriction') == 'vegetarian':
            diet.append('Vegetarian')
        
        name = loc['name'].lower()
        if 'halal' in name:
            diet.append('Halal')
        if 'smoothie' in name:
            diet.extend(['Vegetarian', 'Gluten-Free'])
        if 'pizza' in name:
            diet.append('Vegetarian')

        loc['dietary'] = list(set(diet))
        loc['allergens'] = []

    out = 'ALL_FOOD_LOCATIONS = [\n'
    for i, loc in enumerate(data):
        out += '    {\n'
        out += f'        "name": "{loc["name"]}",\n'
        out += f'        "latitude": {loc["latitude"]},\n'
        out += f'        "longitude": {loc["longitude"]},\n'
        out += f'        "cuisine": "{loc["cuisine"]}",\n'
        out += f'        "restriction": "{loc.get("restriction","")}",\n'
        out += f'        "dietary": {json.dumps(loc.get("dietary", []))},\n'
        out += f'        "allergens": {json.dumps(loc.get("allergens", []))}\n'
        if i == len(data) - 1:
            out += '    }\n'
        else:
            out += '    },\n'
    out += ']\n'

    with open(filepath, 'w') as f:
        f.write(out)
    print("Done updating")
else:
    print("Failed to find ALL_FOOD_LOCATIONS list")
