import json
from bisect import bisect_left
from pathlib import Path

from .engine import Country


def soldier_value(population: int) -> int:
    """The assignment's table: up to 5 million is worth 1 soldier, up to 10 million 2, and so on."""
    return bisect_left([5, 10, 25, 50, 75, 100, 125, 150], population / 1e6) + 1


COUNTRIES = {
    c["code"]: Country(code=c["code"], name=c["name"], value=soldier_value(c["population"]))
    for c in json.loads((Path(__file__).parent / "countries.json").read_text())
}
