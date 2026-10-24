# Sample of verified tests, 2026-10-24

Source: `docs/evidence/eval_2026-10-24_runB.jsonl`; 78 verified gap-runs, 10 sampled with seed 20261024. Read-only: no test or lint rule was changed.

## Summary

- Tests that check a value (compares assert, pytest.raises or mock assert): **9/10**
- Checks by class: compares 16, constant 2, raises 3, truthy 2

## 1. schedule r3 `schedule.py:49-49` [exception, uncovered]

reused test from schedule.py:47 (in cancel) [uncovered]; verdict: passed and executed the target lines

Gap lines:
```python
  49              raise ValueError("cannot cancel before the start date")
```
Test:
```python
from datetime import date
import pytest
from schedule import Subscription


def test_cancel_sets_cancelled_on():
    sub = Subscription(date(2026, 1, 1), 12)
    sub.cancel(date(2026, 7, 1))
    assert sub.cancelled_on == date(2026, 7, 1)


def test_cancel_twice_raises():
    sub = Subscription(date(2026, 1, 1), 12)
    sub.cancel(date(2026, 7, 1))
    with pytest.raises(RuntimeError, match="already cancelled"):
        sub.cancel(date(2026, 8, 1))


def test_cancel_before_start_raises():
    sub = Subscription(date(2026, 1, 1), 12)
    with pytest.raises(ValueError, match="cannot cancel before the start date"):
        sub.cancel(date(2025, 12, 31))
```
Checks:

- **compares**: `assert sub.cancelled_on == date(2026, 7, 1)`
- **raises**: `pytest.raises(RuntimeError, match='already cancelled')`
- **raises**: `pytest.raises(ValueError, match='cannot cancel before the start date')`

Checks a value: **yes**

## 2. schedule r1 `schedule.py:48-48` [exception, partial_branch]

reused test from schedule.py:47 (in cancel) [uncovered]; verdict: passed and took previously missing branch(es): ['48:49']

Gap lines:
```python
  48          if when < self.start:
```
Test:
```python
from datetime import date

from schedule import Subscription


def test_cancel_sets_cancelled_on():
    sub = Subscription(date(2026, 1, 1), 12)
    sub.cancel(date(2026, 7, 1))
    assert sub.cancelled_on == date(2026, 7, 1)


def test_cancel_before_start_raises():
    sub = Subscription(date(2026, 1, 1), 12)
    try:
        sub.cancel(date(2025, 12, 31))
    except ValueError as e:
        assert str(e) == "cannot cancel before the start date"
    else:
        assert False, "expected ValueError"


def test_cancel_twice_raises():
    sub = Subscription(date(2026, 1, 1), 12)
    sub.cancel(date(2026, 7, 1))
    try:
        sub.cancel(date(2026, 8, 1))
    except RuntimeError as e:
        assert str(e) == "already cancelled"
    else:
        assert False, "expected RuntimeError"
```
Checks:

- **compares**: `assert sub.cancelled_on == date(2026, 7, 1)`
- **constant**: `assert False, 'expected ValueError'`
- **constant**: `assert False, 'expected RuntimeError'`
- **compares**: `assert str(e) == 'cannot cancel before the start date'`
- **compares**: `assert str(e) == 'already cancelled'`

Checks a value: **yes**

## 3. textkit r1 `textkit.py:21-21` [loop, uncovered]

reused test from textkit.py:20 (in word_counts) [partial_branch]; verdict: passed and executed the target lines

Gap lines:
```python
  21              continue
```
Test:
```python
from textkit import word_counts

def test_word_counts_branch_not_taken():
    # Input where stripped word becomes empty string, triggering `if not word:` to skip increment
    result = word_counts("...!")
    assert result == {}
```
Checks:

- **compares**: `assert result == {}`

Checks a value: **yes**

## 4. weather r2 `weather.py:26-31` [third_party, uncovered]

generated, nemotron-nano; verdict: passed and executed the target lines

Gap lines:
```python
  26      resp = requests.get(f"{BASE_URL}/forecast", params={"city": city, "days": days}, timeout=10)
  27      resp.raise_for_status()
  28      temps = [d["temp_c"] for d in resp.json()["days"]]
  29      if not temps:
  30          return None
  31      return min(temps), max(temps)
```
Test:
```python
import pytest
from unittest import mock

from weather import forecast_range


@mock.patch("weather.requests.get")
def test_forecast_range_returns_min_max(mock_get):
    # Arrange: mock the GET response to return a JSON payload with forecast data
    mock_resp = mock.Mock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"days": [{"temp_c": 15}, {"temp_c": 20}, {"temp_c": 10}]}
    mock_get.return_value = mock_resp

    # Act
    result = forecast_range("TestCity", days=3)

    # Assert
    assert result == (10, 20)
```
Checks:

- **compares**: `assert result == (10, 20)`

Checks a value: **yes**

## 5. inventory r1 `inventory.py:31-36` [exception+stateful, uncovered]

generated, nemotron-nano; verdict: passed and executed the target lines

Gap lines:
```python
  31          missing = [sku for sku, qty in order.items() if self.count(sku) < qty]
  32          if missing:
  33              raise OutOfStock(", ".join(sorted(missing)))
  34          for sku, qty in order.items():
  35              self.remove(sku, qty)
  36          return sum(order.values())
```
Test:
```python
import pytest
from inventory import Inventory, OutOfStock


def test_reserve_raises_out_of_stock_when_insufficient_qty():
    inv = Inventory()
    inv.add("apple", 5)
    inv.add("banana", 3)

    order = {"apple": 6, "banana": 2}  # apple quantity exceeds available stock
    with pytest.raises(OutOfStock) as excinfo:
        inv.reserve(order)

    assert "apple" in str(excinfo.value)
    assert "banana" not in str(excinfo.value)  # only missing items are listed


def test_reserve_successfully_reserves_all_items_and_returns_total_qty():
    inv = Inventory()
    inv.add("apple", 10)
    inv.add("banana", 4)

    order = {"apple": 7, "banana": 3}
    result = inv.reserve(order)

    assert result == 10  # 7 + 3
    assert inv.count("apple") == 3  # 10 - 7
    assert inv.count("banana") == 1  # 4 - 3
```
Checks:

- **compares**: `assert 'apple' in str(excinfo.value)`
- **compares**: `assert 'banana' not in str(excinfo.value)`
- **compares**: `assert result == 10`
- **compares**: `assert inv.count('apple') == 3`
- **compares**: `assert inv.count('banana') == 1`
- **raises**: `pytest.raises(OutOfStock)`

Checks a value: **yes**

## 6. schedule r1 `schedule.py:53-53` [stateful, partial_branch]

generated, nemotron-super; verdict: passed and took previously missing branch(es): ['53:54']

Gap lines:
```python
  53          if self.cancelled_on is not None and on >= self.cancelled_on:
```
Test:
```python
from datetime import date
from schedule import Subscription

def test_is_active_cancelled_branch():
    sub = Subscription(date(2026, 1, 1), 12)
    cancel_date = date(2026, 7, 1)
    sub.cancel(cancel_date)
    # When checking on the cancellation date or later, the subscription should be inactive
    assert not sub.is_active(cancel_date)
    assert not sub.is_active(date(2026, 8, 1))
```
Checks:

- **truthy**: `assert not sub.is_active(cancel_date)`
- **truthy**: `assert not sub.is_active(date(2026, 8, 1))`

Checks a value: **NO**

## 7. weather r3 `weather.py:37-39` [loop, uncovered]

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


def test_warmest_city_takes_other_branch():
    # Mock current_temp to return a temperature that would be greater than any existing best_temp
    # This forces the condition `temp > best_temp` to be true, taking the other branch of the if statement.
    with mock.patch("weather.current_temp", return_value=30):
        result = warmest_city(["city1", "city2"])
        assert result == "city1"
```
Checks:

- **compares**: `assert result == 'city1'`

Checks a value: **yes**

## 8. textkit r1 `textkit.py:13-13` [branch, uncovered]

reused test from textkit.py:11 (in truncate) [partial_branch]; verdict: passed and executed the target lines

Gap lines:
```python
  13      return text[: limit - len(ellipsis)] + ellipsis
```
Test:
```python
from textkit import truncate

def test_truncate_ellipsis_branch_taken():
    # When text length exceeds limit, the ellipsis branch should be executed.
    text = "abcdefgh"
    limit = 5
    ellipsis = "..."
    # Since len(text)=8 > limit=5, we expect truncation with ellipsis.
    # limit - len(ellipsis) = 5 - 3 = 2, so text[:2] = "ab", then add ellipsis -> "ab..."
    expected = "ab..."
    assert truncate(text, limit, ellipsis) == expected
```
Checks:

- **compares**: `assert truncate(text, limit, ellipsis) == expected`

Checks a value: **yes**

## 9. textkit r1 `textkit.py:34-34` [exit_arc, partial_branch]

generated, nemotron-super; verdict: passed and took previously missing branch(es): ['34:exit']

Gap lines:
```python
  34      if len(text) > limit:
```
Test:
```python
from textkit import warn_if_long

def test_warn_if_long_no_warning_when_within_limit():
    warnings = []
    result = warn_if_long("short", 10, warnings)
    assert result is None
    assert warnings == []
```
Checks:

- **compares**: `assert result is None`
- **compares**: `assert warnings == []`

Checks a value: **yes**

## 10. schedule r2 `schedule.py:16-16` [third_party, uncovered]

reused test from schedule.py:15 (in next_billing_date) [partial_branch]; verdict: passed and executed the target lines

Gap lines:
```python
  16          result = result + relativedelta(day=day_of_month)
```
Test:
```python
from datetime import date
from schedule import next_billing_date

def test_next_billing_date_day_of_month_branch():
    # Call with day_of_month not None to hit the if branch at line 15
    start = date(2026, 1, 15)
    months = 1
    day_of_month = 5

    # start + 1 month -> 2026-02-15, then set day to 5 -> 2026-02-05
    expected = date(2026, 2, 5)

    assert next_billing_date(start, months, day_of_month) == expected
```
Checks:

- **compares**: `assert next_billing_date(start, months, day_of_month) == expected`

Checks a value: **yes**

