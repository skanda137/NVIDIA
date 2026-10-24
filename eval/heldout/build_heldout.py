"""
Deterministically build the held-out repos under $HOME/heldout-repos/<name>/.

    python3 build_heldout.py            # refuses to overwrite an existing repo

Each repo has exactly two commits: "base" (library code + a pytest suite that passes
offline) and "head" (6-8 new functions or methods, no new tests). Repos 1-3 declare
their third-party dependency in requirements.txt; repo 4 (cfgload, a probe) declares it
only in pyproject.toml. Fixed author, committer and dates, so SHAs are reproducible.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

OUT = Path.home() / "heldout-repos"
GIT = ["git", "-c", "user.name=x", "-c", "user.email=x@x.x"]
DATES = {"GIT_AUTHOR_DATE": "2026-10-20T10:00:00+00:00", "GIT_COMMITTER_DATE": "2026-10-20T10:00:00+00:00"}

# ---------------------------------------------------------------------------
# 1. ledger: python-dateutil. File I/O, stateful class, dates, validation.
# ---------------------------------------------------------------------------
LEDGER_BASE = {
    "ledger.py": '''"""A small personal ledger."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Entry:
    when: date
    amount: Decimal
    memo: str = ""


def parse_amount(text):
    """'12.50' -> Decimal('12.50'); '(3.00)' -> Decimal('-3.00')."""
    text = text.strip().replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"not an amount: {text!r}")
    return -value if negative else value
''',
    "test_ledger.py": '''from decimal import Decimal

import pytest

from ledger import parse_amount


def test_parse_plain():
    assert parse_amount("12.50") == Decimal("12.50")


def test_parse_parentheses_negative():
    assert parse_amount("(3.00)") == Decimal("-3.00")


def test_parse_thousands_separator():
    assert parse_amount("1,200") == Decimal("1200")


def test_parse_rejects_text():
    with pytest.raises(ValueError):
        parse_amount("abc")
''',
}
LEDGER_HEAD = {
    "requirements.txt": "python-dateutil==2.9.0.post0\n",
    "ledger.py": LEDGER_BASE["ledger.py"].replace(
        '''from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
''', '''import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from dateutil.parser import isoparse
from dateutil.relativedelta import relativedelta
''') + '''

def load_entries(path):
    """Read a CSV with columns date,amount,memo. Blank lines are skipped."""
    entries = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if not any(row.values()):
                continue
            entries.append(Entry(isoparse(row["date"]).date(), parse_amount(row["amount"]), row.get("memo", "")))
    return entries


def save_entries(path, entries):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "amount", "memo"])
        for e in entries:
            writer.writerow([e.when.isoformat(), str(e.amount), e.memo])


class Ledger:
    def __init__(self, opening_balance=Decimal("0")):
        self.opening_balance = Decimal(opening_balance)
        self._entries = []

    def add(self, entry):
        if not isinstance(entry.amount, Decimal):
            raise TypeError("amount must be a Decimal")
        if entry.amount == 0:
            raise ValueError("zero-amount entries are not allowed")
        self._entries.append(entry)
        self._entries.sort(key=lambda e: e.when)

    def balance(self, on=None):
        total = self.opening_balance
        for e in self._entries:
            if on is not None and e.when > on:
                break
            total += e.amount
        return total

    def monthly_totals(self):
        """{(year, month): net amount} for every month that has entries."""
        totals = {}
        for e in self._entries:
            key = (e.when.year, e.when.month)
            totals[key] = totals.get(key, Decimal("0")) + e.amount
        return totals


def next_due(start, months, today):
    """First date start + k*months (k >= 0) that is on or after today."""
    if months < 1:
        raise ValueError("months must be at least 1")
    due, k = start, 0
    while due < today:
        k += 1
        due = start + relativedelta(months=months * k)
    return due
''',
}

# ---------------------------------------------------------------------------
# 2. ratefeed: requests behind an injectable getter. Stateful cache, regex, file I/O.
# ---------------------------------------------------------------------------
RATEFEED_BASE = {
    "ratefeed.py": '''"""Currency conversion helpers."""

from decimal import ROUND_HALF_UP, Decimal


def round_money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def convert(amount, rate):
    if rate <= 0:
        raise ValueError("rate must be positive")
    return round_money(Decimal(str(amount)) * Decimal(str(rate)))
''',
    "test_ratefeed.py": '''from decimal import Decimal

import pytest

from ratefeed import convert, round_money


def test_round_money_half_up():
    assert round_money("2.345") == Decimal("2.35")


def test_convert():
    assert convert(10, 1.5) == Decimal("15.00")


def test_convert_rejects_non_positive_rate():
    with pytest.raises(ValueError):
        convert(10, 0)
''',
}
RATEFEED_HEAD = {
    "requirements.txt": "requests==2.32.3\n",
    "ratefeed.py": RATEFEED_BASE["ratefeed.py"].replace(
        '''from decimal import ROUND_HALF_UP, Decimal
''', '''import json
import re
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import requests

API = "https://rates.example.com/v2/latest"
CODE = re.compile(r"^[A-Z]{3}$")
''') + '''

class RateError(Exception):
    pass


def fetch_rates(base, get=requests.get):
    """{code: rate} relative to `base`, from the rates API."""
    if not CODE.match(base):
        raise ValueError(f"bad currency code: {base!r}")
    resp = get(API, params={"base": base}, timeout=10)
    if resp.status_code == 429:
        raise RateError("rate limited, try again later")
    resp.raise_for_status()
    data = resp.json()
    return {code: float(rate) for code, rate in data["rates"].items() if CODE.match(code)}


def parse_rate_line(line):
    """'EUR/USD 1.0832' -> ('EUR', 'USD', 1.0832)."""
    m = re.match(r"^\\s*([A-Z]{3})/([A-Z]{3})\\s+(\\d+(?:\\.\\d+)?)\\s*$", line)
    if not m:
        raise ValueError(f"unparseable rate line: {line!r}")
    return m.group(1), m.group(2), float(m.group(3))


def best_rate(quotes, target):
    """Highest rate for `target` among quotes [(source, {code: rate})]; None if no source quotes it."""
    best = None
    for source, rates in quotes:
        rate = rates.get(target)
        if rate is None:
            continue
        if best is None or rate > best[1]:
            best = (source, rate)
    return best


class RateCache:
    def __init__(self, ttl_seconds=300, fetch=fetch_rates, clock=datetime.now):
        self.ttl = timedelta(seconds=ttl_seconds)
        self._fetch, self._clock = fetch, clock
        self._entries = {}
        self.misses = 0

    def get(self, base):
        cached = self._entries.get(base)
        now = self._clock()
        if cached is not None and now - cached[0] < self.ttl:
            return cached[1]
        self.misses += 1
        rates = self._fetch(base)
        self._entries[base] = (now, rates)
        return rates

    def invalidate(self, base=None):
        if base is None:
            self._entries.clear()
        else:
            self._entries.pop(base, None)


def save_rates(path, rates):
    with open(path, "w") as f:
        json.dump({k: rates[k] for k in sorted(rates)}, f, indent=2)


def load_rates(path):
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("rates file must contain a JSON object")
    return {k: float(v) for k, v in data.items()}
''',
}

# ---------------------------------------------------------------------------
# 3. logscan: humanize. Regex, file I/O, branch in a loop, datetime, errors.
# ---------------------------------------------------------------------------
LOGSCAN_BASE = {
    "logscan.py": '''"""Parse simple application logs: '2026-10-01T12:00:00 LEVEL message'."""

import re

LINE = re.compile(r"^(\\S+)\\s+(DEBUG|INFO|WARNING|ERROR)\\s+(.*)$")
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def parse_line(line):
    m = LINE.match(line.rstrip("\\n"))
    if not m:
        return None
    return {"ts": m.group(1), "level": m.group(2), "message": m.group(3)}
''',
    "test_logscan.py": '''from logscan import parse_line


def test_parse_line():
    assert parse_line("2026-10-01T12:00:00 INFO started\\n") == {
        "ts": "2026-10-01T12:00:00", "level": "INFO", "message": "started"}


def test_parse_line_rejects_garbage():
    assert parse_line("not a log line") is None
''',
}
LOGSCAN_HEAD = {
    "requirements.txt": "humanize==4.11.0\n",
    "logscan.py": LOGSCAN_BASE["logscan.py"].replace(
        '''import re
''', '''import os
import re
from collections import Counter
from datetime import datetime

import humanize
''') + '''

def read_log(path):
    """Parsed records of a log file; unparseable lines are counted, not returned."""
    records, bad = [], 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            rec = parse_line(line)
            if rec is None:
                bad += 1
            else:
                records.append(rec)
    return records, bad


def level_counts(records, min_level="DEBUG"):
    if min_level not in LEVELS:
        raise ValueError(f"unknown level: {min_level}")
    floor = LEVELS.index(min_level)
    return Counter(r["level"] for r in records if LEVELS.index(r["level"]) >= floor)


def first_error(records):
    for r in records:
        if r["level"] == "ERROR":
            return r
    return None


def span(records):
    """Human-readable time between the first and last record, e.g. '2 hours'."""
    if len(records) < 2:
        return "no span"
    start = datetime.fromisoformat(records[0]["ts"])
    end = datetime.fromisoformat(records[-1]["ts"])
    if end < start:
        raise ValueError("records are not in time order")
    return humanize.naturaldelta(end - start)


def grep(records, pattern, ignore_case=False):
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        raise ValueError(f"bad pattern {pattern!r}: {exc}") from exc
    return [r for r in records if rx.search(r["message"])]


def describe_file(path):
    """'app.log: 1.2 kB, 40 records (2 unparseable)'."""
    size = humanize.naturalsize(os.path.getsize(path))
    records, bad = read_log(path)
    suffix = f" ({bad} unparseable)" if bad else ""
    return f"{os.path.basename(path)}: {size}, {len(records)} records{suffix}"


class TailState:
    """Remembers how far a log has been read, across calls."""

    def __init__(self, path):
        self.path = path
        self.offset = 0

    def read_new(self):
        with open(self.path, encoding="utf-8") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() < self.offset:  # file was truncated or rotated
                self.offset = 0
            f.seek(self.offset)
            lines = f.readlines()
            self.offset = f.tell()
        return [rec for rec in map(parse_line, lines) if rec is not None]
''',
}

# ---------------------------------------------------------------------------
# 4. cfgload (probe): PyYAML declared only in pyproject.toml, no requirements.txt.
# ---------------------------------------------------------------------------
CFGLOAD_BASE = {
    "pyproject.toml": '''[project]
name = "cfgload"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = []
''',
    "cfgload.py": '''"""Layered configuration: defaults, then files, then environment overrides."""


def merge(base, override):
    """Recursive dict merge; values in `override` win."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out
''',
    "test_cfgload.py": '''from cfgload import merge


def test_merge_nested():
    assert merge({"db": {"host": "a", "port": 1}}, {"db": {"port": 2}}) == {"db": {"host": "a", "port": 2}}


def test_merge_replaces_non_dict():
    assert merge({"x": 1}, {"x": {"y": 2}}) == {"x": {"y": 2}}
''',
}
CFGLOAD_HEAD = {
    "pyproject.toml": CFGLOAD_BASE["pyproject.toml"].replace('dependencies = []', 'dependencies = ["PyYAML>=6.0"]'),
    "cfgload.py": CFGLOAD_BASE["cfgload.py"].replace(
        '''"""Layered configuration: defaults, then files, then environment overrides."""
''', '''"""Layered configuration: defaults, then files, then environment overrides."""

import os

import yaml
''') + '''

class ConfigError(Exception):
    pass


def load_file(path):
    with open(path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def env_overrides(prefix, environ=None):
    """APP_DB__PORT=5432 -> {"db": {"port": 5432}} for prefix 'APP_'."""
    environ = os.environ if environ is None else environ
    out = {}
    for key, raw in environ.items():
        if not key.startswith(prefix):
            continue
        path = key[len(prefix):].lower().split("__")
        node = out
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = yaml.safe_load(raw)
    return out


def get_path(config, dotted, default=None):
    node = config
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def require(config, *dotted):
    missing = [d for d in dotted if get_path(config, d) is None]
    if missing:
        raise ConfigError("missing required settings: " + ", ".join(missing))


def load(defaults, paths, prefix="APP_", environ=None):
    config = dict(defaults)
    for path in paths:
        if os.path.exists(path):
            config = merge(config, load_file(path))
    return merge(config, env_overrides(prefix, environ))


def dump(config, path):
    with open(path, "w") as f:
        yaml.safe_dump(config, f, sort_keys=True)
''',
}

REPOS = {
    "ledger": (LEDGER_BASE, LEDGER_HEAD),
    "ratefeed": (RATEFEED_BASE, RATEFEED_HEAD),
    "logscan": (LOGSCAN_BASE, LOGSCAN_HEAD),
    "cfgload": (CFGLOAD_BASE, CFGLOAD_HEAD),
}


def git(repo, *args):
    env = {**os.environ, **DATES}
    return subprocess.run([*GIT, *args], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout


def build(name, base, head):
    repo = OUT / name
    if repo.exists():
        sys.exit(f"{repo} already exists; remove it first (refusing to overwrite)")
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    for path, text in base.items():
        (repo / path).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    for path, text in head.items():
        (repo / path).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "head")
    return repo


if __name__ == "__main__":
    for name, (base, head) in REPOS.items():
        print(f"built {build(name, base, head)}")
