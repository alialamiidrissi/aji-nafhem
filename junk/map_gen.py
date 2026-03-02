import requests
import json
import os
import pycountry

def generate_country_svg(country_code, output_path='output.svg'):
    """
    Generate SVG map for a country from GADM GeoJSON.
    
    Args:
    country_code (str): ISO alpha-3 code, e.g., 'MAR' for Morocco.
    output_path (str): Path to save SVG file.
    
    Returns:
    str: Path to generated SVG.
    """
    country = pycountry.countries.get(alpha_3=country_code.upper())
    if not country:
        raise ValueError(f"Invalid country code: {country_code}")
    
    countryName = country.name
    print(f'Generating Map for: {countryName}')
    
    # Fetch GeoJSON
    re = requests.get(f'https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_{country_code.upper()}_0.json')
    data = json.loads(re.text)
    
    # Extract points
    allPoints = []
    pointGroups = []
    for i in data['features'][0]['geometry']['coordinates']:
        for group in i:
            pointGroups.append(group)
            for coord in group:
                allPoints.append(coord)
    
    # Compute bounds
    lowestX, highestX = min(p[0] for p in allPoints), max(p[0] for p in allPoints)
    lowestY, highestY = min(p[1] for p in allPoints), max(p[1] for p in allPoints)
    
    svgWidth = highestX - lowestX
    svgHeight = highestY - lowestY
    
    # Build polygons
    polygonString = ''
    for group in pointGroups:
        coordinateString = ' '.join(f'{coord[0] - lowestX},{coord[1] - lowestY}' for coord in group)
        polygonString += f'<polygon points="{coordinateString}"/>'
    
    svgContent = f"""<svg width="{svgWidth}" height="{svgHeight}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" style="transform: scale(1, -1)">
{polygonString}
</svg>"""
    
    # Ensure output dir
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    
    with open(output_path, 'w') as f:
        f.write(svgContent)
    
    print(f'SVG saved to: {output_path}')
    return output_path
