# core/weather/fetcher.py
"""Concurrent public web fetcher with timeout policies and offline safety."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from typing import Dict, List, Optional
import urllib.parse
import urllib.request

from core.connectivity import ConnectivityManager
from core.weather.models import WeatherLocation

logger = logging.getLogger("jarvis.weather.fetcher")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 JarvisWeatherEngine/2.1"


class WeatherFetcher:
    """Retrieves raw content from public weather web endpoints under strict timeout governance."""

    def __init__(
        self,
        connectivity_manager: Optional[ConnectivityManager] = None,
        timeout_seconds: float = 3.5,
        max_workers: int = 3
    ):
        self.connectivity = connectivity_manager or ConnectivityManager()
        self.timeout = timeout_seconds
        self.max_workers = max_workers

    def is_online(self) -> bool:
        """Returns True if network connectivity is available."""
        return self.connectivity.is_online

    def build_url(self, url_pattern: str, location: WeatherLocation) -> str:
        """Constructs target URL by populating location name or coordinates."""
        encoded_name = urllib.parse.quote(location.name.strip())
        url = url_pattern.replace("{location}", encoded_name)

        lat = location.latitude
        lon = location.longitude
        if lat is None or lon is None:
            from core.weather.location_resolver import CITY_COORDINATES
            coords = CITY_COORDINATES.get(location.name.strip().lower())
            if coords:
                lat, lon = coords
            else:
                lat, lon = (28.6139, 77.2090)

        url = url.replace("{lat}", str(round(lat, 4)))
        url = url.replace("{lon}", str(round(lon, 4)))
        return url

    def fetch_single_url(self, url: str) -> Optional[bytes]:
        """Fetches raw bytes from a public web URL within timeout."""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status == 200:
                    return response.read()
                logger.warning("Weather URL %s returned status %d", url, response.status)
        except Exception as e:
            logger.debug("Failed to fetch weather URL %s: %s", url, e)
        return None
