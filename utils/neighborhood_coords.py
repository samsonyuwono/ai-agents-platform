"""NYC neighborhood coordinates for map-based restaurant search."""

from typing import Dict, Optional, Tuple

# NYC default center (Union Square area)
NYC_DEFAULT_CENTER = (40.7430, -73.9930)

# Neighborhood name → (latitude, longitude)
NYC_NEIGHBORHOODS: Dict[str, Tuple[float, float]] = {
    # Manhattan
    'financial district': (40.7075, -74.0089),
    'tribeca': (40.7163, -74.0086),
    'chinatown': (40.7158, -73.9970),
    'little italy': (40.7191, -73.9973),
    'lower east side': (40.7185, -73.9860),
    'soho': (40.7233, -73.9985),
    'nolita': (40.7234, -73.9955),
    'noho': (40.7264, -73.9927),
    'east village': (40.7265, -73.9815),
    'west village': (40.7336, -74.0027),
    'greenwich village': (40.7336, -74.0027),
    'chelsea': (40.7465, -74.0014),
    'flatiron': (40.7411, -73.9897),
    'gramercy': (40.7382, -73.9860),
    'murray hill': (40.7487, -73.9757),
    'kips bay': (40.7420, -73.9801),
    'midtown': (40.7549, -73.9840),
    'midtown east': (40.7549, -73.9712),
    'midtown west': (40.7590, -73.9890),
    'hells kitchen': (40.7638, -73.9918),
    'times square': (40.7580, -73.9855),
    'theater district': (40.7590, -73.9845),
    'upper east side': (40.7736, -73.9566),
    'upper west side': (40.7870, -73.9754),
    'harlem': (40.8116, -73.9465),
    'east harlem': (40.7957, -73.9425),
    'washington heights': (40.8417, -73.9394),
    'inwood': (40.8677, -73.9212),
    'morningside heights': (40.8100, -73.9614),
    'meatpacking district': (40.7401, -74.0079),
    'two bridges': (40.7127, -73.9937),
    'battery park city': (40.7117, -74.0154),

    # Brooklyn
    'williamsburg': (40.7081, -73.9571),
    'dumbo': (40.7033, -73.9890),
    'brooklyn heights': (40.6960, -73.9936),
    'park slope': (40.6710, -73.9799),
    'cobble hill': (40.6861, -73.9960),
    'carroll gardens': (40.6795, -73.9991),
    'boerum hill': (40.6848, -73.9836),
    'fort greene': (40.6893, -73.9742),
    'clinton hill': (40.6892, -73.9662),
    'prospect heights': (40.6770, -73.9685),
    'crown heights': (40.6694, -73.9507),
    'bed-stuy': (40.6872, -73.9418),
    'bushwick': (40.6944, -73.9213),
    'greenpoint': (40.7274, -73.9514),
    'red hook': (40.6734, -74.0080),
    'gowanus': (40.6734, -73.9897),

    # Borough-level
    'manhattan': (40.7580, -73.9855),
    'brooklyn': (40.6782, -73.9442),
    'queens': (40.7282, -73.7949),
    'bronx': (40.8448, -73.8648),
    'staten island': (40.5795, -74.1502),
}

# Common aliases → canonical neighborhood name
NEIGHBORHOOD_ALIASES: Dict[str, str] = {
    'les': 'lower east side',
    'fidi': 'financial district',
    'uws': 'upper west side',
    'ues': 'upper east side',
    'meatpacking': 'meatpacking district',
    'hk': 'hells kitchen',
    'hell\'s kitchen': 'hells kitchen',
    'bk': 'brooklyn',
    'wburg': 'williamsburg',
    'w-burg': 'williamsburg',
    'bk heights': 'brooklyn heights',
    'prospect hts': 'prospect heights',
    'bedstuy': 'bed-stuy',
    'bed stuy': 'bed-stuy',
    'greenwich': 'greenwich village',
    'the village': 'greenwich village',
    'flatiron district': 'flatiron',
    'gramercy park': 'gramercy',
    'nyc': 'manhattan',
    'new york': 'manhattan',
}


def normalize_neighborhood_name(name: str) -> str:
    """Normalize a neighborhood name to its canonical form.

    Args:
        name: Raw neighborhood name (e.g., "UES", "West Village", " soho ")

    Returns:
        Lowercased, stripped canonical name
    """
    cleaned = name.strip().lower()
    return NEIGHBORHOOD_ALIASES.get(cleaned, cleaned)


def get_neighborhood_coords(name: str, city: str = 'ny') -> Optional[Tuple[float, float]]:
    """Look up coordinates for a neighborhood name.

    Args:
        name: Neighborhood name or alias (case-insensitive)
        city: City code (currently only 'ny' supported)

    Returns:
        (latitude, longitude) tuple, or None if not found
    """
    if city.lower() not in ('ny', 'nyc', 'new york'):
        return None

    canonical = normalize_neighborhood_name(name)
    return NYC_NEIGHBORHOODS.get(canonical)
