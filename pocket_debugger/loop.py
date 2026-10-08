"""4-20 mA engineering calculations. These functions do not control hardware."""

import math


def finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def namur_status(current_ma):
    """Classify a loop current against the NAMUR NE 43 signal levels.

    NE 43 reserves 3.8-20.5 mA for the measuring range, treats 3.6-3.8 mA and
    20.5-21.0 mA as saturation, and defines below 3.6 mA or above 21.0 mA as a
    transmitter failure signal. The thresholds are the recommendation's nominal
    values; a specific transmitter may use its own configured failure current.
    """
    current_ma = finite_number(current_ma, "Current")
    if current_ma < 3.6:
        return "failure_low"
    if current_ma < 3.8:
        return "saturated_low"
    if current_ma <= 20.5:
        return "measuring"
    if current_ma <= 21.0:
        return "saturated_high"
    return "failure_high"


def scale_current(current_ma, low=0.0, high=100.0, unit="%"):
    current_ma = finite_number(current_ma, "Current")
    low, high = finite_number(low, "Lower range"), finite_number(high, "Upper range")
    if low >= high:
        raise ValueError("Upper range must exceed lower range")
    if not isinstance(unit, str) or len(unit) > 32:
        raise ValueError("Unit must be text of at most 32 characters")
    fraction = (current_ma - 4.0) / 16.0
    engineering = low + fraction * (high - low)
    if not math.isfinite(engineering) or not math.isfinite(100.0 * fraction):
        raise ValueError("Derived scaling values exceed the finite numeric range")
    return {
        "current_ma": current_ma, "percent": 100.0 * fraction,
        "engineering_value": engineering,
        "low": low, "high": high, "unit": unit,
        "range_status": "below_range" if current_ma < 4 else
                        "above_range" if current_ma > 20 else "in_range",
        "namur_status": namur_status(current_ma),
    }


def current_from_shunt(voltage_mv, resistance_ohm):
    voltage_mv = finite_number(voltage_mv, "Shunt voltage")
    resistance_ohm = finite_number(resistance_ohm, "Shunt resistance")
    if resistance_ohm <= 0:
        raise ValueError("Shunt resistance must be positive")
    return voltage_mv / resistance_ohm
