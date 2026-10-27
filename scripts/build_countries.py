"""Build frontend/public/world.geojson and backend/app/countries.json from their public sources:
populations from worldometers.info, borders and label positions from Natural Earth 1:50m.
"""

import html
import json
import re
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
# Worldometers names that match none of Natural Earth's.
ALIASES = {
    "DR Congo": "CD",
    "Czech Republic (Czechia)": "CZ",
    "Holy See": "VA",
    "Saint Kitts & Nevis": "KN",
    "Saint Pierre & Miquelon": "PM",
    "Sao Tome & Principe": "ST",
    "St. Vincent & Grenadines": "VC",
    "State of Palestine": "PS",
    "Turks and Caicos": "TC",
    "U.S. Virgin Islands": "VI",
    "Wallis & Futuna": "WF",
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request) as response:
        return response.read()


def code_of(props: dict[str, Any]) -> str:
    # Dependencies without an ISO code carry their parent's in ISO_A2_EH.
    shared = props["TYPE"] == "Dependency" and props["ISO_A2"] == "-99"
    return props["ADM0_A3"] if props["ISO_A2_EH"] == "-99" or shared else props["ISO_A2_EH"]


def rounded(coords: Any) -> Any:
    # About 1 km, which halves the file size.
    if isinstance(coords, (int, float)):
        return round(coords, 2)
    return [rounded(c) for c in coords]


def main() -> None:
    page = fetch("https://www.worldometers.info/world-population/population-by-country/").decode()
    rows = re.findall(
        r"<tr[^>]*>\s*<td[^>]*>\s*\d+\s*</td>\s*<td[^>]*>\s*<a[^>]*>\s*(.*?)\s*</a>\s*</td>"
        r"\s*<td[^>]*>\s*([\d,]+)\s*</td>",
        page,
        re.S,
    )
    populations = {html.unescape(name): int(digits.replace(",", "")) for name, digits in rows}
    borders = json.loads(
        fetch(
            "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
            "geojson/ne_50m_admin_0_countries.geojson"
        )
    )["features"]
    borders = [f for f in borders if f["properties"]["NAME"] != "Antarctica"]

    code_by_name = dict(ALIASES)
    for feature in borders:
        for field in ("NAME", "NAME_LONG", "NAME_EN", "ADMIN"):
            name = feature["properties"][field]
            if name != "-99":
                code_by_name.setdefault(name, code_of(feature["properties"]))
    population_by_code = {code_by_name[n]: p for n, p in populations.items() if n in code_by_name}
    name_by_code = {code_by_name[n]: n.split(" (")[0] for n in populations if n in code_by_name}

    features = []
    countries = []
    for feature in borders:
        props = feature["properties"]
        code = code_of(props)
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": feature["geometry"]["type"],
                    "coordinates": rounded(feature["geometry"]["coordinates"]),
                },
                "properties": {
                    "code": code,
                    "lon": round(props["LABEL_X"], 2),
                    "lat": round(props["LABEL_Y"], 2),
                },
            }
        )
        if code in population_by_code:
            name = name_by_code.get(code, props["NAME"])
            countries.append({"code": code, "name": name, "population": population_by_code[code]})

    countries.sort(key=lambda c: unicodedata.normalize("NFKD", c["name"]).casefold())
    (ROOT / "frontend/public/world.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"))
    )
    (ROOT / "backend/app/countries.json").write_text(json.dumps(countries, indent=1) + "\n")
    unmatched = sorted(n for n in populations if n not in code_by_name)
    print(f"{len(features)} borders, {len(countries)} playable countries")
    print(f"worldometers rows without a border of their own: {', '.join(unmatched)}")


if __name__ == "__main__":
    main()
