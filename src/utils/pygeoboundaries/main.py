from typing import List, Union

import geojson
import requests
from fuzzywuzzy import process
from requests_cache import CachedSession

from . import countries_iso_dict, iso_codes


class SessionManager:
    def __init__(self):
        self._session = None

    def get_session(self):
        if self._session is None:
            self._session = CachedSession(expire_after=604800)  # Default to 1 week
        return self._session

    def clear_cache(self):
        if self._session:
            self._session.cache.clear()

    def set_cache_expire_time(self, seconds: int):
        self._session = CachedSession(expire_after=seconds)

    def disable_cache(self):
        self._session = requests.Session()


# Instantiate SessionManager
session_manager = SessionManager()


def _is_valid_adm(iso3, adm: str) -> bool:
    session = session_manager.get_session()
    html = session.get(
        f"https://www.geoboundaries.org/api/current/gbOpen/{iso3}/", verify=True
    ).text
    return adm in html


def _validate_adm(adm: Union[str, int]) -> str:
    if isinstance(adm, int) or len(str(adm)) == 1:
        adm = "ADM" + str(adm)
    if str.upper(adm) in [f"ADM{i}" for i in range(6)] or str.upper(adm) == "ALL":
        return str.upper(adm)
    raise KeyError("Invalid ADM level provided.")


def _get_smallest_adm(iso3):
    current_adm = 5
    while current_adm >= 0:
        if _is_valid_adm(iso3, f"ADM{current_adm}"):
            break
        current_adm -= 1
    print(f"Smallest ADM level found for {iso3} : ADM{current_adm}")
    return f"ADM{current_adm}"


def _is_valid_iso3_code(territory: str) -> bool:
    return str.lower(territory) in iso_codes.iso_codes


def _get_iso3_from_name_or_iso2(name: str) -> str:
    name_lower = str.lower(name)

    # Try to get a direct match first
    if name_lower in countries_iso_dict.countries_iso3:
        return str.upper(countries_iso_dict.countries_iso3[name_lower])

    # If no direct match, use fuzzy matching to find the closest key
    closest_match, match_score = process.extractOne(
        name_lower, countries_iso_dict.countries_iso3.keys()
    )

    # Set a threshold for the match score to consider it a valid match
    # You might need to adjust this based on your testing
    if match_score >= 80:  # Assuming a threshold of 80%
        return str.upper(countries_iso_dict.countries_iso3[closest_match])

    # If no match found, log the issue and raise an exception
    print(f"Failed to find a close match for '{name}'")
    raise KeyError(f"Couldn't find country named '{name}'")


def _generate_url(territory: str, adm: Union[str, int]) -> str:
    iso3 = (
        str.upper(territory)
        if _is_valid_iso3_code(territory)
        else _get_iso3_from_name_or_iso2(territory)
    )
    if adm != -1:
        adm = _validate_adm(adm)
    else:
        adm = _get_smallest_adm(iso3)
    if not _is_valid_adm(iso3, adm):
        raise KeyError(
            f"ADM level '{adm}' doesn't exist for country '{territory}' ({iso3})"
        )
    return f"https://www.geoboundaries.org/api/current/gbOpen/{iso3}/{adm}/"


def get_adm_by_codes(iso3: str, adm_codes: List[int], adm_level: str, simplified=True) -> dict:
    """Get GeoJSON data for multiple ADM codes by filtering the full ADM level data."""
    print(f"Fetching full {adm_level} data for {iso3}...")
    full_data = _get_full_adm_data(iso3, adm_level, simplified)
    
    print(f"Filtering {len(full_data['features'])} features for {len(adm_codes)} ADM codes...")
    filtered_data = _filter_features_by_adm_codes(full_data, adm_codes, adm_level)
    
    if not filtered_data["features"]:
        raise ValueError(f"No matching ADM codes found for {iso3} at level {adm_level}")
    
    print(f"Found {len(filtered_data['features'])} matching features")
    return filtered_data


def _get_full_adm_data(iso3: str, adm_level: str, simplified: bool) -> dict:
    """Get the full GeoJSON data for an entire ADM level."""
    geom_complexity = "simplifiedGeometryGeoJSON" if simplified else "gjDownloadURL"
    try:
        # Get metadata for the entire ADM level
        metadata = get_metadata(iso3, adm_level)
        print(f"\n=== METADATA FOR {iso3} {adm_level} ===")
        for key, value in metadata.items():
            print(f"{key}: {value}")
        print(f"=== END METADATA ===\n")
        
        json_uri = metadata[geom_complexity]
        session = session_manager.get_session()
        response = session.get(json_uri)
        response.raise_for_status()
        return geojson.loads(response.text)
    except Exception as e:
        print(f"Error fetching full ADM data for {iso3} {adm_level}: {e}")
        raise


def _filter_features_by_adm_codes(feature_collection: dict, adm_codes: List[int], adm_level: str) -> dict:
    """Filter GeoJSON features to only include specific ADM codes."""
    filtered_features = []
    
    # Debug: Show sample of available properties
    print(f"\n=== DEBUGGING ADM CODES ===")
    print(f"Looking for ADM codes: {adm_codes}")
    print(f"Total features in data: {len(feature_collection['features'])}")
    
    # Show first few features' properties
    for i, feature in enumerate(feature_collection["features"][:5]):
        print(f"\nFeature {i+1} properties:")
        if "properties" in feature:
            for key, value in feature["properties"].items():
                print(f"  {key}: {value}")
        else:
            print("  No properties found")
    
    # Check if any features have properties that might contain our codes
    print(f"\n=== SEARCHING FOR MATCHING CODES ===")
    found_codes = set()
    for i, feature in enumerate(feature_collection["features"]):
        if "properties" in feature:
            for key, value in feature["properties"].items():
                # Try to convert to int and check if it matches any of our codes
                try:
                    if isinstance(value, str) and value.isdigit():
                        int_value = int(value)
                        if int_value in adm_codes:
                            print(f"Found code {int_value} in feature {i+1}, property '{key}': {value}")
                            found_codes.add(int_value)
                except (ValueError, TypeError):
                    continue
    
    print(f"Found codes: {sorted(list(found_codes))}")
    print(f"Missing codes: {sorted(list(set(adm_codes) - found_codes))}")
    
    for feature in feature_collection["features"]:
        # Extract ADM code from feature properties
        # The property name might vary, so we'll try common patterns
        adm_code = None
        
        # Try different possible property names for ADM codes
        possible_props = [
            f"shapeID",  # Common in geoBoundaries
            f"shapeid", 
            f"adm{adm_level[-1]}code",  # e.g., adm2code
            f"adm{adm_level[-1]}_code",
            f"code",
            f"id"
        ]
        
        if "properties" in feature:
            for prop in possible_props:
                if prop in feature["properties"]:
                    adm_code = feature["properties"][prop]
                    break
        
        # Convert to int for comparison
        try:
            if adm_code is not None:
                adm_code = int(adm_code)
                if adm_code in adm_codes:
                    filtered_features.append(feature)
                    print(f"Found matching ADM code: {adm_code}")
        except (ValueError, TypeError):
            continue
    
    print(f"=== END DEBUGGING ===\n")
    
    return {
        "type": "FeatureCollection",
        "features": filtered_features
    }


def get_metadata(territory: str, adm: Union[str, int]) -> dict:
    session = session_manager.get_session()
    url = _generate_url(territory, adm)
    response = session.get(url, verify=True)
    response.raise_for_status()  # Raises error for bad responses
    return response.json()


def _get_data(territory: str, adm: str, simplified: bool) -> dict:
    geom_complexity = "simplifiedGeometryGeoJSON" if simplified else "gjDownloadURL"
    try:
        json_uri = get_metadata(territory, adm)[geom_complexity]
        session = session_manager.get_session()
        response = session.get(json_uri)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(
            f"Error while requesting geoboundaries API\nURL: {json_uri}\nException: {e}"
        )
        raise


def get_adm(
    territories: Union[str, List[str]], adm: Union[str, int], simplified=True
) -> dict:
    if isinstance(territories, str):
        territories = [territories]
    geojson_features = [
        geojson.loads(_get_data(i, adm, simplified)) for i in territories
    ]
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            feature["features"][0] for feature in geojson_features
        ],  # Assuming each call returns a FeatureCollection with one feature
    }
    return feature_collection


def _calculate_bounding_box(feature_collection):
    """Calculate bounding box from GeoJSON FeatureCollection."""
    min_lat, max_lat = float('inf'), float('-inf')
    min_lon, max_lon = float('inf'), float('-inf')
    
    for feature in feature_collection["features"]:
        geometry = feature["geometry"]
        
        if geometry["type"] == "Polygon":
            coords = geometry["coordinates"][0]  # First ring of polygon
        elif geometry["type"] == "MultiPolygon":
            coords = []
            for polygon in geometry["coordinates"]:
                coords.extend(polygon[0])  # First ring of each polygon
        else:
            continue
            
        for coord in coords:
            lon, lat = coord
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)
    
    return {
        "min_lat": min_lat,
        "max_lat": max_lat,
        "min_lon": min_lon,
        "max_lon": max_lon
    }


# function to get area of interest for a place name-------------------------------------------------------
def get_area_of_interest(place_name, adm="ADM0"):
    """Retrieve the area of interest based on the place name."""
    geojson_data = get_adm(territories=place_name, adm=adm)
    return _calculate_bounding_box(geojson_data)


def get_area_of_interest_by_codes(adm_codes: List[int], adm_level: str, country_iso3: str, simplified=True):
    """Retrieve the area of interest based on ADM codes.
    
    Args:
        adm_codes: List of ADM codes (e.g., [4386, 4395, 4445])
        adm_level: ADM level (e.g., 'ADM1', 'ADM2')
        country_iso3: ISO3 country code (e.g., 'ARG' for Argentina)
        simplified: Whether to use simplified geometry (default: True)
    
    Returns:
        Dictionary with bounding box coordinates: {min_lat, max_lat, min_lon, max_lon}
    """
    geojson_data = get_adm_by_codes(country_iso3, adm_codes, adm_level, simplified)
    return _calculate_bounding_box(geojson_data)


def _filter_features_by_names(feature_collection: dict, unit_names: List[str], adm_level: str) -> dict:
    """Filter GeoJSON features to only include specific administrative unit names."""
    filtered_features = []
    
    print(f"\n=== SEARCHING BY NAMES ===")
    print(f"Looking for units: {unit_names}")
    print(f"Total features in data: {len(feature_collection['features'])}")
    
    # Get all available names for debugging
    available_names = []
    for feature in feature_collection["features"]:
        if "properties" in feature and "shapeName" in feature["properties"]:
            available_names.append(feature["properties"]["shapeName"])
    
    print(f"Sample of available names: {available_names[:10]}")
    
    for feature in feature_collection["features"]:
        if "properties" in feature and "shapeName" in feature["properties"]:
            feature_name = feature["properties"]["shapeName"]
            
            # Try exact match first
            if feature_name in unit_names:
                filtered_features.append(feature)
                print(f"Exact match found: {feature_name}")
                continue
            
            # Try case-insensitive match
            if feature_name.lower() in [name.lower() for name in unit_names]:
                filtered_features.append(feature)
                print(f"Case-insensitive match found: {feature_name}")
                continue
    
    print(f"Found {len(filtered_features)} matching features")
    print(f"=== END NAME SEARCH ===\n")
    
    return {
        "type": "FeatureCollection",
        "features": filtered_features
    }


def get_adm_by_names(iso3: str, unit_names: List[str], adm_level: str, simplified=True) -> dict:
    """Get GeoJSON data for multiple administrative units by name."""
    print(f"Fetching full {adm_level} data for {iso3}...")
    full_data = _get_full_adm_data(iso3, adm_level, simplified)
    
    print(f"Filtering {len(full_data['features'])} features for {len(unit_names)} unit names...")
    filtered_data = _filter_features_by_names(full_data, unit_names, adm_level)
    
    if not filtered_data["features"]:
        raise ValueError(f"No matching administrative units found for {iso3} at level {adm_level}")
    
    print(f"Found {len(filtered_data['features'])} matching features")
    return filtered_data


def get_area_of_interest_by_names(unit_names: List[str], adm_level: str, country_iso3: str, simplified=True):
    """Retrieve the area of interest based on administrative unit names.
    
    Args:
        unit_names: List of administrative unit names (e.g., ['La Plata', 'Buenos Aires'])
        adm_level: ADM level (e.g., 'ADM1', 'ADM2')
        country_iso3: ISO3 country code (e.g., 'ARG' for Argentina)
        simplified: Whether to use simplified geometry (default: True)
    
    Returns:
        Dictionary with bounding box coordinates: {min_lat, max_lat, min_lon, max_lon}
    """
    geojson_data = get_adm_by_names(country_iso3, unit_names, adm_level, simplified)
    return _calculate_bounding_box(geojson_data)


def list_available_units(country_iso3: str, adm_level: str, simplified=True, max_units=50):
    """List all available administrative unit names in a dataset.
    
    Args:
        country_iso3: ISO3 country code (e.g., 'ARG' for Argentina)
        adm_level: ADM level (e.g., 'ADM1', 'ADM2')
        simplified: Whether to use simplified geometry (default: True)
        max_units: Maximum number of units to display (default: 50)
    
    Returns:
        List of available unit names
    """
    print(f"Fetching {adm_level} data for {country_iso3}...")
    full_data = _get_full_adm_data(country_iso3, adm_level, simplified)
    
    unit_names = []
    for feature in full_data["features"]:
        if "properties" in feature and "shapeName" in feature["properties"]:
            unit_names.append(feature["properties"]["shapeName"])
    
    unit_names.sort()  # Sort alphabetically
    
    print(f"\n=== AVAILABLE {adm_level} UNITS FOR {country_iso3} ===")
    print(f"Total units: {len(unit_names)}")
    
    if len(unit_names) <= max_units:
        for i, name in enumerate(unit_names, 1):
            print(f"{i:3d}. {name}")
    else:
        print(f"Showing first {max_units} units:")
        for i, name in enumerate(unit_names[:max_units], 1):
            print(f"{i:3d}. {name}")
        print(f"... and {len(unit_names) - max_units} more")
    
    print(f"=== END LIST ===\n")
    
    return unit_names
