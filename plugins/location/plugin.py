# plugins/location/plugin.py
"""
Dedicated Location & Universal Geography Plugin for Jarvis V2.
"""

import logging
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from core.permissions import PermissionLevel
from .commands import ACTIONS, LocationCommands
from .resolver import LocationResolver

logger = logging.getLogger("jarvis.plugins.location")


class LocationPlugin(BasePlugin):
    """
    Dedicated Geography & Place Resolution Plugin providing local, deterministic,
    offline location information, hierarchical places, distance, and zero-API map routes.
    """

    def __init__(self, manifest=None, config=None, event_bus=None):
        super().__init__(manifest=manifest, config=config)
        self.event_bus = event_bus
        self.resolver = LocationResolver()
        self.commands = LocationCommands(resolver=self.resolver)

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="location",
            version="2.0.0",
            description="Universal offline location, country/city hierarchy, distance, and web map plugin.",
            author="Jarvis Team",
            permissions=[PermissionLevel.READ],
            actions=ACTIONS
        )

    def _open_or_focus_map(self, map_url: str, place_name: str) -> None:
        """
        Automatically focuses an existing browser tab if Google Maps with the same place is open,
        otherwise opens the location in Google Maps in the default browser.
        """
        import webbrowser
        try:
            from core.target_engine import UniversalTargetEngine, TargetRequest
            target_engine = UniversalTargetEngine()

            # 1. Check if a tab with the place name is already open
            matches_place = target_engine.resolver.resolve(TargetRequest(target=place_name, action="activate"))
            for cand in matches_place:
                if cand.browser or "map" in (cand.title or "").lower():
                    target_engine.executor.execute("activate_tab", cand)
                    return

            # 2. Check if a Google Maps tab is already showing this place
            matches_maps = target_engine.resolver.resolve(TargetRequest(target="Google Maps", action="activate"))
            for cand in matches_maps:
                if place_name.lower() in (cand.title or "").lower():
                    target_engine.executor.execute("activate_tab", cand)
                    return

            # 3. Otherwise open the generated Google Maps URL in the default browser
            webbrowser.open(map_url)
        except Exception as e:
            logger.debug(f"LocationPlugin: Auto map focus error, falling back to webbrowser.open: {e}")
            try:
                webbrowser.open(map_url)
            except Exception:
                pass

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None, **kwargs) -> PluginResult:
        """Executes the requested geographical action."""
        act_name = (action_name or kwargs.get("action", "")).lower().strip()
        params = parameters if parameters is not None else kwargs.get("parameters", kwargs)

        logger.info(f"LocationPlugin: Executing action '{act_name}' with params {params}")

        # 1. Location Info
        if act_name in ("location_info", "place_info", "where_is", "find_place"):
            place = params.get("place", "")
            res = self.commands.location_info(place=place)
            if res.get("success") and not res.get("needs_clarification"):
                map_url = res.get("map_url")
                place_name = (res.get("location") or {}).get("name") if isinstance(res.get("location"), dict) else place
                if map_url:
                    self._open_or_focus_map(map_url, place_name or place)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 2. Country Info
        elif act_name in ("country_info", "capital", "country"):
            country = params.get("country", "")
            res = self.commands.country_info(country=country)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 3. Distance
        elif act_name in ("distance", "calc_distance", "doori"):
            orig = params.get("origin", "")
            dest = params.get("destination", "")
            res = self.commands.distance(origin=orig, destination=dest)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 4. Directions / Route
        elif act_name in ("directions", "route", "rasta"):
            orig = params.get("origin", "")
            dest = params.get("destination", "")
            res = self.commands.directions(origin=orig, destination=dest)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 5. Open Map
        elif act_name in ("open_map", "map", "show_map", "naksha"):
            place = params.get("place", "")
            res = self.commands.open_map(place=place)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 6. Nearby Search
        elif act_name in ("nearby_search", "nearby", "near_me"):
            category = params.get("category", "restaurant")
            loc = params.get("location", "current location")
            res = self.commands.nearby_search(category=category, location=loc)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 7. Geocode Coordinates
        elif act_name in ("geocode_coordinates", "coordinates", "lat_long"):
            place = str(params.get("place", "")).strip()
            if not place:
                return PluginResult(success=False, error="Place parameter is required.")
            cleaned = self.resolver.clean_place_name(place)
            loc = self.resolver.db.find_location(cleaned)
            if not loc:
                return PluginResult(success=False, error=f"Could not resolve coordinates for '{place}'.")
            return PluginResult(
                success=True,
                data={
                    "place": loc.name,
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                    "country": loc.country_name,
                    "continent": loc.continent,
                    "timezone": loc.timezone,
                    "message": f"Coordinates for {loc.name}: {loc.latitude}° N, {loc.longitude}° E ({loc.country_name})."
                }
            )

        # 8. Reverse Geocode
        elif act_name in ("reverse_geocode", "nearest_city"):
            try:
                lat = float(params.get("latitude", 0))
                lon = float(params.get("longitude", 0))
            except (ValueError, TypeError):
                return PluginResult(success=False, error="Valid numeric latitude and longitude are required.")

            all_locs = self.resolver.db.get_all_locations()
            if not all_locs:
                return PluginResult(success=False, error="No location data available in database.")

            closest = None
            min_dist = float("inf")
            for loc in all_locs:
                if loc.latitude is not None and loc.longitude is not None:
                    d_km, _ = self.resolver.haversine_distance(lat, lon, loc.latitude, loc.longitude)
                    if d_km < min_dist:
                        min_dist = d_km
                        closest = loc

            if closest:
                return PluginResult(
                    success=True,
                    data={
                        "latitude": lat,
                        "longitude": lon,
                        "closest_place": closest.name,
                        "country": closest.country_name,
                        "distance_km": round(min_dist, 1),
                        "message": f"Nearest known location is {closest.name}, {closest.country_name} ({round(min_dist, 1)} km away)."
                    }
                )
            return PluginResult(success=False, error="Could not determine nearest location.")

        # 9. Get Timezone
        elif act_name in ("get_timezone", "timezone"):
            place = str(params.get("place", "")).strip()
            if not place:
                return PluginResult(success=False, error="Place parameter is required.")
            cleaned = self.resolver.clean_place_name(place)
            loc = self.resolver.db.find_location(cleaned)
            if not loc or not loc.timezone:
                return PluginResult(success=False, error=f"Timezone for '{place}' not found.")
            return PluginResult(
                success=True,
                data={
                    "place": loc.name,
                    "timezone": loc.timezone,
                    "country": loc.country_name,
                    "message": f"Timezone for {loc.name}, {loc.country_name}: {loc.timezone}."
                }
            )

        # 10. Calculate Bearing
        elif act_name in ("calculate_bearing", "bearing", "heading"):
            orig_name = str(params.get("origin", "")).strip()
            dest_name = str(params.get("destination", "")).strip()
            if not orig_name or not dest_name:
                return PluginResult(success=False, error="Both 'origin' and 'destination' are required.")

            loc1 = self.resolver.db.find_location(self.resolver.clean_place_name(orig_name))
            loc2 = self.resolver.db.find_location(self.resolver.clean_place_name(dest_name))
            if not loc1 or not loc2 or loc1.latitude is None or loc2.latitude is None:
                return PluginResult(success=False, error="Could not resolve coordinates for origin or destination.")

            import math
            dlon = math.radians(loc2.longitude - loc1.longitude)
            lat1_rad = math.radians(loc1.latitude)
            lat2_rad = math.radians(loc2.latitude)
            x = math.sin(dlon) * math.cos(lat2_rad)
            y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)
            bearing_rad = math.atan2(x, y)
            deg = (math.degrees(bearing_rad) + 360) % 360

            dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
            compass = dirs[int((deg + 11.25) / 22.5) % 16]

            return PluginResult(
                success=True,
                data={
                    "origin": loc1.name,
                    "destination": loc2.name,
                    "bearing_degrees": round(deg, 1),
                    "compass_direction": compass,
                    "message": f"Bearing from {loc1.name} to {loc2.name} is {round(deg, 1)}° ({compass})."
                }
            )

        # 11. Get Midpoint
        elif act_name in ("get_midpoint", "midpoint"):
            orig_name = str(params.get("origin", "")).strip()
            dest_name = str(params.get("destination", "")).strip()
            if not orig_name or not dest_name:
                return PluginResult(success=False, error="Both 'origin' and 'destination' are required.")

            loc1 = self.resolver.db.find_location(self.resolver.clean_place_name(orig_name))
            loc2 = self.resolver.db.find_location(self.resolver.clean_place_name(dest_name))
            if not loc1 or not loc2 or loc1.latitude is None or loc2.latitude is None:
                return PluginResult(success=False, error="Could not resolve coordinates for origin or destination.")

            mid_lat = round((loc1.latitude + loc2.latitude) / 2.0, 4)
            mid_lon = round((loc1.longitude + loc2.longitude) / 2.0, 4)

            return PluginResult(
                success=True,
                data={
                    "origin": loc1.name,
                    "destination": loc2.name,
                    "midpoint_latitude": mid_lat,
                    "midpoint_longitude": mid_lon,
                    "message": f"Geographic midpoint between {loc1.name} and {loc2.name}: {mid_lat}° N, {mid_lon}° E."
                }
            )

        # 12. Estimate Flight Time
        elif act_name in ("estimate_flight_time", "flight_time"):
            orig_name = str(params.get("origin", "")).strip()
            dest_name = str(params.get("destination", "")).strip()
            if not orig_name or not dest_name:
                return PluginResult(success=False, error="Both 'origin' and 'destination' are required.")

            loc1 = self.resolver.db.find_location(self.resolver.clean_place_name(orig_name))
            loc2 = self.resolver.db.find_location(self.resolver.clean_place_name(dest_name))
            if not loc1 or not loc2 or loc1.latitude is None or loc2.latitude is None:
                return PluginResult(success=False, error="Could not resolve coordinates for origin or destination.")

            d_km, d_miles = self.resolver.haversine_distance(loc1.latitude, loc1.longitude, loc2.latitude, loc2.longitude)
            # 850 km/h cruising + 0.5 hours taxi/takeoff/landing
            flight_hours = (d_km / 850.0) + 0.5
            h = int(flight_hours)
            m = int((flight_hours - h) * 60)
            flight_str = f"{h}h {m}m" if h > 0 else f"{m} mins"

            return PluginResult(
                success=True,
                data={
                    "origin": loc1.name,
                    "destination": loc2.name,
                    "distance_km": round(d_km, 1),
                    "estimated_flight_duration": flight_str,
                    "message": f"Estimated non-stop flight from {loc1.name} to {loc2.name} ({round(d_km):,} km): approx {flight_str}."
                }
            )

        # 13. Country Neighbors
        elif act_name in ("get_country_neighbors", "neighbors", "borders"):
            country = str(params.get("country", "")).strip().lower()
            if not country:
                return PluginResult(success=False, error="Country parameter is required.")

            country_borders = {
                "india": ["Pakistan", "China", "Nepal", "Bhutan", "Bangladesh", "Myanmar"],
                "bharat": ["Pakistan", "China", "Nepal", "Bhutan", "Bangladesh", "Myanmar"],
                "united states of america": ["Canada", "Mexico"],
                "united states": ["Canada", "Mexico"],
                "usa": ["Canada", "Mexico"],
                "united kingdom": ["Ireland"],
                "uk": ["Ireland"],
                "france": ["Germany", "Italy", "Spain", "Switzerland", "Belgium", "Luxembourg", "Monaco", "Andorra"],
                "germany": ["France", "Poland", "Czech Republic", "Austria", "Switzerland", "Denmark", "Netherlands", "Belgium", "Luxembourg"],
                "japan": ["Maritime borders with Russia, South Korea, China, Taiwan"],
                "china": ["India", "Russia", "Mongolia", "Kazakhstan", "Pakistan", "Nepal", "Bhutan", "Myanmar", "Laos", "Vietnam", "North Korea"]
            }
            borders = country_borders.get(country, ["No immediate land borders recorded or island nation."])
            loc = self.resolver.db.find_location(country)

            return PluginResult(
                success=True,
                data={
                    "country": loc.name if loc else country.title(),
                    "neighbors": borders,
                    "count": len(borders),
                    "message": f"Bordering neighbors of {loc.name if loc else country.title()}: {', '.join(borders)}."
                }
            )

        # 14. List Cities in Country
        elif act_name in ("list_cities_in_country", "cities_in_country", "cities"):
            country = str(params.get("country", "")).strip()
            if not country:
                return PluginResult(success=False, error="Country parameter is required.")

            locations = self.resolver.db.find_by_country(country)
            cities = [
                {
                    "name": l.name,
                    "state": l.state_name,
                    "type": l.place_type.value if hasattr(l.place_type, "value") else str(l.place_type),
                    "latitude": l.latitude,
                    "longitude": l.longitude
                }
                for l in locations if l.latitude is not None
            ]

            return PluginResult(
                success=True,
                data={
                    "country": country,
                    "cities": cities,
                    "count": len(cities),
                    "message": f"Found {len(cities)} registered place(s) in {country.title()}."
                }
            )

        # 15. IP Geolocation
        elif act_name in ("get_ip_geolocation", "ip_location"):
            try:
                import json
                from urllib.request import Request, urlopen
                req = Request("https://ipinfo.io/json", headers={"User-Agent": "Jarvis-Location/2.1"})
                with urlopen(req, timeout=5) as resp:
                    geo_info = json.loads(resp.read().decode("utf-8"))
                return PluginResult(
                    success=True,
                    data={
                        "ip": geo_info.get("ip"),
                        "city": geo_info.get("city"),
                        "region": geo_info.get("region"),
                        "country": geo_info.get("country"),
                        "loc": geo_info.get("loc"),
                        "org": geo_info.get("org"),
                        "message": f"Device IP location: {geo_info.get('city')}, {geo_info.get('region')} ({geo_info.get('country')})."
                    }
                )
            except Exception as e:
                # Fallback to local default
                return PluginResult(
                    success=True,
                    data={
                        "city": "New Delhi",
                        "country": "India",
                        "offline_fallback": True,
                        "message": f"Network offline ({e}), defaulting to system regional baseline: New Delhi, India."
                    }
                )

        # 16. Find Places Within Radius
        elif act_name in ("find_places_within_radius", "places_near"):
            place = str(params.get("place", "")).strip()
            radius_km = float(params.get("radius_km", 200.0))
            if not place:
                return PluginResult(success=False, error="Place parameter is required.")

            center_loc = self.resolver.db.find_location(self.resolver.clean_place_name(place))
            if not center_loc or center_loc.latitude is None:
                return PluginResult(success=False, error=f"Could not resolve center location '{place}'.")

            all_locs = self.resolver.db.get_all_locations()
            matched = []
            for loc in all_locs:
                if loc.name.lower() != center_loc.name.lower() and loc.latitude is not None:
                    d_km, _ = self.resolver.haversine_distance(center_loc.latitude, center_loc.longitude, loc.latitude, loc.longitude)
                    if d_km <= radius_km:
                        matched.append({
                            "name": loc.name,
                            "country": loc.country_name,
                            "distance_km": round(d_km, 1)
                        })

            matched.sort(key=lambda x: x["distance_km"])
            return PluginResult(
                success=True,
                data={
                    "center": center_loc.name,
                    "radius_km": radius_km,
                    "places": matched,
                    "count": len(matched),
                    "message": f"Found {len(matched)} place(s) within {radius_km} km of {center_loc.name}."
                }
            )

        return PluginResult(
            success=False,
            error=f"Unsupported location action '{act_name}'"
        )
