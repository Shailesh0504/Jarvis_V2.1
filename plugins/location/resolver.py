# plugins/location/resolver.py
"""
Universal Location & Geography Resolution Engine for Jarvis V2.
Calculates spherical distances, generates zero-API map URLs, and resolves geographic hierarchies.
"""

import logging
import math
import re
import urllib.parse
import webbrowser
from typing import Any, Dict, List, Optional, Tuple

from .database import LocationDatabase
from .models import GeoDistanceResult, GeoLocation, LocationQueryResult, PlaceType

logger = logging.getLogger("jarvis.plugins.location.resolver")


class LocationResolver:
    """Universal place/entity resolver and geographic calculation engine."""

    EARTH_RADIUS_KM = 6371.0
    KM_TO_MILES = 0.621371

    def __init__(self, db: Optional[LocationDatabase] = None):
        self.db = db or LocationDatabase()

    def clean_place_name(self, text: str) -> str:
        """Strips Hindi/English query particles and question marks from place name."""
        if not text:
            return ""
        s = text.strip()
        # Remove question marks, punctuation
        s = re.sub(r'[\?\.\,\!]', '', s)
        # Remove Hindi/English connectors: "se", "ko", "mein", "ka", "ki", "ke", "to", "from", "near"
        s = re.sub(r'^(?:where\s+is|kaha\s+hai|kahan\s+hai|location\s+of|distance\s+between|map\s+of|directions\s+to|directions\s+from|from|to|se|ko|in|near)\s+', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\s+(?:kaha\s+hai|kahan\s+hai|mein\s+hai|me\s+hai|mein|me|ka\s+map|directions|dikhao|batao|hai)$', '', s, flags=re.IGNORECASE)
        return s.strip()

    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
        """Calculates great-circle distance between two points in km and miles."""
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2.0) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2.0) ** 2)
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        km = self.EARTH_RADIUS_KM * c
        miles = km * self.KM_TO_MILES
        return km, miles

    def estimate_travel_time(self, distance_km: float) -> str:
        """Estimates approximate driving travel time based on average speed."""
        if distance_km <= 0:
            return "0 mins"
        hours = distance_km / 75.0 # Average highway drive speed
        if hours < 1.0:
            mins = int(hours * 60)
            return f"approx {mins} minutes"
        h = int(hours)
        m = int((hours - h) * 60)
        return f"approx {h} hours {m} mins"

    def get_map_url(self, query: str) -> str:
        """Generates zero-API web map URL for viewing a place."""
        encoded = urllib.parse.quote(query.strip())
        return f"https://www.google.com/maps/search/?api=1&query={encoded}"

    def get_directions_url(self, origin: str, destination: str) -> str:
        """Generates zero-API web directions URL."""
        enc_orig = urllib.parse.quote(origin.strip())
        enc_dest = urllib.parse.quote(destination.strip())
        return f"https://www.google.com/maps/dir/?api=1&origin={enc_orig}&destination={enc_dest}"

    def get_location_info(self, place_name: str) -> LocationQueryResult:
        """Resolves location details into a short, natural spoken answer and map search URL."""
        cleaned = self.clean_place_name(place_name)
        lower_q = cleaned.lower()

        # 1. Ambiguous locations requiring clarification before map action
        if lower_q == "washington":
            return LocationQueryResult(
                success=True,
                action="location_info",
                formatted_answer="Aap Washington, D.C. ki baat kar rahe hain ya Washington State ki?",
                needs_clarification=True
            )

        loc = self.db.find_location(cleaned)

        if not loc:
            map_url = self.get_map_url(cleaned)
            return LocationQueryResult(
                success=True,
                action="location_info",
                formatted_answer=f"{cleaned.capitalize()} ki location main map par dikha raha hoon, Boss.",
                map_url=map_url
            )

        # 2. Conversational spoken responses for common cities/places
        spoken_answers = {
            "mumbai": "Mumbai Maharashtra mein hai, India ke west coast par. Ye Maharashtra ki capital city hai. Main aapko map par bhi dikha raha hoon, Boss.",
            "pune": "Pune Maharashtra mein hai, Mumbai ke southeast mein. Main map par bhi dikha raha hoon, Boss.",
            "delhi": "Delhi India ka National Capital Territory hai, north India mein sthit hai. Main map par bhi dikha raha hoon, Boss.",
            "goa": "Goa India ke southwest coast par ek state hai, Arabian Sea ke kinare. Main map par bhi dikha raha hoon, Boss.",
            "bangalore": "Bangalore Karnataka ki capital city hai, India ke southern part mein IT hub hai. Main map par bhi dikha raha hoon, Boss.",
            "kolkata": "Kolkata West Bengal ki capital city hai, East India mein sthit hai. Main map par bhi dikha raha hoon, Boss.",
            "chennai": "Chennai Tamil Nadu ki capital city hai, South India ke Coromandel Coast par sthit hai. Main map par bhi dikha raha hoon, Boss.",
            "hyderabad": "Hyderabad Telangana ki capital city hai, South India mein sthit hai. Main map par bhi dikha raha hoon, Boss.",
            "jaipur": "Jaipur Rajasthan ki capital city hai, jise Pink City bhi kaha jata hai. Main map par bhi dikha raha hoon, Boss.",
            "ahmedabad": "Ahmedabad Gujarat ka sabse bada city hai, Sabarmati river ke kinare. Main map par bhi dikha raha hoon, Boss.",
            "london": "London United Kingdom ki capital city hai, Europe ke River Thames ke kinare sthit hai. Main map par bhi dikha raha hoon, Boss.",
            "paris": "Paris France ki capital city hai, Western Europe mein sthit hai. Main map par bhi dikha raha hoon, Boss.",
            "tokyo": "Tokyo Japan ki capital city hai, East Asia mein sthit hai. Main map par bhi dikha raha hoon, Boss.",
            "new york": "New York USA ke east coast par ek major global city hai. Main map par bhi dikha raha hoon, Boss.",
            "mount everest": "Mount Everest Himalayas mein Nepal aur China ke border par sthit duniya ki sabse unchi peak hai. Main map par bhi dikha raha hoon, Boss.",
            "taj mahal": "Taj Mahal Uttar Pradesh ke Agra mein Yamuna river ke kinare sthit hai. Main map par bhi dikha raha hoon, Boss."
        }

        ans = spoken_answers.get(loc.name.lower())
        if not ans:
            if loc.place_type == PlaceType.CITY:
                state_part = f"{loc.state_name}, " if loc.state_name else ""
                ans = f"{loc.name} {state_part}{loc.country_name} mein hai. Main map par bhi dikha raha hoon, Boss."
            elif loc.place_type == PlaceType.STATE:
                ans = f"{loc.name} {loc.country_name} ka ek state hai. Main map par bhi dikha raha hoon, Boss."
            elif loc.place_type == PlaceType.COUNTRY:
                ans = f"{loc.name} {loc.continent} mein sthit ek desh hai. Main map par bhi dikha raha hoon, Boss."
            else:
                loc_part = loc.state_name or loc.country_name
                ans = f"{loc.name} {loc_part} mein sthit hai. Main map par bhi dikha raha hoon, Boss."

        map_query = f"{loc.name}, {loc.country_name}" if loc.country_name else loc.name
        map_url = self.get_map_url(map_query)

        return LocationQueryResult(
            success=True,
            action="location_info",
            formatted_answer=ans,
            location=loc,
            map_url=map_url
        )

    def get_country_info(self, country_name: str) -> LocationQueryResult:
        """Resolves country-specific information (capital, continent, states count, currency)."""
        cleaned = self.clean_place_name(country_name)
        loc = self.db.find_location(cleaned)

        if loc and loc.place_type == PlaceType.COUNTRY:
            extra = loc.extra_info
            cap = loc.capital or "N/A"
            states_info = f"{extra.get('states_count', 'N/A')} states" if "states_count" in extra else ""
            curr = extra.get("currency", "N/A")

            lines = [
                f"🌍 **{loc.name}**",
                f"• Capital: {cap}",
                f"• Continent: {loc.continent}",
            ]
            if states_info:
                lines.append(f"• States: {states_info}")
            if curr != "N/A":
                lines.append(f"• Currency: {curr}")
            if loc.timezone:
                lines.append(f"• Timezone: {loc.timezone}")
            if loc.description:
                lines.append(f"• Overview: {loc.description}")

            return LocationQueryResult(
                success=True,
                action="country_info",
                formatted_answer="\n".join(lines),
                location=loc,
                map_url=self.get_map_url(loc.name)
            )

        # Fallback if specific city/country
        return self.get_location_info(cleaned)

    def calculate_distance(self, origin: str, destination: str) -> LocationQueryResult:
        """Calculates distance between two places and generates map route link."""
        orig_clean = self.clean_place_name(origin)
        dest_clean = self.clean_place_name(destination)

        loc1 = self.db.find_location(orig_clean)
        loc2 = self.db.find_location(dest_clean)

        map_url = self.get_directions_url(orig_clean, dest_clean)

        if loc1 and loc2 and loc1.latitude and loc1.longitude and loc2.latitude and loc2.longitude:
            km, miles = self.haversine_distance(loc1.latitude, loc1.longitude, loc2.latitude, loc2.longitude)
            drive_time = self.estimate_travel_time(km)
            dist_res = GeoDistanceResult(
                origin=loc1.name,
                destination=loc2.name,
                distance_km=km,
                distance_miles=miles,
                estimated_drive_time=drive_time,
                map_url=self.get_map_url(f"{loc1.name} to {loc2.name}"),
                directions_url=map_url
            )
            ans = (
                f"📏 **Distance from {loc1.name} to {loc2.name}**:\n"
                f"• Straight-line Distance: **{round(km, 1)} km** ({round(miles, 1)} miles)\n"
                f"• Approximate Driving Time: **{drive_time}**\n"
                f"🔗 Live Route & Directions: {map_url}"
            )
            return LocationQueryResult(
                success=True,
                action="distance",
                formatted_answer=ans,
                distance_info=dist_res,
                map_url=map_url
            )
        else:
            ans = f"{orig_clean} se {dest_clean} ke beech directions aur distance dekhne ke liye:\n🔗 {map_url}"
            return LocationQueryResult(
                success=True,
                action="distance",
                formatted_answer=ans,
                map_url=map_url
            )

    def open_map_in_browser(self, place_name: str) -> LocationQueryResult:
        """Opens map for the place directly in default browser."""
        cleaned = self.clean_place_name(place_name)
        url = self.get_map_url(cleaned)
        try:
            webbrowser.open(url)
            ans = f"Opening map for '{cleaned}' in your browser: {url}"
        except Exception as e:
            ans = f"Map URL: {url}"

        return LocationQueryResult(
            success=True,
            action="open_map",
            formatted_answer=ans,
            map_url=url
        )

    def open_directions_in_browser(self, origin: str, destination: str) -> LocationQueryResult:
        """Opens directions between origin and destination in default browser."""
        orig_clean = self.clean_place_name(origin)
        dest_clean = self.clean_place_name(destination)
        url = self.get_directions_url(orig_clean, dest_clean)
        try:
            webbrowser.open(url)
            ans = f"Opening directions from '{orig_clean}' to '{dest_clean}' in your browser: {url}"
        except Exception as e:
            ans = f"Directions URL: {url}"

        return LocationQueryResult(
            success=True,
            action="directions",
            formatted_answer=ans,
            map_url=url
        )

    def search_nearby(self, category: str, location: str = "current location") -> LocationQueryResult:
        """Searches nearby POIs (restaurants, hospitals, ATMs) via zero-API map search."""
        cat_clean = category.strip()
        loc_clean = self.clean_place_name(location) if location and location != "current location" else ""
        query_str = f"{cat_clean} near {loc_clean}" if loc_clean else f"{cat_clean} near me"
        url = self.get_map_url(query_str)
        try:
            webbrowser.open(url)
            ans = f"Searching nearby {cat_clean} in your browser: {url}"
        except Exception:
            ans = f"Nearby {cat_clean} Search URL: {url}"

        return LocationQueryResult(
            success=True,
            action="nearby_search",
            formatted_answer=ans,
            map_url=url
        )
