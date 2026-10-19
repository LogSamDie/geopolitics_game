"""Build the country data used by the game from two public sources.

- Borders and label positions: Natural Earth 1:110m admin-0 countries (public domain).
- Populations: scripts/population.json, copied from worldometers.info (October 2025),
  the source the assignment names.

Writes frontend/public/world.geojson (every border, drawn on the map) and
backend/app/countries.json (the countries with a known population, which can be played).
Run once: `python scripts/build_countries.py`.
"""

import json
import urllib.request
from pathlib import Path
from typing import Any

NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_110m_admin_0_countries.geojson"
)
ROOT = Path(__file__).resolve().parent.parent


def rounded(coords: Any) -> Any:
    """Round coordinates to 2 decimals (about 1 km), which cuts the file size by half."""
    if isinstance(coords, (int, float)):
        return round(coords, 2)
    return [rounded(c) for c in coords]


def main() -> None:
    with urllib.request.urlopen(NE_URL) as response:
        natural_earth = json.load(response)
    population = {
        c["code"]: c for c in json.loads((ROOT / "scripts/population.json").read_text())
    }

    features = []
    countries = []
    for feature in natural_earth["features"]:
        props = feature["properties"]
        code = props["ISO_A2_EH"] if props["ISO_A2_EH"] != "-99" else props["ADM0_A3"]
        known = population.get(code)
        name = known["name"] if known else props["NAME"]
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": feature["geometry"]["type"],
                    "coordinates": rounded(feature["geometry"]["coordinates"]),
                },
                "properties": {
                    "code": code,
                    "name": name,
                    "lon": round(props["LABEL_X"], 2),
                    "lat": round(props["LABEL_Y"], 2),
                },
            }
        )
        if known:
            countries.append({"code": code, "name": name, "population": known["population"]})

    countries.sort(key=lambda c: c["name"])
    (ROOT / "frontend/public/world.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"))
    )
    (ROOT / "backend/app/countries.json").write_text(json.dumps(countries, indent=1) + "\n")
    print(f"{len(features)} borders, {len(countries)} playable countries")


if __name__ == "__main__":
    main()
