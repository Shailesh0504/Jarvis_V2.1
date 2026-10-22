# tests/test_plugin_location.py
"""Tests for LocationPlugin covering original and newly added actions."""

import pytest
from plugins.location.plugin import LocationPlugin


@pytest.fixture
def plugin():
    p = LocationPlugin()
    p.initialize()
    return p


def test_location_manifest(plugin):
    manifest = plugin.get_manifest()
    assert manifest.name == "location"
    action_names = {a.name for a in manifest.actions}
    expected = {
        "location_info",
        "country_info",
        "distance",
        "directions",
        "open_map",
        "nearby_search",
        "geocode_coordinates",
        "reverse_geocode",
        "get_timezone",
        "calculate_bearing",
        "get_midpoint",
        "estimate_flight_time",
        "get_country_neighbors",
        "list_cities_in_country",
        "get_ip_geolocation",
        "find_places_within_radius"
    }
    assert expected.issubset(action_names)


def test_location_original_features(plugin):
    # Country info
    res_country = plugin.execute("country_info", {"country": "India"})
    assert res_country.success is True
    assert "India" in res_country.data.get("formatted_answer", "")

    # Distance
    res_dist = plugin.execute("distance", {"origin": "Delhi", "destination": "Mumbai"})
    assert res_dist.success is True
    assert "km" in res_dist.data.get("formatted_answer", "").lower()

    # Nearby search
    res_near = plugin.execute("nearby_search", {"category": "hospital", "location": "Delhi"})
    assert res_near.success is True


def test_location_geocode_and_reverse(plugin):
    # Geocode
    res_geo = plugin.execute("geocode_coordinates", {"place": "Tokyo"})
    assert res_geo.success is True
    assert res_geo.data["latitude"] is not None
    assert res_geo.data["longitude"] is not None
    assert res_geo.data["country"] == "Japan"

    # Reverse geocode
    res_rev = plugin.execute("reverse_geocode", {"latitude": 28.6139, "longitude": 77.2090})
    assert res_rev.success is True
    assert "New Delhi" in res_rev.data["closest_place"] or "Delhi" in res_rev.data["closest_place"]
    assert res_rev.data["distance_km"] < 50


def test_location_timezone_and_bearing_and_midpoint(plugin):
    # Timezone
    res_tz = plugin.execute("get_timezone", {"place": "Paris"})
    assert res_tz.success is True
    assert "Europe/Paris" in res_tz.data["timezone"] or "CET" in res_tz.data["timezone"]

    # Bearing
    res_bearing = plugin.execute("calculate_bearing", {"origin": "New Delhi", "destination": "Mumbai"})
    assert res_bearing.success is True
    assert "bearing_degrees" in res_bearing.data
    assert "compass_direction" in res_bearing.data

    # Midpoint
    res_mid = plugin.execute("get_midpoint", {"origin": "London", "destination": "Paris"})
    assert res_mid.success is True
    assert "midpoint_latitude" in res_mid.data
    assert "midpoint_longitude" in res_mid.data


def test_location_flight_and_neighbors_and_radius(plugin):
    # Flight time
    res_flight = plugin.execute("estimate_flight_time", {"origin": "London", "destination": "Tokyo"})
    assert res_flight.success is True
    assert "estimated_flight_duration" in res_flight.data
    assert res_flight.data["distance_km"] > 5000

    # Country neighbors
    res_neigh = plugin.execute("get_country_neighbors", {"country": "India"})
    assert res_neigh.success is True
    assert "Nepal" in res_neigh.data["neighbors"]

    # List cities
    res_cities = plugin.execute("list_cities_in_country", {"country": "India"})
    assert res_cities.success is True
    assert res_cities.data["count"] > 0

    # Find places within radius
    res_radius = plugin.execute("find_places_within_radius", {"place": "New Delhi", "radius_km": 500})
    assert res_radius.success is True
    assert res_radius.data["count"] >= 1

    # IP Geolocation (with guaranteed offline fallback)
    res_ip = plugin.execute("get_ip_geolocation", {})
    assert res_ip.success is True
    assert "city" in res_ip.data
