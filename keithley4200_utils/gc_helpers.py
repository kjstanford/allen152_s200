"""Gain-cell measurements for a Keithley 4200A-SCS controlled through KXCI.

The default terminal-to-SMU mapping is WWL=SMU1, WBL=SMU2, RWL=SMU3,
and RBL=SMU4. Every public measurement function returns the acquired data
as a :class:`pandas.DataFrame` and creates the plot requested by the test.
"""

from collections.abc import Mapping
import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:  # Support both package imports and running this file directly.
    from .k4200_helpers import (
        check_for_rpms,
        map_rpm_to_smu,
        switch_rpm_mode,
        wait_for_stb,
    )
except ImportError:  # pragma: no cover - used only for direct execution
    from k4200_helpers import (  # type: ignore
        check_for_rpms,
        map_rpm_to_smu,
        switch_rpm_mode,
        wait_for_stb,
    )


TERMINALS = ("WWL", "WBL", "RWL", "RBL")
DEFAULT_CHANNELS = {"WWL": 1, "WBL": 2, "RWL": 3, "RBL": 4}
DEFAULT_COMPLIANCE = 1e-3
DEFAULT_CURRENT_RANGE = "1e-6"
MAX_POINTS = 4096


def _terminal_values(value, default, value_name):
    """Broadcast a scalar or validate a terminal-keyed mapping."""
    if value is None:
        value = default
    if isinstance(value, Mapping):
        missing = set(TERMINALS) - set(value)
        if missing:
            raise ValueError(
                f"{value_name} is missing terminal(s): {', '.join(sorted(missing))}"
            )
        return {terminal: value[terminal] for terminal in TERMINALS}
    return {terminal: value for terminal in TERMINALS}


def _validate_channels(channels):
    channels = _terminal_values(channels, DEFAULT_CHANNELS, "channels")
    normalized = {}
    for terminal, channel in channels.items():
        if isinstance(channel, bool) or not isinstance(channel, (int, np.integer)):
            raise TypeError(f"Channel for {terminal} must be an integer")
        if not 1 <= int(channel) <= 9:
            raise ValueError(f"Channel for {terminal} must be between 1 and 9")
        normalized[terminal] = int(channel)
    if len(set(normalized.values())) != len(TERMINALS):
        raise ValueError("WWL, WBL, RWL, and RBL must use distinct SMU channels")
    return normalized


def _validate_state(state):
    if state not in (0, 1, False, True):
        raise ValueError("state must be 0 or 1")
    return int(state)


def _bidirectional_values(start, stop, step):
    """Return an endpoint-inclusive forward/backward list sweep."""
    start = float(start)
    stop = float(stop)
    step = float(step)
    if not all(math.isfinite(value) for value in (start, stop, step)):
        raise ValueError("Sweep voltages and step must be finite")
    if step <= 0:
        raise ValueError("step must be greater than zero")

    distance = abs(stop - start)
    if distance == 0:
        forward = np.array([start], dtype=float)
    else:
        direction = 1.0 if stop > start else -1.0
        forward = np.arange(start, stop + direction * step * 0.5, direction * step)
        if not np.isclose(forward[-1], stop):
            forward = np.append(forward, stop)
        else:
            forward[-1] = stop

    values = np.concatenate((forward, forward[::-1]))
    if len(values) > MAX_POINTS:
        raise ValueError(
            f"Bidirectional sweep has {len(values)} points; KXCI supports at most "
            f"{MAX_POINTS}"
        )
    return values, len(forward)


def _parse_kxci_data(data_string):
    """Parse comma-separated KXCI readings, including status-prefixed values."""
    values = []
    for raw_value in data_string.split(","):
        value = raw_value.strip()
        if not value:
            continue
        # System-mode readings normally start with N/C/T/X status. Timestamp
        # data may instead begin directly with a sign or digit.
        if value[0].isalpha():
            value = value[1:].strip()
        values.append(float(value))
    return values


def _get_data(my4200, name):
    return _parse_kxci_data(my4200.query(f"DO '{name}'"))


def _define_channels(my4200, channels, swept_terminal=None):
    my4200.write("DE")
    for terminal in TERMINALS:
        function = 1 if terminal == swept_terminal else 3  # VAR1 or constant
        channel = channels[terminal]
        my4200.write(f"CH{channel},'V{terminal}','I{terminal}',1,{function}")


def _set_common_smu_options(
    my4200, channels, ranges, integration_time, resolution, standby
):
    my4200.write(f"IT{integration_time}")
    my4200.write(f"RS {resolution}")
    for terminal in TERMINALS:
        channel = channels[terminal]
        my4200.write(f"RG {channel},{ranges[terminal]}")
        my4200.write(f"ST {channel},{int(bool(standby))}")


def _start_measurement(my4200, message):
    my4200.write("DR1")
    my4200.write("MD")
    print(message)
    my4200.write("ME1")
    wait_for_stb(my4200)


def _read_gc_data(my4200, voltage_terminals=(), sample_interval=None):
    columns = {
        f"V{terminal}": _get_data(my4200, f"V{terminal}")
        for terminal in voltage_terminals
    }
    for terminal in TERMINALS:
        columns[f"I{terminal}"] = _get_data(my4200, f"I{terminal}")

    if sample_interval is not None:
        number_of_samples = len(columns["IRWL"])
        # Some KXCI/firmware combinations do not respond to the documented
        # DO '<name>T' timestamp query. Use the programmed IN schedule so a
        # completed retention measurement is not lost to a VISA timeout.
        columns["Time"] = np.arange(number_of_samples) * sample_interval

    lengths = {name: len(values) for name, values in columns.items()}
    if len(set(lengths.values())) != 1:
        raise RuntimeError(f"KXCI returned columns of different lengths: {lengths}")
    return pd.DataFrame(columns)


def _configure_rpms(my4200, channels, smu_mode):
    mode = 2 if smu_mode else 0
    for channel in channels.values():
        card, rpm_channel = map_rpm_to_smu(channel)
        switch_rpm_mode(my4200, card, rpm_channel, mode)


def _turn_off_channels(my4200, channels):
    """Put all used SMUs in standby by removing them from the DE page."""
    my4200.write("DE")
    for channel in channels.values():
        my4200.write(f"CH{channel}")


def _run_constant_bias(
    my4200,
    voltages,
    hold_time,
    channels,
    compliances,
    ranges,
    integration_time,
    resolution,
):
    """Apply a constant bias stage, hold it, and leave its outputs active."""
    if hold_time < 0:
        raise ValueError("hold_time cannot be negative")

    my4200.write("BC")
    _define_channels(my4200, channels)
    my4200.write("SS")
    for terminal in TERMINALS:
        my4200.write(
            f"VC{channels[terminal]},{voltages[terminal]},{compliances[terminal]}"
        )
    my4200.write(f"HT {hold_time}")
    my4200.write("DT 0")
    # Standby is disabled so the bias is maintained into the next stage.
    _set_common_smu_options(
        my4200,
        channels,
        ranges,
        integration_time,
        resolution,
        standby=False,
    )
    my4200.write("SM")
    my4200.write("DM2")
    my4200.write("LI 'IWWL','IWBL','IRWL','IRBL'")
    my4200.write("NR 1")
    my4200.write("WT 0")
    my4200.write("IN 0.01")
    _start_measurement(my4200, f"Holding gain-cell bias for {hold_time:g} s...")


def _execute_sweep(
    my4200,
    swept_terminal,
    sweep_values,
    constant_voltages,
    channels,
    compliances,
    ranges,
    integration_time,
    hold_time,
    delay_time,
    resolution,
):
    my4200.write("BC")
    _define_channels(my4200, channels, swept_terminal=swept_terminal)
    my4200.write("SS")
    sweep_string = ",".join(f"{value:.9g}" for value in sweep_values)
    my4200.write(
        f"VL{channels[swept_terminal]},1,{compliances[swept_terminal]},"
        f"{sweep_string}"
    )
    for terminal, voltage in constant_voltages.items():
        my4200.write(f"VC{channels[terminal]},{voltage},{compliances[terminal]}")
    my4200.write(f"HT {hold_time}")
    my4200.write(f"DT {delay_time}")
    _set_common_smu_options(
        my4200,
        channels,
        ranges,
        integration_time,
        resolution,
        standby=True,
    )
    my4200.write("SM")
    my4200.write("DM2")
    my4200.write(
        f"LI 'V{swept_terminal}','IWWL','IWBL','IRWL','IRBL'"
    )
    _start_measurement(my4200, f"Executing bidirectional {swept_terminal} sweep...")
    return _read_gc_data(my4200, voltage_terminals=(swept_terminal,))


def _execute_retention_sampling(
    my4200,
    voltages,
    number_of_readings,
    sample_interval,
    channels,
    compliances,
    ranges,
    integration_time,
    resolution,
):
    my4200.write("BC")
    _define_channels(my4200, channels)
    my4200.write("SS")
    for terminal in TERMINALS:
        my4200.write(
            f"VC{channels[terminal]},{voltages[terminal]},{compliances[terminal]}"
        )
    my4200.write("HT 0")
    my4200.write("DT 0")
    _set_common_smu_options(
        my4200,
        channels,
        ranges,
        integration_time,
        resolution,
        standby=True,
    )
    my4200.write("SM")
    my4200.write("DM2")
    my4200.write("LI 'IWWL','IWBL','IRWL','IRBL'")
    my4200.write(f"NR {number_of_readings}")
    my4200.write(f"IN {sample_interval:.9g}")
    my4200.write("WT 0")
    _start_measurement(my4200, "Executing gain-cell retention sampling...")
    return _read_gc_data(my4200, sample_interval=sample_interval)


def _plot_sweep(data, x_column, forward_count, title, show_plot):
    figure, axis = plt.subplots()
    colors = {
        "RWL": "tab:blue",
        "RBL": "tab:orange",
        "WWL": "tab:green",
        "WBL": "tab:red",
    }
    for terminal in ("RWL", "RBL", "WWL", "WBL"):
        current = np.abs(data[f"I{terminal}"].to_numpy())
        voltage = data[x_column].to_numpy()
        axis.plot(
            voltage[:forward_count],
            current[:forward_count],
            color=colors[terminal],
            linestyle="-",
            label=f"|I({terminal})| forward",
        )
        axis.plot(
            voltage[forward_count:],
            current[forward_count:],
            color=colors[terminal],
            linestyle="--",
            label=f"|I({terminal})| backward",
        )
    axis.set_yscale("log")
    axis.set_xlabel(f"{x_column[1:]} voltage (V)")
    axis.set_ylabel("Absolute current (A)")
    axis.set_title(title)
    axis.grid(True, which="both", linestyle=":", linewidth=0.5)
    axis.legend()
    figure.tight_layout()
    if show_plot:
        plt.show(block=False)
        plt.pause(5)
    return figure


def _plot_retention(data, state, show_plot):
    figure, axis = plt.subplots()
    colors = {
        "RWL": "tab:blue",
        "RBL": "tab:orange",
        "WWL": "tab:green",
        "WBL": "tab:red",
    }
    for terminal in ("RWL", "RBL", "WWL", "WBL"):
        axis.plot(
            data["Time"],
            np.abs(data[f"I{terminal}"]),
            color=colors[terminal],
            label=f"|I({terminal})|",
        )
    axis.set_yscale("log")
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Absolute current (A)")
    axis.set_title(f"Gain-cell state-{state} retention")
    axis.grid(True, which="both", linestyle=":", linewidth=0.5)
    axis.legend()
    figure.tight_layout()
    if show_plot:
        plt.show(block=False)
        plt.pause(5)
    return figure


def wbl_sweep(
    my4200,
    vdata0,
    vdata1,
    vdata_step,
    vboost,
    vdd,
    vss=0.0,
    *,
    channels=None,
    compliances=None,
    current_ranges=None,
    integration_time=3,
    hold_time=0.0,
    delay_time=0.001,
    resolution=5,
    manage_rpms=True,
    show_plot=True,
):
    """Sweep WBL from ``vdata0`` to ``vdata1`` and back.

    WWL is held at ``vboost``, RWL at ``vdd``, and RBL at ``vss``.
    The returned columns are VWBL plus currents for WWL, WBL, RWL, and RBL.
    """
    channels = _validate_channels(channels)
    compliances = _terminal_values(
        compliances, DEFAULT_COMPLIANCE, "compliances"
    )
    ranges = _terminal_values(
        current_ranges, DEFAULT_CURRENT_RANGE, "current_ranges"
    )
    values, forward_count = _bidirectional_values(vdata0, vdata1, vdata_step)
    rpm_present = manage_rpms and check_for_rpms(my4200)

    try:
        if rpm_present:
            _configure_rpms(my4200, channels, smu_mode=True)
        data = _execute_sweep(
            my4200,
            "WBL",
            values,
            {"WWL": vboost, "RWL": vdd, "RBL": vss},
            channels,
            compliances,
            ranges,
            integration_time,
            hold_time,
            delay_time,
            resolution,
        )
    finally:
        _turn_off_channels(my4200, channels)
        if rpm_present:
            _configure_rpms(my4200, channels, smu_mode=False)

    data.attrs["forward_points"] = forward_count
    _plot_sweep(data, "VWBL", forward_count, "Gain-cell WBL sweep", show_plot)
    return data


def wwl_sweep(
    my4200,
    state,
    vdata0,
    vdata1,
    vhold,
    vboost,
    vwwl_step,
    vdd,
    vss=0.0,
    *,
    conditioning_time=2.0,
    channels=None,
    compliances=None,
    current_ranges=None,
    integration_time=3,
    hold_time=0.0,
    delay_time=0.001,
    resolution=5,
    manage_rpms=True,
    show_plot=True,
):
    """Condition the gain cell, then sweep WWL from hold to boost and back.

    ``state=1`` biases WBL at ``vdata1`` during the sweep; ``state=0`` uses
    ``vdata0``. The first conditioning stage always uses WBL=vdata0 exactly
    as specified by the gain-cell test sequence.
    """
    state = _validate_state(state)
    channels = _validate_channels(channels)
    compliances = _terminal_values(
        compliances, DEFAULT_COMPLIANCE, "compliances"
    )
    ranges = _terminal_values(
        current_ranges, DEFAULT_CURRENT_RANGE, "current_ranges"
    )
    values, forward_count = _bidirectional_values(vhold, vboost, vwwl_step)
    data_voltage = vdata1 if state else vdata0
    rpm_present = manage_rpms and check_for_rpms(my4200)

    try:
        if rpm_present:
            _configure_rpms(my4200, channels, smu_mode=True)
        _run_constant_bias(
            my4200,
            {"WWL": vboost, "WBL": vdata0, "RWL": vss, "RBL": vss},
            conditioning_time,
            channels,
            compliances,
            ranges,
            integration_time,
            resolution,
        )
        _run_constant_bias(
            my4200,
            {"WWL": vhold, "WBL": vdata0, "RWL": vss, "RBL": vss},
            conditioning_time,
            channels,
            compliances,
            ranges,
            integration_time,
            resolution,
        )
        data = _execute_sweep(
            my4200,
            "WWL",
            values,
            {"WBL": data_voltage, "RWL": vdd, "RBL": vss},
            channels,
            compliances,
            ranges,
            integration_time,
            hold_time,
            delay_time,
            resolution,
        )
    finally:
        _turn_off_channels(my4200, channels)
        if rpm_present:
            _configure_rpms(my4200, channels, smu_mode=False)

    data.attrs.update({"state": state, "forward_points": forward_count})
    _plot_sweep(
        data,
        "VWWL",
        forward_count,
        f"Gain-cell WWL sweep (state {state})",
        show_plot,
    )
    return data


def gc_retention_test(
    my4200,
    state,
    vdata0,
    vdata1,
    vhold,
    vboost,
    vdd,
    tretention,
    vss=0.0,
    *,
    sample_interval=1.0,
    conditioning_time=2.0,
    channels=None,
    compliances=None,
    current_ranges=None,
    integration_time=3,
    resolution=5,
    manage_rpms=True,
    show_plot=True,
):
    """Program a gain-cell state and sample its terminal currents over time.

    State 1 is programmed with WBL=vdata1 and retained with WBL=vdata0;
    state 0 is programmed with WBL=vdata0 and retained with WBL=vdata1.
    The actual interval is adjusted slightly, when needed, so the final sample
    occurs exactly at ``tretention``.
    """
    state = _validate_state(state)
    tretention = float(tretention)
    sample_interval = float(sample_interval)
    if not math.isfinite(tretention) or tretention < 0.01:
        raise ValueError("tretention must be finite and at least 0.01 s")
    if not math.isfinite(sample_interval) or not 0.01 <= sample_interval <= 10:
        raise ValueError("sample_interval must be between 0.01 and 10 s")

    interval_count = max(1, round(tretention / sample_interval))
    actual_interval = tretention / interval_count
    if not 0.01 <= actual_interval <= 10:
        raise ValueError(
            "The requested retention duration cannot be sampled within KXCI's "
            "0.01-to-10 s interval limits"
        )
    number_of_readings = interval_count + 1
    if number_of_readings > MAX_POINTS:
        raise ValueError(
            f"Retention test requires {number_of_readings} readings; KXCI "
            f"supports at most {MAX_POINTS}. Increase sample_interval."
        )

    channels = _validate_channels(channels)
    compliances = _terminal_values(
        compliances, DEFAULT_COMPLIANCE, "compliances"
    )
    ranges = _terminal_values(
        current_ranges, DEFAULT_CURRENT_RANGE, "current_ranges"
    )
    programmed_voltage = vdata1 if state else vdata0
    retention_voltage = vdata0 if state else vdata1
    rpm_present = manage_rpms and check_for_rpms(my4200)

    try:
        if rpm_present:
            _configure_rpms(my4200, channels, smu_mode=True)
        _run_constant_bias(
            my4200,
            {
                "WWL": vboost,
                "WBL": programmed_voltage,
                "RWL": vss,
                "RBL": vss,
            },
            conditioning_time,
            channels,
            compliances,
            ranges,
            integration_time,
            resolution,
        )
        _run_constant_bias(
            my4200,
            {
                "WWL": vhold,
                "WBL": programmed_voltage,
                "RWL": vss,
                "RBL": vss,
            },
            conditioning_time,
            channels,
            compliances,
            ranges,
            integration_time,
            resolution,
        )
        data = _execute_retention_sampling(
            my4200,
            {
                "WWL": vhold,
                "WBL": retention_voltage,
                "RWL": vdd,
                "RBL": vss,
            },
            number_of_readings,
            actual_interval,
            channels,
            compliances,
            ranges,
            integration_time,
            resolution,
        )
    finally:
        _turn_off_channels(my4200, channels)
        if rpm_present:
            _configure_rpms(my4200, channels, smu_mode=False)

    data.attrs.update(
        {
            "state": state,
            "retention_time": tretention,
            "sample_interval": actual_interval,
        }
    )
    _plot_retention(data, state, show_plot)
    return data


# Explicit alias makes the naming convenient in measurement notebooks.
retention_test = gc_retention_test


__all__ = ["wbl_sweep", "wwl_sweep", "gc_retention_test", "retention_test"]
