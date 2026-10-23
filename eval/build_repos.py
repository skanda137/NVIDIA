"""
Deterministically build the seeded eval repos: each is a git repo with a base
commit (code + passing tests) and a PR commit (new code, some of it untested).

    python eval/build_repos.py <out_dir>      # builds all, prints each diff

A line ending in `  #@<category>` marks where a gap is expected to start. The
marker is stripped before the file is written (the model never sees it) and
recorded in RepoSpec.categories as {(file, line): category}. Gaps are not
designed around any known model failure; they are the ordinary shapes a PR
leaves untested.

Categories: branch (plain uncovered branch), exit_arc (partial branch whose
missing arc leaves the function), exception (needs pytest.raises), third_party
(calls requests / python-dateutil, listed in requirements.txt), stateful (a
method whose result depends on earlier calls), loop (a branch inside a loop or
comprehension).
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

MARK = "  #@"
# Fixed author/committer identity and dates: same inputs -> same commit SHAs.
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Eval", "GIT_AUTHOR_EMAIL": "eval@example.com",
    "GIT_COMMITTER_NAME": "Eval", "GIT_COMMITTER_EMAIL": "eval@example.com",
    "GIT_AUTHOR_DATE": "2026-10-01T12:00:00+00:00", "GIT_COMMITTER_DATE": "2026-10-01T12:00:00+00:00",
}


@dataclass
class RepoSpec:
    name: str
    path: str
    base_sha: str
    pr_sha: str
    diff: str
    changed_files: list[str]
    categories: dict[tuple[str, int], str] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Repo sources: {name: (base_files, pr_files)}; pr_files overwrite/add.
# --------------------------------------------------------------------------

INVENTORY_BASE = {
    "inventory.py": '''"""Stock levels for a small warehouse."""


class OutOfStock(Exception):
    pass


class Inventory:
    def __init__(self):
        self._stock = {}

    def add(self, sku, qty):
        if qty <= 0:
            raise ValueError("qty must be positive")
        self._stock[sku] = self._stock.get(sku, 0) + qty

    def count(self, sku):
        return self._stock.get(sku, 0)
''',
    "test_inventory.py": '''import pytest

from inventory import Inventory


def test_add_accumulates():
    inv = Inventory()
    inv.add("apple", 2)
    inv.add("apple", 3)
    assert inv.count("apple") == 5


def test_add_rejects_non_positive():
    with pytest.raises(ValueError):
        Inventory().add("apple", 0)
''',
}

INVENTORY_PR = {
    "inventory.py": '''"""Stock levels for a small warehouse."""


class OutOfStock(Exception):
    pass


class Inventory:
    def __init__(self):
        self._stock = {}

    def add(self, sku, qty):
        if qty <= 0:
            raise ValueError("qty must be positive")
        self._stock[sku] = self._stock.get(sku, 0) + qty

    def count(self, sku):
        return self._stock.get(sku, 0)

    def remove(self, sku, qty):
        have = self._stock.get(sku, 0)
        if qty > have:
            raise OutOfStock(f"{sku}: have {have}, want {qty}")  #@exception
        if qty == have:
            del self._stock[sku]  #@stateful
        else:
            self._stock[sku] = have - qty

    def reserve(self, order):
        """Remove every line of `order` (sku -> qty), or nothing if any is short."""
        missing = [sku for sku, qty in order.items() if self.count(sku) < qty]
        if missing:
            raise OutOfStock(", ".join(sorted(missing)))  #@exception
        for sku, qty in order.items():  #@stateful
            self.remove(sku, qty)
        return sum(order.values())

    def low_stock(self, threshold):
        result = []
        for sku, qty in sorted(self._stock.items()):  #@loop
            if qty < threshold:
                result.append(sku)
        return result
''',
    "test_inventory.py": '''import pytest

from inventory import Inventory


def test_add_accumulates():
    inv = Inventory()
    inv.add("apple", 2)
    inv.add("apple", 3)
    assert inv.count("apple") == 5


def test_add_rejects_non_positive():
    with pytest.raises(ValueError):
        Inventory().add("apple", 0)


def test_remove_part_of_stock():
    inv = Inventory()
    inv.add("apple", 5)
    inv.remove("apple", 2)
    assert inv.count("apple") == 3
''',
}

TEXTKIT_BASE = {
    "textkit.py": '''"""Small text helpers."""


def slugify(text):
    return "-".join(text.lower().split())
''',
    "test_textkit.py": '''from textkit import slugify


def test_slugify():
    assert slugify("Hello  World") == "hello-world"
''',
}

TEXTKIT_PR = {
    "textkit.py": '''"""Small text helpers."""


def slugify(text):
    return "-".join(text.lower().split())


def truncate(text, limit, ellipsis="..."):
    if limit < len(ellipsis):
        raise ValueError("limit is shorter than the ellipsis")  #@exception
    if len(text) <= limit:
        return text
    return text[: limit - len(ellipsis)] + ellipsis  #@branch


def word_counts(text):
    counts = {}
    for word in text.lower().split():
        word = word.strip(".,!?;:")
        if not word:  #@loop
            continue  #@loop
        counts[word] = counts.get(word, 0) + 1
    return counts


def normalize_lines(lines, strip_blank=False):
    out = [" ".join(line.split()) for line in lines]
    if strip_blank:
        out = [line for line in out if line]  #@loop
    return out


def warn_if_long(text, limit, warnings):
    if len(text) > limit:  #@exit_arc
        warnings.append(f"text is {len(text)} chars, limit {limit}")
''',
    "test_textkit.py": '''from textkit import slugify, truncate, warn_if_long, word_counts


def test_slugify():
    assert slugify("Hello  World") == "hello-world"


def test_truncate_short_text_unchanged():
    assert truncate("hi", 10) == "hi"


def test_word_counts():
    assert word_counts("a b a") == {"a": 2, "b": 1}


def test_warn_if_long_appends():
    warnings = []
    warn_if_long("abcdef", 3, warnings)
    assert warnings == ["text is 6 chars, limit 3"]
''',
}

WEATHER_BASE = {
    "requirements.txt": "requests==2.32.3\n",
    "weather.py": '''"""Client for a small weather HTTP API."""

import requests

BASE_URL = "https://api.weather.example/v1"


def celsius_to_fahrenheit(c):
    return c * 9 / 5 + 32
''',
    "test_weather.py": '''from weather import celsius_to_fahrenheit


def test_celsius_to_fahrenheit():
    assert celsius_to_fahrenheit(100) == 212
''',
}

WEATHER_PR = {
    "requirements.txt": "requests==2.32.3\n",
    "weather.py": '''"""Client for a small weather HTTP API."""

import requests

BASE_URL = "https://api.weather.example/v1"


class WeatherError(Exception):
    pass


def celsius_to_fahrenheit(c):
    return c * 9 / 5 + 32


def current_temp(city, session=None):
    http = session or requests  #@third_party
    resp = http.get(f"{BASE_URL}/current", params={"city": city}, timeout=10)
    if resp.status_code == 404:
        raise WeatherError(f"unknown city: {city}")
    resp.raise_for_status()
    return resp.json()["temp_c"]


def forecast_range(city, days=3):
    resp = requests.get(f"{BASE_URL}/forecast", params={"city": city, "days": days}, timeout=10)  #@third_party
    resp.raise_for_status()
    temps = [d["temp_c"] for d in resp.json()["days"]]
    if not temps:
        return None
    return min(temps), max(temps)


def warmest_city(cities, session=None):
    best, best_temp = None, None
    for city in cities:
        temp = current_temp(city, session=session)  #@loop
        if best_temp is None or temp > best_temp:
            best, best_temp = city, temp
    return best
''',
    "test_weather.py": '''from unittest import mock

from weather import celsius_to_fahrenheit, warmest_city


def test_celsius_to_fahrenheit():
    assert celsius_to_fahrenheit(100) == 212


def test_warmest_city_of_none():
    assert warmest_city([], session=mock.Mock()) is None
''',
}

SCHEDULE_BASE = {
    "requirements.txt": "python-dateutil==2.9.0.post0\n",
    "schedule.py": '''"""Billing calendar helpers."""

from datetime import date


def is_weekend(d):
    return d.weekday() >= 5
''',
    "test_schedule.py": '''from datetime import date

from schedule import is_weekend


def test_is_weekend():
    assert is_weekend(date(2026, 10, 24))
    assert not is_weekend(date(2026, 10, 23))
''',
}

SCHEDULE_PR = {
    "requirements.txt": "python-dateutil==2.9.0.post0\n",
    "schedule.py": '''"""Billing calendar helpers."""

from datetime import date, timedelta

from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta


def is_weekend(d):
    return d.weekday() >= 5


def next_billing_date(start, months, day_of_month=None):
    result = start + relativedelta(months=months)
    if day_of_month is not None:
        result = result + relativedelta(day=day_of_month)  #@third_party
    return result


def parse_due(text):
    try:
        return parse_date(text).date()
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"bad due date: {text!r}") from exc  #@exception


def business_days_between(start, end):
    if end < start:
        start, end = end, start  #@branch
    days = 0
    current = start
    while current < end:
        if not is_weekend(current):
            days += 1
        current += timedelta(days=1)
    return days


class Subscription:
    def __init__(self, start, months):
        self.start = start
        self.months = months
        self.cancelled_on = None

    def cancel(self, when):
        if self.cancelled_on is not None:
            raise RuntimeError("already cancelled")  #@stateful
        if when < self.start:
            raise ValueError("cannot cancel before the start date")  #@exception
        self.cancelled_on = when

    def is_active(self, on):
        if self.cancelled_on is not None and on >= self.cancelled_on:
            return False  #@stateful
        return self.start <= on < self.start + relativedelta(months=self.months)
''',
    "test_schedule.py": '''from datetime import date

from schedule import Subscription, business_days_between, is_weekend, next_billing_date, parse_due


def test_is_weekend():
    assert is_weekend(date(2026, 10, 24))
    assert not is_weekend(date(2026, 10, 23))


def test_next_billing_date_plain():
    assert next_billing_date(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_parse_due():
    assert parse_due("2026-11-05") == date(2026, 11, 5)


def test_business_days_forward():
    assert business_days_between(date(2026, 10, 19), date(2026, 10, 26)) == 5


def test_subscription_active_and_cancel():
    sub = Subscription(date(2026, 1, 1), 12)
    assert sub.is_active(date(2026, 6, 1))
    sub.cancel(date(2026, 7, 1))
''',
}

REPOS = {
    "inventory": (INVENTORY_BASE, INVENTORY_PR),
    "textkit": (TEXTKIT_BASE, TEXTKIT_PR),
    "weather": (WEATHER_BASE, WEATHER_PR),
    "schedule": (SCHEDULE_BASE, SCHEDULE_PR),
}


def _strip_markers(path: str, text: str, categories: dict) -> str:
    lines = []
    for n, line in enumerate(text.splitlines(), start=1):
        code, mark, cat = line.partition(MARK)
        if mark:
            categories[(path, n)] = cat.strip()
        lines.append(code if mark else line)
    return "\n".join(lines) + "\n"


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout


def build_repo(out_dir: Path, name: str) -> RepoSpec:
    base, pr = REPOS[name]
    repo = out_dir / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    for path, text in base.items():
        (repo / path).write_text(_strip_markers(path, text, {}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD").strip()

    categories: dict[tuple[str, int], str] = {}
    for path, text in pr.items():
        (repo / path).write_text(_strip_markers(path, text, categories))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"{name}: new feature, partly tested")
    pr_sha = _git(repo, "rev-parse", "HEAD").strip()
    diff = _git(repo, "diff", f"{base_sha}..{pr_sha}")
    changed = sorted(p for p in pr if p.endswith(".py") and not p.startswith("test_"))
    return RepoSpec(name, str(repo), base_sha, pr_sha, diff, changed, categories)


def build_all(out_dir: Path) -> list[RepoSpec]:
    return [build_repo(out_dir, name) for name in REPOS]


if __name__ == "__main__":
    out = Path(sys.argv[1])
    for spec in build_all(out):
        print(f"### {spec.name}  base={spec.base_sha[:8]} pr={spec.pr_sha[:8]}  "
              f"{len(spec.categories)} marked gap(s)\n{spec.diff}")
