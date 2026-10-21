"""The countries that can be played and how many soldiers each one starts with."""

import json
from pathlib import Path

from pydantic import BaseModel

# (population limit, soldiers) from the assignment's table; the last row is "anything more".
SOLDIER_TABLE = [
    (5_000_000, 1),
    (10_000_000, 2),
    (25_000_000, 3),
    (50_000_000, 4),
    (75_000_000, 5),
    (100_000_000, 6),
    (125_000_000, 7),
    (150_000_000, 8),
]


def soldier_value(population: int) -> int:
    """Soldiers a country is worth. India (1.4bn) is worth 9, Vatican City (500) is worth 1."""
    for limit, soldiers in SOLDIER_TABLE:
        if population <= limit:
            return soldiers
    return 9


class CountryInfo(BaseModel):
    code: str
    name: str
    population: int
    value: int  # soldiers it starts with


# All playable countries keyed by ISO code, from countries.json (see scripts/).
COUNTRIES = {
    c["code"]: CountryInfo(**c, value=soldier_value(c["population"]))
    for c in json.loads((Path(__file__).parent / "countries.json").read_text())
}
