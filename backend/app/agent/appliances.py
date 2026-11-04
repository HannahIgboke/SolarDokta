"""How much power common Nigerian household appliances draw, so the agent can answer
"Can I use my pressing iron now?".

watts:   typical running power
minutes: how long one typical use lasts (the customer can say otherwise)
surge:   starting kick: motors (pumps, ACs, fridges) pull 2-3x their running power for a
         second or two when they start, which can trip a small inverter
Numbers are typical label values; real appliances vary, so the customer can always give watts.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ApplianceSpec:
    name: str
    watts: float
    minutes: float
    surge: float = 1.0
    aliases: tuple[str, ...] = ()


APPLIANCES = [
    ApplianceSpec("pressing iron", 1000, 30, 1.0, ("iron", "pressing iron", "electric iron")),
    ApplianceSpec("electric kettle", 1500, 5, 1.0, ("kettle", "electric kettle", "water boiler")),
    ApplianceSpec("microwave", 1200, 5, 1.0, ("microwave",)),
    ApplianceSpec("blender", 400, 5, 1.5, ("blender",)),
    ApplianceSpec("rice cooker", 700, 40, 1.0, ("rice cooker",)),
    ApplianceSpec("electric cooker", 1500, 45, 1.0, ("cooker", "hot plate", "hotplate",
                                                     "electric stove", "electric cooker")),
    ApplianceSpec("electric oven", 2000, 45, 1.0, ("oven", "electric oven")),
    ApplianceSpec("air fryer", 1500, 20, 1.0, ("air fryer", "airfryer")),
    ApplianceSpec("toaster", 900, 5, 1.0, ("toaster",)),
    ApplianceSpec("water heater", 2000, 20, 1.0, ("water heater", "heater", "geyser")),
    ApplianceSpec("hair dryer", 1200, 10, 1.0, ("hair dryer", "hairdryer", "blow dryer")),
    ApplianceSpec("washing machine", 500, 60, 2.0, ("washing machine", "washer")),
    ApplianceSpec("pumping machine", 750, 30, 3.0, ("pumping machine", "water pump", "pump",
                                                    "borehole", "sumo")),
    ApplianceSpec("air conditioner (1 hp)", 900, 60, 3.0, ("ac", "a c", "air conditioner",
                                                           "aircon", "air condition", "1hp ac")),
    ApplianceSpec("air conditioner (1.5 hp)", 1300, 60, 3.0, ("1.5hp ac", "1.5 hp ac",
                                                              "1.5hp air conditioner")),
    ApplianceSpec("deep freezer", 200, 60, 3.0, ("freezer", "deep freezer", "chest freezer")),
    ApplianceSpec("fridge", 150, 60, 3.0, ("fridge", "refrigerator")),
    ApplianceSpec("television", 120, 120, 1.0, ("tv", "television", "telly")),
    ApplianceSpec("fan", 70, 120, 1.5, ("fan", "standing fan", "ceiling fan")),
    ApplianceSpec("laptop", 65, 120, 1.0, ("laptop",)),
    ApplianceSpec("desktop computer", 250, 120, 1.0, ("desktop", "computer", "pc")),
    ApplianceSpec("sound system", 150, 120, 1.0, ("sound system", "speaker", "home theatre",
                                                  "home theater")),
    ApplianceSpec("vacuum cleaner", 1000, 20, 1.5, ("vacuum", "vacuum cleaner")),
    ApplianceSpec("phone charger", 10, 60, 1.0, ("phone", "charger", "phone charger")),
    ApplianceSpec("bulbs", 40, 240, 1.0, ("bulb", "bulbs", "lighting")),  # "light" = NEPA
]


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9.]+", " ", text.lower()).strip() + " "


def find_appliance(text: str) -> ApplianceSpec | None:
    """Best match for what the customer typed, e.g. 'my pressing iron' -> pressing iron.

    Matches whole words and prefers the longest alias, so '1.5hp ac' beats 'ac'.
    """
    t = _norm(text)
    best, best_len = None, 0
    for spec in APPLIANCES:
        for alias in spec.aliases:
            a = _norm(alias)
            if a in t and len(a) > best_len:
                best, best_len = spec, len(a)
    return best
