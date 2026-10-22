# plugins/location/commands.py
"""
Command actions and handlers for the Location & Geography Plugin.
"""

from typing import Any, Dict, List, Optional
from core.permissions import PermissionLevel
from plugins.manifest import PluginAction, PluginParameter
from .models import LocationQueryResult
from .resolver import LocationResolver

ACTIONS = [
    PluginAction(
        name="location_info",
        description="Provides geographic information, coordinates, and details about a city, landmark, or place",
        keywords=["location", "kaha hai", "kahan hai", "where is", "place info", "sthit hai"],
        parameters=[
            PluginParameter(name="place", type="string", description="Name of the city, country, or landmark", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="country_info",
        description="Provides detailed information about a country (capital, continent, states count, currency)",
        keywords=["country info", "capital", "rajdhani", "currency", "desh"],
        parameters=[
            PluginParameter(name="country", type="string", description="Country name", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="distance",
        description="Calculates geographic distance and travel time between two places",
        keywords=["distance", "doori", "kitna door", "distance between"],
        parameters=[
            PluginParameter(name="origin", type="string", description="Starting place", required=True),
            PluginParameter(name="destination", type="string", description="Destination place", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="directions",
        description="Opens route and driving/transit directions between two locations in browser",
        keywords=["directions", "rasta", "route", "directions to", "directions from"],
        parameters=[
            PluginParameter(name="origin", type="string", description="Starting location", required=True),
            PluginParameter(name="destination", type="string", description="Destination location", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="open_map",
        description="Opens interactive map of a place or address in browser",
        keywords=["map", "map dikhao", "show map", "open map", "naksha"],
        parameters=[
            PluginParameter(name="place", type="string", description="Place or city name to show on map", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="nearby_search",
        description="Searches nearby points of interest (restaurants, hospitals, ATMs, gas stations)",
        keywords=["nearby", "mere paas", "nearest", "pass mein", "dhoondo"],
        parameters=[
            PluginParameter(name="category", type="string", description="Type of place (restaurant, hospital, atm)", required=True),
            PluginParameter(name="location", type="string", description="Reference location (optional)", required=False, default="current location")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="geocode_coordinates",
        description="Returns geographic coordinates (latitude and longitude) for a named location",
        keywords=["coordinates", "lat long", "latitude", "longitude", "geocode"],
        parameters=[
            PluginParameter(name="place", type="string", description="Name of the place or city", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="reverse_geocode",
        description="Finds the nearest known city or landmark for given GPS coordinates",
        keywords=["reverse geocode", "coordinates to city", "where is this point"],
        parameters=[
            PluginParameter(name="latitude", type="float", description="Latitude coordinate", required=True),
            PluginParameter(name="longitude", type="float", description="Longitude coordinate", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="get_timezone",
        description="Returns the local timezone and UTC offset for a specified location",
        keywords=["timezone", "time zone", "local time of city", "samay"],
        parameters=[
            PluginParameter(name="place", type="string", description="Place name", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="calculate_bearing",
        description="Calculates compass bearing (heading direction) between two places",
        keywords=["bearing", "compass heading", "direction angle", "which direction"],
        parameters=[
            PluginParameter(name="origin", type="string", description="Starting place", required=True),
            PluginParameter(name="destination", type="string", description="Destination place", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="get_midpoint",
        description="Computes the exact geographic midpoint halfway between two locations",
        keywords=["midpoint", "halfway point", "beech ka rasta", "center coordinate"],
        parameters=[
            PluginParameter(name="origin", type="string", description="First place", required=True),
            PluginParameter(name="destination", type="string", description="Second place", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="estimate_flight_time",
        description="Estimates flight duration and flight distance between two cities",
        keywords=["flight time", "flight duration", "air travel time", "plane time"],
        parameters=[
            PluginParameter(name="origin", type="string", description="Departure city", required=True),
            PluginParameter(name="destination", type="string", description="Arrival city", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="get_country_neighbors",
        description="Lists bordering countries and regional clusters for a given nation",
        keywords=["neighboring countries", "borders of country", "padosi desh"],
        parameters=[
            PluginParameter(name="country", type="string", description="Country name", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="list_cities_in_country",
        description="Lists known major cities and locations in a country or state",
        keywords=["cities in country", "list cities", "major cities of"],
        parameters=[
            PluginParameter(name="country", type="string", description="Country name", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="get_ip_geolocation",
        description="Estimates the current device's geographic location via IP address",
        keywords=["ip location", "current location by ip", "where am i"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="find_places_within_radius",
        description="Finds all known cities and landmarks within a specified radius (km) of a place",
        keywords=["places within radius", "nearby cities", "cities near"],
        parameters=[
            PluginParameter(name="place", type="string", description="Center place", required=True),
            PluginParameter(name="radius_km", type="float", description="Search radius in kilometers", required=False, default=200.0)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    )
]


class LocationCommands:
    """Executable command handlers for the Location subsystem."""

    def __init__(self, resolver: Optional[LocationResolver] = None):
        self.resolver = resolver or LocationResolver()

    def location_info(self, place: str) -> Dict[str, Any]:
        res: LocationQueryResult = self.resolver.get_location_info(place)
        return res.to_dict()

    def country_info(self, country: str) -> Dict[str, Any]:
        res: LocationQueryResult = self.resolver.get_country_info(country)
        return res.to_dict()

    def distance(self, origin: str, destination: str) -> Dict[str, Any]:
        res: LocationQueryResult = self.resolver.calculate_distance(origin, destination)
        return res.to_dict()

    def directions(self, origin: str, destination: str) -> Dict[str, Any]:
        res: LocationQueryResult = self.resolver.open_directions_in_browser(origin, destination)
        return res.to_dict()

    def open_map(self, place: str) -> Dict[str, Any]:
        res: LocationQueryResult = self.resolver.open_map_in_browser(place)
        return res.to_dict()

    def nearby_search(self, category: str, location: str = "current location") -> Dict[str, Any]:
        res: LocationQueryResult = self.resolver.search_nearby(category, location)
        return res.to_dict()
