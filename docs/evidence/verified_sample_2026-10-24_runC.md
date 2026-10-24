# Sample of verified tests, 2026-10-24

Source: `docs/evidence/eval_2026-10-24_runC.jsonl`; 87 verified gap-runs, 10 sampled with seed 20261024. Read-only: no test or lint rule was changed.

## Summary

- Tests that check a value (compares assert, pytest.raises or mock assert): **10/10**
- Checks by class: compares 8, constant 1, raises 2

## 1. weather r3 `weather.py:37-39` [loop, uncovered]

reused test from weather.py:36 (in warmest_city) [partial_branch]; verdict: passed and executed the target lines

Gap lines:
```python
  37          temp = current_temp(city, session=session)
  38          if best_temp is None or temp > best_temp:
  39              best, best_temp = city, temp
```
Test:
```python
from unittest import mock

from weather import warmest_city


def test_warmest_city_takes_first_branch_side():
    # Mock current_temp to return a temperature that will be compared
    # Ensure that the condition `temp > best_temp` evaluates to True on the first iteration
    # This forces the branch from line 36 to line 37 to be taken
    with mock.patch("weather.current_temp", return_value=30.0):
        cities = ["CityA", "CityB"]
        result = warmest_city(cities)
        assert result == "CityA"
```
Checks:

- **compares**: `assert result == 'CityA'`

Checks a value: **yes**

## 2. schedule r1 `schedule.py:29-29` [branch, uncovered]

reused test from schedule.py:28 (in business_days_between) [partial_branch]; verdict: passed and executed the target lines

Gap lines:
```python
  29          start, end = end, start
```
Test:
```python
from datetime import date, timedelta

from schedule import business_days_between, is_weekend


def test_business_days_between_swaps_start_and_end():
    # Force the branch at line 28-29 to be taken by making end < start
    start = date(2026, 10, 26)  # Friday
    end = date(2026, 10, 19)   # Friday earlier in the week
    # Expected result: business days between 2026-10-19 and 2026-10-26 = 5
    assert business_days_between(start, end) == 5
```
Checks:

- **compares**: `assert business_days_between(start, end) == 5`

Checks a value: **yes**

## 3. textkit r1 `textkit.py:13-13` [branch, uncovered]

reused test from textkit.py:11 (in truncate) [partial_branch]; verdict: passed and executed the target lines

Gap lines:
```python
  13      return text[: limit - len(ellipsis)] + ellipsis
```
Test:
```python
from textkit import truncate

def test_truncate_long_text_takes_else_branch():
    # Force the else branch of the condition at line 11 (len(text) > limit)
    # Ensure limit is not shorter than the ellipsis to avoid early ValueError.
    assert truncate("hello world", 5) == "he..."
```
Checks:

- **compares**: `assert truncate('hello world', 5) == 'he...'`

Checks a value: **yes**

## 4. textkit r2 `textkit.py:20-20` [loop, partial_branch]

generated, nemotron-super; verdict: passed and took previously missing branch(es): ['20:21']

Gap lines:
```python
  20          if not word:
```
Test:
```python
from textkit import word_counts

def test_word_counts_skips_empty_after_strip():
    # Tokens: "hello", "!!", "world" -> after strip punctuation: "hello", "", "world"
    # The empty token should trigger the `if not word:` branch and be skipped.
    result = word_counts("hello !! world")
    assert result == {"hello": 1, "world": 1}
```
Checks:

- **compares**: `assert result == {'hello': 1, 'world': 1}`

Checks a value: **yes**

## 5. schedule r3 `schedule.py:48-48` [exception, partial_branch]

generated, nemotron-nano; verdict: passed and took previously missing branch(es): ['48:49']

Gap lines:
```python
  48          if when < self.start:
```
Test:
```python
import pytest
from datetime import date

from schedule import Subscription


def test_cancel_before_start_raises_value_error():
    # Arrange: create a subscription that starts in the future
    start_date = date(2026, 12, 1)  # future date
    sub = Subscription(start_date, 12)  # 12-month subscription

    # Act & Assert: calling cancel() with a date before the start should raise ValueError
    with pytest.raises(ValueError, match="cannot cancel before the start date"):
        sub.cancel(date(2026, 11, 15))  # when is before start -> triggers the uncaptured branch
```
Checks:

- **raises**: `pytest.raises(ValueError, match='cannot cancel before the start date')`

Checks a value: **yes**

## 6. inventory r1 `inventory.py:24-24` [stateful, partial_branch]

generated, nemotron-nano; verdict: passed and took previously missing branch(es): ['24:25']

Gap lines:
```python
  24          if qty == have:
```
Test:
```python
import pytest
from inventory import Inventory, OutOfStock


def test_remove_exact_quantity_deletes_stock():
    inv = Inventory()
    inv.add("widget", 10)
    # This call triggers the branch at line 24 (qty == have)
    inv.remove("widget", 10)
    # After removal, the SKU should no longer exist in stock
    assert "widget" not in inv._stock
```
Checks:

- **compares**: `assert 'widget' not in inv._stock`

Checks a value: **yes**

## 7. schedule r1 `schedule.py:47-47` [stateful, uncovered]

reused test from schedule.py:46 (in cancel) [partial_branch]; verdict: passed and executed the target lines

Gap lines:
```python
  47              raise RuntimeError("already cancelled")
```
Test:
```python
import pytest
from datetime import date
from schedule import Subscription


def test_cancel_raises_runtime_error_when_cancelled_on_is_not_none():
    # Arrange: create a Subscription and cancel it once so cancelled_on is set
    sub = Subscription(date(2026, 1, 1), 12)
    sub.cancel(date(2026, 7, 1))  # sets cancelled_on

    # Act & Assert: calling cancel again should raise RuntimeError
    with pytest.raises(RuntimeError, match="already cancelled"):
        sub.cancel(date(2026, 8, 1))
```
Checks:

- **raises**: `pytest.raises(RuntimeError, match='already cancelled')`

Checks a value: **yes**

## 8. textkit r3 `textkit.py:13-13` [branch, uncovered]

reused test from textkit.py:11 (in truncate) [partial_branch]; verdict: passed and executed the target lines

Gap lines:
```python
  13      return text[: limit - len(ellipsis)] + ellipsis
```
Test:
```python
from textkit import truncate

def test_truncate_long_text_returns_ellipsis():
    # Force the branch where len(text) > limit (line 11 -> line 13)
    assert truncate("hello world", 8) == "hello..."
```
Checks:

- **compares**: `assert truncate('hello world', 8) == 'hello...'`

Checks a value: **yes**

## 9. textkit r1 `textkit.py:10-10` [exception, uncovered]

reused test from textkit.py:9 (in truncate) [partial_branch]; verdict: passed and executed the target lines

Gap lines:
```python
  10          raise ValueError("limit is shorter than the ellipsis")
```
Test:
```python
from textkit import truncate

def test_truncate_limit_shorter_than_ellipsis_raises():
    try:
        truncate("hello", 2, ellipsis="...")
    except ValueError as e:
        assert str(e) == "limit is shorter than the ellipsis"
    else:
        assert False, "Expected ValueError"
```
Checks:

- **constant**: `assert False, 'Expected ValueError'`
- **compares**: `assert str(e) == 'limit is shorter than the ellipsis'`

Checks a value: **yes**

## 10. textkit r3 `textkit.py:34-34` [exit_arc, partial_branch]

generated, nemotron-super; verdict: passed and took previously missing branch(es): ['34:exit']

Gap lines:
```python
  34      if len(text) > limit:
```
Test:
```python
from textkit import warn_if_long

def test_warn_if_long_no_warning():
    warnings = []
    warn_if_long("short", 10, warnings)
    assert warnings == []
```
Checks:

- **compares**: `assert warnings == []`

Checks a value: **yes**

