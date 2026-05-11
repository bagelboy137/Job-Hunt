"""Commute-distance filtering.

Primary filter: Haversine great-circle distance ≤ config.max_commute_miles (40 mi).
40 miles from Chestnut Hill captures Wilmington DE, Princeton NJ, and the
entire Philadelphia metro — all realistically within a 1-hour drive.

Optional upgrade: set GOOGLE_MAPS_KEY in .env to get exact driving-time checks
for jobs that fall in the 30–40 mile grey zone near the boundary.
"""
import logging
import math
import time
from typing import Optional

import requests
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim

log = logging.getLogger(__name__)


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


class CommuteFilter:
    def __init__(self, config):
        self.config = config
        self._geocoder = Nominatim(user_agent="pharma-job-alerts-philly")
        self._geo_cache: dict[str, Optional[tuple[float, float]]] = {}

    # ── Public ────────────────────────────────────────────────────────────────

    def filter(self, jobs: list[dict]) -> list[dict]:
        reachable: list[dict] = []
        for job in jobs:
            coords = self._coords(job)
            if coords is None:
                log.debug("Skipping (no coords): %s @ %s", job["title"], job["location"])
                continue

            dist = haversine_miles(
                self.config.home_lat, self.config.home_lon, coords[0], coords[1]
            )

            # For border-zone jobs use Google Maps driving time if key is set
            in_border_zone = 30.0 <= dist <= self.config.max_commute_miles
            if in_border_zone and self.config.google_maps_key:
                minutes = self._google_minutes(coords)
                if minutes is not None:
                    log.debug("%s — Google Maps: %d min drive", job["title"], minutes)
                    if minutes <= 60:
                        job["commute_minutes"] = minutes
                        reachable.append(job)
                    continue  # Don't fall through to distance check

            if dist <= self.config.max_commute_miles:
                job["commute_miles"] = round(dist, 1)
                reachable.append(job)

        return reachable

    # ── Private ───────────────────────────────────────────────────────────────

    def _coords(self, job: dict) -> Optional[tuple[float, float]]:
        # Use API-supplied coordinates when available (most reliable)
        if job.get("lat") is not None and job.get("lon") is not None:
            return job["lat"], job["lon"]

        loc_key = job.get("location", "").strip()
        if not loc_key:
            return None

        if loc_key in self._geo_cache:
            return self._geo_cache[loc_key]

        coords = self._geocode(loc_key)
        self._geo_cache[loc_key] = coords
        return coords

    def _geocode(self, location: str) -> Optional[tuple[float, float]]:
        try:
            time.sleep(1.1)  # Nominatim usage policy: max 1 req/s
            result = self._geocoder.geocode(location, timeout=8)
            if result:
                return result.latitude, result.longitude
        except (GeocoderTimedOut, GeocoderUnavailable) as exc:
            log.warning("Geocoding failed for '%s': %s", location, exc)
        return None

    def _google_minutes(self, dest: tuple[float, float]) -> Optional[int]:
        origin = f"{self.config.home_lat},{self.config.home_lon}"
        destination = f"{dest[0]},{dest[1]}"
        try:
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params={
                    "origins": origin,
                    "destinations": destination,
                    "mode": "driving",
                    "departure_time": "now",
                    "key": self.config.google_maps_key,
                },
                timeout=10,
            )
            resp.raise_for_status()
            element = resp.json()["rows"][0]["elements"][0]
            duration = element.get("duration_in_traffic") or element.get("duration")
            if duration:
                return duration["value"] // 60  # seconds → minutes
        except Exception as exc:
            log.warning("Google Maps API error: %s", exc)
        return None
