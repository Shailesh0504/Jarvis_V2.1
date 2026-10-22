# plugins/location/models.py
"""
Geographic & Location Data Models for Jarvis V2 Location Plugin.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PlaceType(str, Enum):
    CITY = "city"
    STATE = "state"
    COUNTRY = "country"
    CONTINENT = "continent"
    LANDMARK = "landmark"
    AIRPORT = "airport"
    MOUNTAIN = "mountain"
    RIVER = "river"
    DISTRICT = "district"
    REGION = "region"
    POINT_OF_INTEREST = "poi"


@dataclass
class GeoLocation:
    """Represents a structured geographical entity."""
    name: str
    place_type: PlaceType
    country_name: str
    continent: str
    state_name: Optional[str] = None
    district_name: Optional[str] = None
    capital: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    description: Optional[str] = None
    extra_info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "place_type": self.place_type.value,
            "country_name": self.country_name,
            "state_name": self.state_name,
            "district_name": self.district_name,
            "continent": self.continent,
            "capital": self.capital,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": self.timezone,
            "aliases": self.aliases,
            "description": self.description,
            "extra_info": self.extra_info
        }


@dataclass
class GeoDistanceResult:
    """Result of distance and route calculation between two places."""
    origin: str
    destination: str
    distance_km: float
    distance_miles: float
    estimated_drive_time: str
    map_url: str
    directions_url: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "distance_km": round(self.distance_km, 2),
            "distance_miles": round(self.distance_miles, 2),
            "estimated_drive_time": self.estimated_drive_time,
            "map_url": self.map_url,
            "directions_url": self.directions_url
        }


@dataclass
class LocationQueryResult:
    """Overall outcome of a location/geography query."""
    success: bool
    action: str
    formatted_answer: str
    location: Optional[GeoLocation] = None
    distance_info: Optional[GeoDistanceResult] = None
    map_url: Optional[str] = None
    needs_clarification: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "formatted_answer": self.formatted_answer,
            "location": self.location.to_dict() if self.location else None,
            "distance_info": self.distance_info.to_dict() if self.distance_info else None,
            "map_url": self.map_url,
            "needs_clarification": self.needs_clarification,
            "error": self.error
        }
