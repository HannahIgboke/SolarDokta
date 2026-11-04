"""Appliance lists for each kind of site.

All numbers are reasonable assumptions for Nigerian homes and businesses running on solar.
Change them freely, or replace them with what real owners report in the Google Form.

Appliance kinds:
- always:  on all the time inside its window (router, security lights)
- cycle:   compressor that switches on and off (fridge, freezer); works harder when hot
- window:  used during a time window on most days (TV, fans, lights, computers)
- event:   short uses a few times a day (iron, pumping machine, microwave)
- cooling: air conditioner; more likely to be on when it's hot

Windows are local hours, e.g. (19, 23) = 7pm to 11pm; (21, 6) wraps past midnight.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Appliance:
    name: str
    watts: float
    kind: str                                   # always | cycle | window | event | cooling
    windows: tuple[tuple[int, int], ...] = ((0, 24),)
    qty: int = 1
    prob: float = 1.0                           # window/cooling: chance it's used on a given day
    uses_per_day: float = 0.0                   # event: average number of uses
    minutes: tuple[int, int] = (10, 30)         # event: min/max length of one use
    duty: float = 0.4                           # cycle/cooling: share of time the compressor runs
    days: str = "all"                           # all | weekdays | not_sunday


@dataclass(frozen=True)
class Profile:
    name: str
    appliances: tuple[Appliance, ...] = field(default_factory=tuple)


PROFILES: dict[str, Profile] = {
    "home": Profile("home", (
        Appliance("router", 15, "always"),
        Appliance("security_light", 40, "always", windows=((19, 6),), qty=2),
        Appliance("fridge", 150, "cycle", duty=0.40),
        Appliance("lights", 60, "window", windows=((18, 23),), prob=0.98),
        Appliance("tv", 120, "window", windows=((19, 23),), prob=0.9),
        Appliance("fans", 70, "window", windows=((21, 6),), qty=2, prob=0.95),
        Appliance("phone_laptop", 80, "window", windows=((9, 17),), prob=0.7),
        Appliance("pressing_iron", 1000, "event", uses_per_day=0.6, minutes=(15, 35),
                  windows=((6, 8), (19, 21))),
        Appliance("pumping_machine", 750, "event", uses_per_day=0.8, minutes=(20, 40),
                  windows=((6, 9), (17, 20))),
        Appliance("microwave", 1200, "event", uses_per_day=1.2, minutes=(3, 6),
                  windows=((7, 9), (12, 14), (19, 21))),
        Appliance("ac_bedroom", 1100, "cooling", windows=((22, 5),), prob=0.35, duty=0.65),
    )),
    "home_large": Profile("home_large", (
        Appliance("router", 20, "always"),
        Appliance("cctv", 40, "always"),
        Appliance("security_light", 40, "always", windows=((19, 6),), qty=4),
        Appliance("fridge", 180, "cycle", duty=0.40),
        Appliance("freezer", 200, "cycle", duty=0.45),
        Appliance("lights", 120, "window", windows=((18, 24),), prob=0.98),
        Appliance("tv", 150, "window", windows=((17, 24),), qty=2, prob=0.9),
        Appliance("fans", 70, "window", windows=((13, 17), (21, 6)), qty=3, prob=0.9),
        Appliance("home_office", 250, "window", windows=((9, 18),), prob=0.6, days="weekdays"),
        Appliance("pressing_iron", 1000, "event", uses_per_day=1.0, minutes=(15, 40),
                  windows=((6, 8), (19, 22))),
        Appliance("pumping_machine", 1100, "event", uses_per_day=1.2, minutes=(25, 45),
                  windows=((6, 9), (16, 20))),
        Appliance("washing_machine", 500, "event", uses_per_day=0.4, minutes=(50, 80),
                  windows=((9, 16),)),
        Appliance("microwave", 1200, "event", uses_per_day=2.0, minutes=(3, 6),
                  windows=((7, 9), (12, 14), (19, 21))),
        Appliance("ac_living", 1500, "cooling", windows=((12, 18),), prob=0.5, duty=0.7),
        Appliance("ac_bedrooms", 1100, "cooling", windows=((22, 6),), qty=2, prob=0.55, duty=0.65),
    )),
    "clinic": Profile("clinic", (
        Appliance("router", 20, "always"),
        Appliance("lights_24h", 150, "always"),
        Appliance("vaccine_fridge", 120, "cycle", duty=0.5),
        Appliance("fridge", 150, "cycle", duty=0.4),
        Appliance("computers", 300, "window", windows=((8, 18),), prob=0.95, days="not_sunday"),
        Appliance("fans", 70, "window", windows=((9, 18),), qty=4, prob=0.9),
        Appliance("ward_fans", 70, "window", windows=((21, 6),), qty=3, prob=0.8),
        Appliance("sterilizer", 1500, "event", uses_per_day=3.0, minutes=(20, 30),
                  windows=((8, 17),), days="not_sunday"),
        Appliance("lab_centrifuge", 400, "event", uses_per_day=4.0, minutes=(5, 15),
                  windows=((8, 16),), days="not_sunday"),
        Appliance("borehole_pump", 1100, "event", uses_per_day=1.5, minutes=(30, 50),
                  windows=((6, 9), (15, 18))),
        Appliance("ac_consulting", 1100, "cooling", windows=((9, 17),), prob=0.6, duty=0.7,
                  days="not_sunday"),
    )),
    "school": Profile("school", (
        Appliance("router", 20, "always"),
        Appliance("security_light", 40, "always", windows=((19, 6),), qty=6),
        Appliance("staff_fridge", 150, "cycle", duty=0.4),
        Appliance("computer_lab", 1500, "window", windows=((9, 14),), prob=0.9, days="weekdays"),
        Appliance("projectors", 300, "window", windows=((8, 14),), prob=0.8, days="weekdays"),
        Appliance("classroom_fans", 70, "window", windows=((9, 14),), qty=10, prob=0.9,
                  days="weekdays"),
        Appliance("office", 300, "window", windows=((8, 16),), prob=0.95, days="weekdays"),
        Appliance("borehole_pump", 1100, "event", uses_per_day=1.5, minutes=(30, 60),
                  windows=((6, 9), (14, 17)), days="weekdays"),
        Appliance("ac_principal", 1100, "cooling", windows=((10, 15),), prob=0.5, duty=0.7,
                  days="weekdays"),
    )),
    "shop": Profile("shop", (
        Appliance("chest_freezer", 200, "cycle", qty=2, duty=0.5),
        Appliance("drinks_fridge", 250, "cycle", duty=0.55),
        Appliance("lights", 80, "window", windows=((7, 21),), prob=0.95, days="not_sunday"),
        Appliance("fan", 70, "window", windows=((9, 20),), qty=2, prob=0.9, days="not_sunday"),
        Appliance("tv", 120, "window", windows=((10, 21),), prob=0.7, days="not_sunday"),
        Appliance("pos_and_phones", 60, "window", windows=((8, 21),), prob=0.95, days="not_sunday"),
    )),
}
