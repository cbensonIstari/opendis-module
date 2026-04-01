"""ECEF to geodetic (WGS-84) coordinate conversion.

Converts Earth-Centered Earth-Fixed (x, y, z) coordinates in meters
to geodetic (latitude_deg, longitude_deg, altitude_m) using the WGS-84 ellipsoid.
No external dependencies (no pyproj).
"""

import math

# WGS-84 constants
_A = 6378137.0  # Semi-major axis (meters)
_F = 1.0 / 298.257223563  # Flattening
_B = _A * (1.0 - _F)  # Semi-minor axis
_E2 = 1.0 - (_B**2 / _A**2)  # First eccentricity squared


def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Convert ECEF (x, y, z) in meters to (lat_deg, lon_deg, alt_m) using WGS-84.

    Uses iterative Bowring method (10 iterations, converges to sub-mm accuracy).

    Returns:
        Tuple of (latitude_degrees, longitude_degrees, altitude_meters).
    """
    lon = math.atan2(y, x)
    p = math.sqrt(x**2 + y**2)

    # Handle polar singularity
    if p < 1e-10:
        lat = math.copysign(math.pi / 2.0, z)
        n = _A / math.sqrt(1.0 - _E2 * math.sin(lat) ** 2)
        alt = abs(z) - _B
        return math.degrees(lat), math.degrees(lon), alt

    # Initial latitude estimate
    lat = math.atan2(z, p * (1.0 - _E2))

    # Iterative refinement
    for _ in range(10):
        n = _A / math.sqrt(1.0 - _E2 * math.sin(lat) ** 2)
        lat = math.atan2(z + _E2 * n * math.sin(lat), p)

    n = _A / math.sqrt(1.0 - _E2 * math.sin(lat) ** 2)
    alt = p / math.cos(lat) - n

    return math.degrees(lat), math.degrees(lon), alt
