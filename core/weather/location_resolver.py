# core/weather/location_resolver.py
"""Location resolution hierarchy and conversation location memory for Weather Engine."""

import json
import logging
from pathlib import Path
import re
import threading
import time
from typing import Dict, List, Optional, Tuple
import urllib.request

from core.weather.models import WeatherLocation

logger = logging.getLogger("jarvis.weather.location")

DEFAULT_DEVICE_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "device_location_cache.json"

COMMON_CITIES = {
    "delhi", "new delhi", "mumbai", "bombay", "pune", "panvel", "bangalore", "bengaluru",
    "kolkata", "calcutta", "chennai", "madras", "hyderabad", "jaipur", "ahmedabad",
    "lucknow", "chandigarh", "shimla", "manali", "dehradun", "patna", "bhopal",
    "indore", "surat", "nagpur", "goa", "panaji", "varanasi", "agra", "kanpur",
    "amritsar", "srinagar", "jammu", "ranchi", "raipur", "guwahati", "bhubaneswar",
    "kochi", "cochin", "thiruvananthapuram", "trivandrum", "coimbatore", "mysore",
    "noida", "gurugram", "gurgaon", "faridabad", "ghaziabad", "thane", "navi mumbai",
    "london", "new york", "tokyo", "paris", "dubai", "singapore", "sydney",
    "toronto", "berlin", "moscow", "san francisco", "chicago", "los angeles",
    "seattle", "boston", "washington"
}

CITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "bombay": (19.0760, 72.8777),
    "bangalore": (12.9716, 77.5946),
    "bengaluru": (12.9716, 77.5946),
    "kolkata": (22.5726, 88.3639),
    "calcutta": (22.5726, 88.3639),
    "chennai": (13.0827, 80.2707),
    "madras": (13.0827, 80.2707),
    "hyderabad": (17.3850, 78.4867),
    "pune": (18.5204, 73.8567),
    "ahmedabad": (23.0225, 72.5714),
    "jaipur": (26.9124, 75.7873),
    "lucknow": (26.8467, 80.9462),
    "chandigarh": (30.7333, 76.7794),
    "bhopal": (23.2599, 77.4126),
    "indore": (22.7196, 75.8577),
    "patna": (25.5941, 85.1376),
    "nagpur": (21.1458, 79.0882),
    "surat": (21.1702, 72.8311),
    "varanasi": (25.3176, 82.9739),
    "agra": (27.1767, 78.0081),
    "kanpur": (26.4499, 80.3319),
    "shimla": (31.1048, 77.1734),
    "dehradun": (30.3165, 78.0322),
    "amritsar": (31.6340, 74.8723),
    "srinagar": (34.0837, 74.7973),
    "jammu": (32.7266, 74.8570),
    "ranchi": (23.3441, 85.3096),
    "raipur": (21.2514, 81.6296),
    "guwahati": (26.1445, 91.7362),
    "bhubaneswar": (20.2961, 85.8245),
    "kochi": (9.9312, 76.2673),
    "cochin": (9.9312, 76.2673),
    "thiruvananthapuram": (8.5241, 76.9366),
    "coimbatore": (11.0168, 76.9558),
    "mysore": (12.2958, 76.6394),
    "noida": (28.5355, 77.3910),
    "gurugram": (28.4595, 77.0266),
    "gurgaon": (28.4595, 77.0266),
    "faridabad": (28.4089, 77.3178),
    "ghaziabad": (28.6692, 77.4538),
    "thane": (19.2183, 72.9781),
    "goa": (15.2993, 74.1240),
    "london": (51.5074, -0.1278),
    "new york": (40.7128, -74.0060),
    "tokyo": (35.6762, 139.6503),
    "paris": (48.8566, 2.3522),
    "dubai": (25.2048, 55.2708),
    "singapore": (1.3521, 103.8198),
    "sydney": (-33.8688, 151.2093),
    "toronto": (43.6532, -79.3832),
    "berlin": (52.5200, 13.4050),
    "moscow": (55.7558, 37.6173),
    "san francisco": (37.7749, -122.4194),
    "chicago": (41.8781, -87.6298),
    "los angeles": (34.0522, -118.2437),
}

LOCAL_AREA_CUES = [
    "mere yahan", "mere yaha", "mera yahan", "mere area", "hamare yahan", "hamare yaha",
    "apne yahan", "here", "my location", "current location", "local weather", "locally"
]


class WeatherLocationResolver:
    """
    Resolves location based on strict hierarchical priority:
    1. Local area cues ("mere yahan", "my area") -> current device location
    2. Explicit location in user query ("Mumbai ka weather")
    3. Active conversation context location ("aur kal ka?")
    4. Current device/network geolocation (Rule 32 API-free discovery)
    5. Configured default location (system baseline fallback)
    6. Prompt user clarification when ambiguous
    """

    def __init__(
        self,
        default_city: str = "Delhi",
        context_ttl_seconds: float = 900.0,
        enable_device_location: bool = True,
        cache_file: Optional[Path] = None,
        device_location_ttl: float = 3600.0,
    ):
        self.default_city = default_city
        self.context_ttl = context_ttl_seconds
        self.enable_device_location = enable_device_location
        self.cache_file = cache_file or DEFAULT_DEVICE_CACHE_PATH
        self.device_location_ttl = device_location_ttl

        self._last_location: Optional[str] = None
        self._last_timestamp: float = 0.0

        self._cached_device_loc: Optional[WeatherLocation] = None
        self._device_loc_timestamp: float = 0.0
        self._lock = threading.Lock()

        # Load persisted device location from disk on startup if available
        self._load_cached_device_location()

    def update_conversation_location(self, city_name: str) -> None:
        """Stores the last resolved location in conversation memory."""
        if city_name:
            self._last_location = city_name.strip()
            self._last_timestamp = time.time()
            logger.debug("Weather location context updated to: %s", self._last_location)

    def clear_context(self) -> None:
        """Clears stored conversation location."""
        self._last_location = None
        self._last_timestamp = 0.0

    def get_conversation_location(self) -> Optional[str]:
        """Returns active conversation location if not expired."""
        if self._last_location and (time.time() - self._last_timestamp) <= self.context_ttl:
            return self._last_location
        return None

    def _load_cached_device_location(self) -> Optional[WeatherLocation]:
        """Loads cached device location from local storage if available."""
        if not self.cache_file or not self.cache_file.exists():
            return None
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_time = float(data.get("timestamp", 0))
            if (time.time() - cached_time) < (self.device_location_ttl * 24):
                city = data.get("city")
                if city:
                    loc = WeatherLocation(
                        name=city,
                        state=data.get("state"),
                        country=data.get("country"),
                        latitude=float(data["latitude"]) if data.get("latitude") is not None else None,
                        longitude=float(data["longitude"]) if data.get("longitude") is not None else None,
                        is_default=False,
                        resolution_source="device_location",
                    )
                    self._cached_device_loc = loc
                    self._device_loc_timestamp = cached_time
                    logger.debug("Loaded cached device location: %s", loc.name)
                    return loc
        except Exception as e:
            logger.debug("Failed to load device location cache: %s", e)
        return None

    def _save_cached_device_location(self, loc: WeatherLocation) -> None:
        """Persists device location to disk cache."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "city": loc.name,
                "state": loc.state,
                "country": loc.country,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "timestamp": time.time(),
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.debug("Failed to save device location cache: %s", e)

    def get_device_location(self, force_refresh: bool = False) -> Optional[WeatherLocation]:
        """
        Discovers the user's actual physical/network device location via public IP geolocation.
        Uses cached location if fresh, otherwise queries public API-free endpoints.
        """
        if not self.enable_device_location:
            return None

        # 1. Fast in-memory cache check
        now = time.time()
        with self._lock:
            if not force_refresh and self._cached_device_loc:
                if (now - self._device_loc_timestamp) < self.device_location_ttl:
                    return self._cached_device_loc

        # 2. Check disk cache if in-memory cache is empty
        if not force_refresh and self._cached_device_loc is None:
            disk_loc = self._load_cached_device_location()
            if disk_loc:
                with self._lock:
                    self._cached_device_loc = disk_loc
                return disk_loc

        # 3. Public API-Free Geolocation Discovery (Rule 32 compliant)
        endpoints = [
            (
                "https://ipinfo.io/json",
                lambda d: (
                    d.get("city"),
                    d.get("region"),
                    d.get("country"),
                    float(d["loc"].split(",")[0]) if "loc" in d and "," in d["loc"] else None,
                    float(d["loc"].split(",")[1]) if "loc" in d and "," in d["loc"] else None,
                ),
            ),
            (
                "http://ip-api.com/json",
                lambda d: (
                    d.get("city"),
                    d.get("regionName"),
                    d.get("country"),
                    float(d.get("lat")) if d.get("lat") is not None else None,
                    float(d.get("lon")) if d.get("lon") is not None else None,
                ),
            ),
            (
                "https://ipapi.co/json/",
                lambda d: (
                    d.get("city"),
                    d.get("region"),
                    d.get("country_name"),
                    float(d.get("latitude")) if d.get("latitude") is not None else None,
                    float(d.get("longitude")) if d.get("longitude") is not None else None,
                ),
            ),
        ]

        for url, extractor in endpoints:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "JarvisWeatherEngine/2.1", "Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        city, region, country, lat, lon = extractor(data)
                        if city and city.strip():
                            clean_city = city.strip().title()
                            loc = WeatherLocation(
                                name=clean_city,
                                state=region.strip() if region else None,
                                country=country.strip() if country else None,
                                latitude=lat,
                                longitude=lon,
                                is_default=False,
                                resolution_source="device_location",
                            )
                            with self._lock:
                                self._cached_device_loc = loc
                                self._device_loc_timestamp = time.time()
                            self._save_cached_device_location(loc)
                            logger.info(
                                "Discovered user device location: %s, %s (lat=%s, lon=%s)",
                                loc.name, loc.state, loc.latitude, loc.longitude
                            )
                            return loc
            except Exception as e:
                logger.debug("Endpoint %s geolocation attempt failed: %s", url, e)
                continue

        # 4. If live endpoints failed, return stale memory cache if exists
        with self._lock:
            if self._cached_device_loc:
                return self._cached_device_loc

        return None

    @staticmethod
    def get_city_coordinates(city_name: str) -> Tuple[Optional[float], Optional[float]]:
        """Returns (latitude, longitude) for known cities if available."""
        if not city_name:
            return None, None
        coords = CITY_COORDINATES.get(city_name.strip().lower())
        if coords:
            return coords[0], coords[1]
        return None, None

    def resolve_location(self, text: str) -> Tuple[Optional[WeatherLocation], bool, Optional[str]]:
        """
        Resolves query text into a WeatherLocation using strict priority hierarchy:
        1. Local area cues ("mere yahan") -> Current device location
        2. Explicit city in text ("Mumbai mein baarish") -> Explicit location
        3. Active conversation context location ("aur kal ka?") -> Context location
        4. Device geolocation for general weather queries ("abhi weather kaisa hai") -> Device location
        5. Configured default location (system baseline fallback) -> Default location
        6. Clarification prompt
        """
        raw = text.strip()
        lowered = raw.lower()

        # 1. Check for explicit local-area cues ("mere yahan", "apne yahan", "here", "my location")
        if any(cue in lowered for cue in LOCAL_AREA_CUES):
            device_loc = self.get_device_location()
            if device_loc:
                self.update_conversation_location(device_loc.name)
                return device_loc, False, None
            # Fallback if device location unavailable
            target_name = self.get_conversation_location() or self.default_city
            if target_name:
                lat, lon = self.get_city_coordinates(target_name)
                loc = WeatherLocation(
                    name=target_name,
                    latitude=lat,
                    longitude=lon,
                    is_default=True,
                    resolution_source="default_config"
                )
                return loc, False, None

        # 2. Extract explicit city from text
        explicit_city = self._extract_explicit_city(lowered)
        if explicit_city:
            lat, lon = self.get_city_coordinates(explicit_city)
            loc = WeatherLocation(
                name=explicit_city.title(),
                latitude=lat,
                longitude=lon,
                is_default=False,
                resolution_source="explicit"
            )
            self.update_conversation_location(loc.name)
            return loc, False, None

        # 3. Check recent conversation context location
        conv_loc = self.get_conversation_location()
        if conv_loc:
            lat, lon = self.get_city_coordinates(conv_loc)
            loc = WeatherLocation(
                name=conv_loc,
                latitude=lat,
                longitude=lon,
                is_default=False,
                resolution_source="conversation_context"
            )
            return loc, False, None

        # 4. User's Current Device Geolocation for queries without specified city ("abhi weather kaisa hai")
        device_loc = self.get_device_location()
        if device_loc:
            self.update_conversation_location(device_loc.name)
            return device_loc, False, None

        # 5. Fallback to configured default location (system baseline)
        if self.default_city:
            lat, lon = self.get_city_coordinates(self.default_city)
            loc = WeatherLocation(
                name=self.default_city,
                latitude=lat,
                longitude=lon,
                is_default=True,
                resolution_source="default_config"
            )
            return loc, False, None

        # 6. Clarification needed
        prompt = "Main kis city ka weather check karun?"
        return None, True, prompt

    def _extract_explicit_city(self, lowered: str) -> Optional[str]:
        """Scans query for explicit city names using known vocab and regex patterns."""
        # Pattern A: "<city> ka/ki/ke/mein/me weather/mausam/baarish/temp"
        m_prep = re.search(
            r"\b([a-zA-Z\s]{3,20}?)\s+(?:ka|ki|ke|mein|me|se)\s+(?:weather|mausam|mousam|temperature|temp|baarish|rain|forecast|garmi|sardi|humidity|hawa)\b",
            lowered
        )
        if m_prep:
            cand = m_prep.group(1).strip()
            # Clean noise words (incl. discourse leads like "achha"/"theek hai")
            cand = re.sub(r"^(?:bhai|jarvis|aaj|kal|parso|tell|me|please|show|check|achha|accha|acha|theek|thik|ok|okay)\s+", "", cand).strip()
            if cand in COMMON_CITIES or len(cand.split()) == 1 and cand not in ("aaj", "kal", "parso", "weather", "rain", "achha", "accha", "acha", "theek", "thik"):
                return cand

        # Pattern B: "weather/mausam/forecast of/in/for <city>"
        m_of = re.search(
            r"\b(?:weather|mausam|mousam|forecast|temperature|temp|rain|baarish)\s+(?:of|in|at|for)\s+([a-zA-Z\s]{3,20}?)(?:\s+(?:today|tomorrow|aaj|kal|batao|kaisa))?$",
            lowered
        )
        if m_of:
            cand = m_of.group(1).strip()
            cand = re.sub(r"\b(?:today|tomorrow|now|please|batao)\b", "", cand).strip()
            if cand:
                return cand

        # Pattern C: Direct known city keyword check
        for city in sorted(COMMON_CITIES, key=len, reverse=True):
            pattern = rf"\b{re.escape(city)}\b"
            if re.search(pattern, lowered):
                return city

        # Pattern D: "<city> weather/mausam/forecast/temperature"
        m_direct = re.search(
            r"\b([a-zA-Z]{3,20})\s+(?:weather|mausam|mousam|forecast|temperature|temp)\b",
            lowered
        )
        if m_direct:
            cand = m_direct.group(1).strip()
            if cand not in ("aaj", "kal", "parso", "today", "tomorrow", "live", "current", "abhi", "local", "check", "show", "tell",
                            "achha", "accha", "acha", "theek", "thik", "badhiya", "ok", "okay"):
                return cand

        return None

