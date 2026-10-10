"""Fictional companies, parties, items and employees for the synthetic books.

Train and test draw from disjoint name pools, so the unseen split has companies, parties
and banks the models never saw.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from viveka import gstin

STATES = {
    "27": "Maharashtra",
    "24": "Gujarat",
    "29": "Karnataka",
    "33": "Tamil Nadu",
    "07": "Delhi",
    "09": "Uttar Pradesh",
    "19": "West Bengal",
    "36": "Telangana",
    "08": "Rajasthan",
    "23": "Madhya Pradesh",
    "06": "Haryana",
    "32": "Kerala",
}

# Disjoint vocabularies per pool: "seen" builds train/dev, "unseen" builds the test split.
# fmt: off
_POOLS = {
    "seen": {
        "first": (
            "Kaveri", "Narmada", "Shree", "Sahyadri", "Ganga", "Vindhya", "Aravali", "Konark",
            "Deccan", "Malabar", "Sindhu", "Godavari", "Tapi", "Nilgiri", "Satpura", "Ajanta",
            "Lotus", "Trident", "Pragati", "Unnati", "Mahalaxmi", "Annapurna", "Saraswati",
            "Vardhman", "Om Sai", "Jai Ambe", "Siddhi", "Balaji",
        ),
        "trade": (
            "Fabricators", "Steels", "Polymers", "Textiles", "Engineering", "Chemicals",
            "Auto Components", "Packaging", "Electricals", "Agro Foods", "Paper Mills",
            "Traders", "Enterprises", "Industries", "Castings", "Pharma",
        ),
        "suffix": ("Pvt Ltd", "Private Limited", "LLP", "& Co", "Industries", "Ltd"),
        "banks": ("HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank"),
        "people_first": (
            "Ramesh", "Suresh", "Anita", "Priya", "Mahesh", "Kavita", "Sunil", "Deepa",
            "Vijay", "Rekha", "Amit", "Neha", "Rahul", "Pooja", "Sanjay", "Meena",
        ),
        "people_last": (
            "Patil", "Sharma", "Iyer", "Reddy", "Deshmukh", "Gupta", "Nair", "Joshi",
            "Kulkarni", "Verma", "Menon", "Shah",
        ),
        "foreign": (
            ("Hamburg Maschinen GmbH", "Germany", "EUR"),
            ("Pacific Resin Corp", "USA", "USD"),
            ("Osaka Precision KK", "Japan", "JPY"),
            ("Gulf Trading FZE", "UAE", "AED"),
            ("Thames Components Ltd", "United Kingdom", "GBP"),
        ),
    },
    "unseen": {
        "first": (
            "Kalinga", "Chola", "Hampi", "Brahmaputra", "Chambal", "Mandovi", "Sabari",
            "Pench", "Kanha", "Gir", "Rann", "Sundarban", "Kopili", "Mahanadi",
        ),
        "trade": (
            "Metal Works", "Rubber Products", "Garments", "Forgings", "Glass Works",
            "Ceramics", "Plastics", "Wires & Cables", "Spices", "Furnishings",
        ),
        "suffix": ("Pvt. Ltd.", "Limited", "Udyog", "Brothers", "OPC Pvt Ltd"),
        "banks": ("Kotak Mahindra Bank", "Bank of Baroda", "Canara Bank", "IDFC First Bank"),
        "people_first": (
            "Arjun", "Lakshmi", "Farhan", "Swati", "Gurpreet", "Ananya", "Tenzin", "Bhavna",
            "Irfan", "Jyoti", "Karthik", "Madhuri",
        ),
        "people_last": ("Bose", "Khan", "Pillai", "Sandhu", "Rao", "Mishra", "Das", "Bhat"),
        "foreign": (
            ("Shenzhen Brightway Electronics Co", "China", "CNY"),
            ("Lyon Textiles SARL", "France", "EUR"),
            ("Busan Heavy Parts Co", "South Korea", "USD"),
            ("Melbourne Agri Exports Pty", "Australia", "AUD"),
        ),
    },
}

# (name, HSN, unit, rate range): goods the companies trade or consume.
GOODS = (
    ("HR Steel Coil", "7208", "MT", (48000, 62000)),
    ("GI Sheet 0.8mm", "7210", "MT", (70000, 86000)),
    ("MS Angle 50x50", "7216", "MT", (52000, 60000)),
    ("Cotton Fabric 60s", "5208", "MTR", (90, 240)),
    ("Polyester Yarn", "5402", "KG", (110, 180)),
    ("Caustic Soda Flakes", "2815", "KG", (38, 55)),
    ("Industrial Relay 24V", "8536", "NOS", (180, 650)),
    ("LDPE Granules", "3901", "KG", (95, 130)),
    ("Brake Drum Assembly", "8708", "NOS", (1400, 3200)),
    ("Kraft Paper 120 GSM", "4804", "KG", (32, 48)),
    ("Corrugated Boxes", "4819", "NOS", (18, 65)),
    ("Ball Bearing 6205", "8482", "NOS", (95, 240)),
    ("Copper Wire 2.5 sqmm", "8544", "MTR", (28, 46)),
    ("Paracetamol API", "2924", "KG", (380, 520)),
    ("Basmati Rice", "1006", "KG", (75, 140)),
    ("Hydraulic Pump", "8413", "NOS", (8500, 26000)),
)

# (description, SAC, rate range): services booked as expenses.
SERVICES = (
    ("Office rent", "997212", (25000, 120000)),
    ("Professional fees - statutory audit", "998221", (40000, 150000)),
    ("Legal consultancy", "998211", (15000, 80000)),
    ("Security services", "998525", (18000, 60000)),
    ("Housekeeping services", "998533", (9000, 30000)),
    ("Internet and leased line", "998422", (3000, 15000)),
    ("Advertisement in newspaper", "998361", (12000, 70000)),
    ("Courier charges", "996812", (800, 6000)),
    ("Repairs to machinery", "998719", (5000, 45000)),
    ("Software subscription", "997331", (4000, 30000)),
)
# fmt: on

JOB_PROCESSES = (
    "Galvanising",
    "Powder coating",
    "Machining",
    "Heat treatment",
    "Dyeing",
    "Printing",
    "Stitching",
    "Plating",
    "Cutting and slitting",
    "Assembly",
)

GODOWNS = (
    "Main Store",
    "Bhiwandi Godown",
    "Factory Floor",
    "Finished Goods Store",
    "Raw Material Store",
    "Branch Warehouse",
    "Unit 2 Store",
)

_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def make_gstin(rng: random.Random, state: str, entity: str = "C") -> str:
    """A GSTIN with a valid Luhn mod 36 check character (and a fictional PAN)."""
    pan = (
        "".join(rng.choice(_CHARS) for _ in range(3))
        + entity
        + rng.choice(_CHARS)
        + f"{rng.randint(0, 9999):04d}"
        + rng.choice(_CHARS)
    )
    first14 = f"{state}{pan}{rng.choice('123')}Z"
    return first14 + gstin.checksum_char(first14)


@dataclass
class Party:
    name: str
    gstin: str | None
    state: str
    role: str  # supplier | customer | vendor | job_worker | principal | foreign
    country: str = "India"
    currency: str = "INR"

    @property
    def prefix(self) -> str:
        return "".join(w[0] for w in re.findall(r"[A-Za-z]+", self.name)[:2]).upper()


@dataclass
class Employee:
    emp_id: str
    name: str
    basic: int


@dataclass
class Company:
    name: str
    gstin: str
    state: str
    prefix: str
    banks: list[str]
    cash: str
    numbering: str  # typed (one series per voucher type) | generic (one running series)
    parties: dict[str, list[Party]] = field(default_factory=dict)
    employees: list[Employee] = field(default_factory=list)
    goods: list[tuple] = field(default_factory=list)
    godowns: list[str] = field(default_factory=list)
    _counters: dict[str, int] = field(default_factory=dict)

    def next_number(self, series: str, rng: random.Random) -> str:
        key = series if self.numbering == "typed" else "VCH"
        n = self._counters.get(key, rng.randint(11, 400)) + 1
        self._counters[key] = n
        if self.numbering == "typed":
            return f"{self.prefix}/{series}/{n:04d}"
        return f"{self.prefix}/26-27/{n:05d}"

    def party(self, role: str, rng: random.Random) -> Party:
        return rng.choice(self.parties[role])


class Names:
    """Draws unique firm and person names from one pool."""

    def __init__(self, pool: str, rng: random.Random):
        self.p = _POOLS[pool]
        self.rng = rng
        self.used: set[str] = set()

    def firm(self) -> str:
        for _ in range(500):
            name = (
                f"{self.rng.choice(self.p['first'])} {self.rng.choice(self.p['trade'])} "
                f"{self.rng.choice(self.p['suffix'])}"
            )
            if name not in self.used:
                self.used.add(name)
                return name
        raise RuntimeError("firm name pool exhausted")

    def person(self) -> str:
        return f"{self.rng.choice(self.p['people_first'])} {self.rng.choice(self.p['people_last'])}"


def make_company(pool: str, rng: random.Random, names: Names) -> Company:
    p = _POOLS[pool]
    state = rng.choice(list(STATES))
    name = names.firm()
    words = re.findall(r"[A-Za-z]+", name)
    company = Company(
        name=name,
        gstin=make_gstin(rng, state),
        state=state,
        prefix=(words[0][0] + words[1][0]).upper(),
        banks=[f"{b} A/c {rng.randint(1000, 9999)}" for b in rng.sample(p["banks"], 2)],
        cash=rng.choice(("Cash", "Cash in Hand", "Petty Cash")),
        numbering=rng.choice(("typed", "generic")),
    )
    other_states = [s for s in STATES if s != state]

    def domestic(role: str, n: int) -> list[Party]:
        out = []
        for _ in range(n):
            st = state if rng.random() < 0.5 else rng.choice(other_states)
            out.append(Party(names.firm(), make_gstin(rng, st, rng.choice("CCFP")), st, role))
        return out

    company.parties = {
        "supplier": domestic("supplier", 6),
        "customer": domestic("customer", 6),
        "vendor": domestic("vendor", 4),
        "job_worker": domestic("job_worker", 3),
        "principal": domestic("principal", 2),
        "foreign": [
            Party(n, None, "97", "foreign", country=c, currency=cur)
            for n, c, cur in rng.sample(p["foreign"], 3)
        ],
    }
    company.employees = [
        Employee(f"E{rng.randint(100, 999)}", names.person(), rng.randrange(14000, 90000, 500))
        for _ in range(8)
    ]
    company.goods = rng.sample(GOODS, 6)
    company.godowns = rng.sample(GODOWNS, 3)
    return company
