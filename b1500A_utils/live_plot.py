"""
Live Plotting for IV Curve Measurements
=========================================

How live plotting works
-----------------------
The B1500A staircase sweep mode collects all data points on the instrument and
returns them in one block when the sweep is done.  True point-by-point streaming
is not available through the pymeasure driver.

Instead, "live" here means the plot updates after every completed sub-sweep —
i.e. after each (Vd, cycle) pair — rather than once at the very end.  For a
typical multi-Vd run this means you see each curve appear on screen as it is
measured, which gives immediate feedback on device behaviour.

The mechanism:
    1. plt.ion() puts matplotlib into interactive (non-blocking) mode.
    2. A LivePlotter instance owns the figure and a set of Axes, one per
       requested quantity.
    3. After each IdVg_single_Vd / IdVd_single_Vg call returns a DataFrame,
       LivePlotter.update(data, label) is called to add/refresh the
       corresponding Line2D objects on each axis.
    4. fig.canvas.flush_events() + plt.pause(0.01) hands control back to the
       GUI event loop just long enough to render the new data, then returns
       immediately so the next sweep can begin.
    5. At the end, LivePlotter.freeze() turns off interactive mode and calls
       plt.show(block=True) so the window stays open.

Wrapper functions (live_IdVg_single_Vd, live_IdVg_multi_Vd, etc.) mirror the
signatures in FET_three_terminal.py and simply call the library function, then
call plotter.update().  The main script uses these wrappers instead of the
library functions directly.

Quantities that can be plotted
-------------------------------
Specify what to display by passing a list of plot_spec dicts to LivePlotter.
Each dict has the following keys:

    title       str     Subplot title
    xlabel      str     X-axis label
    ylabel      str     Y-axis label
    yscale      str     'log' or 'linear'
    abs         bool    Take absolute value of y before plotting (default False)

    -- choose exactly one of the following --
    y           str     Column name from the DataFrame to plot directly.
                        Valid column names: 'Drain_Current', 'Gate_Current',
                        'Source_Current', 'Gate_Voltage', 'Drain_Voltage'
    derived     str     Compute a quantity from the DataFrame on the fly.
                        Options:
                          'gm'   Transconductance dId/dVg  (S)
                          'SS'   Subthreshold swing dVg/d(log10|Id|) (mV/dec)
                          'gd'   Output conductance dId/dVd  (S)

    x           str     Column name to use as the x-axis (default 'Gate_Voltage'
                        for IdVg plots, 'Drain_Voltage' for IdVd plots)

Pre-built presets (use directly or as starting points):
    PRESET_ID_LOG    |Id| vs Vg, log scale
    PRESET_IG_LOG    |Ig| vs Vg, log scale
    PRESET_ID_LIN    Id vs Vg, linear scale
    PRESET_GM        gm vs Vg, linear scale
    PRESET_SS        Subthreshold swing vs Vg, linear scale
    PRESET_IDVD      Id vs Vd, linear scale
    PRESET_GD        gd vs Vd, linear scale

Example usage
-------------
    from b1500A_utils.live_plot import LivePlotter, live_IdVg_multi_Vd
    from b1500A_utils.live_plot import PRESET_ID_LOG, PRESET_IG_LOG, PRESET_GM

    plotter = LivePlotter([PRESET_ID_LOG, PRESET_IG_LOG, PRESET_GM])

    data = live_IdVg_multi_Vd(
        plotter=plotter,
        b1500=myb1500,
        smu_gate=smu_gate,
        smu_drain=smu_drain,
        smu_source=smu_source,
        gate_start=-3.0,
        gate_stop=3.0,
        gate_step=0.025,
        drain_list=[0.05, 1.0],
        Irange='1 nA limited auto ranging',
        Vrange='2 V limited auto ranging',
    )

    plotter.freeze()   # keeps the window open after all sweeps finish
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from b1500A_utils.FET_three_terminal import (
    IdVg_single_Vd,
    IdVg_multi_Vd,
    IdVg_multi_Vd_multi_cycle,
    IdVd_single_Vg,
    IdVd_multi_Vg,
    IdVd_multi_Vg_multi_cycle,
)

# ---------------------------------------------------------------------------
# Pre-built plot presets
# ---------------------------------------------------------------------------

PRESET_ID_LOG = {
    'title':  '|Id| vs Vg',
    'x':      'Gate_Voltage',
    'y':      'Drain_Current',
    'abs':    True,
    'yscale': 'log',
    'xlabel': 'Vg (V)',
    'ylabel': '|Id| (A)',
}

PRESET_IG_LOG = {
    'title':  '|Ig| vs Vg',
    'x':      'Gate_Voltage',
    'y':      'Gate_Current',
    'abs':    True,
    'yscale': 'log',
    'xlabel': 'Vg (V)',
    'ylabel': '|Ig| (A)',
}

PRESET_ID_LIN = {
    'title':  'Id vs Vg',
    'x':      'Gate_Voltage',
    'y':      'Drain_Current',
    'abs':    False,
    'yscale': 'linear',
    'xlabel': 'Vg (V)',
    'ylabel': 'Id (A)',
}

PRESET_GM = {
    'title':   'Transconductance gm vs Vg',
    'x':       'Gate_Voltage',
    'derived': 'gm',
    'yscale':  'linear',
    'xlabel':  'Vg (V)',
    'ylabel':  'gm (S)',
}

PRESET_SS = {
    'title':   'Subthreshold Swing vs Vg',
    'x':       'Gate_Voltage',
    'derived': 'SS',
    'yscale':  'linear',
    'xlabel':  'Vg (V)',
    'ylabel':  'SS (mV/dec)',
}

PRESET_IDVD = {
    'title':  'Id vs Vd',
    'x':      'Drain_Voltage',
    'y':      'Drain_Current',
    'abs':    False,
    'yscale': 'linear',
    'xlabel': 'Vd (V)',
    'ylabel': 'Id (A)',
}

PRESET_GD = {
    'title':   'Output conductance gd vs Vd',
    'x':       'Drain_Voltage',
    'derived': 'gd',
    'yscale':  'linear',
    'xlabel':  'Vd (V)',
    'ylabel':  'gd (S)',
}


# ---------------------------------------------------------------------------
# LivePlotter class
# ---------------------------------------------------------------------------

class LivePlotter:
    """
    Manages a live-updating matplotlib figure with one subplot per requested
    quantity.  Call update(data, label) after each sweep to add a new curve.
    Call freeze() when all measurements are done to keep the window open.

    Parameters
    ----------
    plot_specs : list[dict]
        One dict per subplot.  See module docstring for the full key reference
        and the PRESET_* constants for ready-made examples.
    figsize_per_panel : tuple, optional
        Width and height in inches for each subplot panel (default (5.5, 4.5)).
    """

    def __init__(self, plot_specs, figsize_per_panel=(5.5, 4.5)):
        self.plot_specs = plot_specs
        self._lines = [{} for _ in plot_specs]   # label -> Line2D per panel

        n = len(plot_specs)
        fig_w = figsize_per_panel[0] * n
        fig_h = figsize_per_panel[1]

        plt.ion()
        self.fig, axes = plt.subplots(1, n, figsize=(fig_w, fig_h))
        self.axes = [axes] if n == 1 else list(axes)

        for ax, spec in zip(self.axes, plot_specs):
            ax.set_title(spec.get('title', ''))
            ax.set_xlabel(spec.get('xlabel', spec.get('x', '')))
            ax.set_ylabel(spec.get('ylabel', spec.get('y', spec.get('derived', ''))))
            if spec.get('yscale') == 'log':
                ax.set_yscale('log')
            ax.grid(True, which='both' if spec.get('yscale') == 'log' else 'major')

        self.fig.tight_layout()
        self.fig.canvas.draw()
        plt.pause(0.01)

    def update(self, data, label=None):
        """
        Add or refresh curves on all panels using the supplied DataFrame.

        Parameters
        ----------
        data : pd.DataFrame
            Output of any IdVg_* or IdVd_* function.  Must contain at minimum
            the columns referenced by the plot_specs passed at construction.
        label : str, optional
            Legend label for this sweep (e.g. 'Vd=0.05 V', 'cycle 2').
            Curves with the same label are overwritten; new labels add new lines.
        """
        for ax, spec, lines in zip(self.axes, self.plot_specs, self._lines):
            x_col = spec.get('x', 'Gate_Voltage')
            derived = spec.get('derived')

            x_vals = data[x_col].to_numpy()

            if derived == 'gm':
                id_vals = data['Drain_Current'].to_numpy()
                y_vals = np.gradient(id_vals, x_vals)

            elif derived == 'SS':
                id_vals = np.abs(data['Drain_Current'].to_numpy())
                id_vals = np.maximum(id_vals, 1e-15)   # guard against log(0)
                log_id = np.log10(id_vals)
                # SS = dVg / d(log10 Id), converted to mV/dec
                y_vals = np.gradient(x_vals, log_id) * 1e3

            elif derived == 'gd':
                id_vals = data['Drain_Current'].to_numpy()
                y_vals = np.gradient(id_vals, x_vals)

            else:
                y_col = spec['y']
                y_vals = data[y_col].to_numpy()
                if spec.get('abs', False):
                    y_vals = np.abs(y_vals)

            key = label if label is not None else '_default'

            if key in lines:
                lines[key].set_xdata(x_vals)
                lines[key].set_ydata(y_vals)
            else:
                line, = ax.plot(x_vals, y_vals, label=label)
                lines[key] = line
                if label is not None:
                    ax.legend(fontsize=7)

            ax.relim()
            ax.autoscale_view()

        self.fig.canvas.draw()
        self.fig.canvas.flush_events()
        plt.pause(0.01)

    def freeze(self):
        """
        Stop interactive mode and block until the window is closed.
        Call this after all sweeps have finished.
        """
        plt.ioff()
        plt.show(block=True)


# ---------------------------------------------------------------------------
# Wrapper functions — mirror FET_three_terminal signatures, add live update
# ---------------------------------------------------------------------------

def live_IdVg_single_Vd(plotter, b1500, smu_gate, smu_drain, smu_source,
                         gate_start, gate_stop, gate_step, drain_voltage,
                         Irange='1 nA limited auto ranging',
                         Vrange='2 V limited auto ranging',
                         label=None):
    """
    Run a single Id-Vg sweep and immediately update the live plot.

    Parameters mirror IdVg_single_Vd() in FET_three_terminal.py.
    plotter : LivePlotter  instance to update after the sweep.
    label   : str          legend label (defaults to 'Vd=<drain_voltage> V').
    """
    data = IdVg_single_Vd(
        b1500=b1500, smu_gate=smu_gate, smu_drain=smu_drain,
        smu_source=smu_source, gate_start=gate_start, gate_stop=gate_stop,
        gate_step=gate_step, drain_voltage=drain_voltage,
        Irange=Irange, Vrange=Vrange,
    )
    plotter.update(data, label=label or f'Vd={drain_voltage} V')
    return data


def live_IdVg_multi_Vd(plotter, b1500, smu_gate, smu_drain, smu_source,
                        gate_start, gate_stop, gate_step, drain_list,
                        Irange='1 nA limited auto ranging',
                        Vrange='2 V limited auto ranging'):
    """
    Run Id-Vg sweeps at each drain voltage in drain_list, updating the live
    plot after every sweep so each curve appears as it is measured.

    Parameters mirror IdVg_multi_Vd() in FET_three_terminal.py.
    plotter : LivePlotter  instance to update after each sweep.
    """
    all_data = pd.DataFrame()
    for Vd in drain_list:
        print(f"Measuring at Drain Voltage: {Vd} V")
        data = IdVg_single_Vd(
            b1500=b1500, smu_gate=smu_gate, smu_drain=smu_drain,
            smu_source=smu_source, gate_start=gate_start, gate_stop=gate_stop,
            gate_step=gate_step, drain_voltage=Vd,
            Irange=Irange, Vrange=Vrange,
        )
        data['Drain_Voltage'] = Vd
        plotter.update(data, label=f'Vd={Vd} V')
        all_data = pd.concat([all_data, data], ignore_index=True)
    return all_data


def live_IdVg_multi_Vd_multi_cycle(plotter, b1500, smu_gate, smu_drain,
                                    smu_source, gate_start, gate_stop,
                                    gate_step, drain_list, num_cycles=1,
                                    Irange='1 nA limited auto ranging',
                                    Vrange='2 V limited auto ranging'):
    """
    Run multiple cycles of multi-Vd Id-Vg sweeps, updating the live plot
    after each individual sweep.

    Parameters mirror IdVg_multi_Vd_multi_cycle() in FET_three_terminal.py.
    plotter : LivePlotter  instance to update after each sweep.
    """
    all_data = pd.DataFrame()
    for cycle in range(1, num_cycles + 1):
        print(f"Starting measurement cycle {cycle} of {num_cycles}")
        for Vd in drain_list:
            print(f"  Measuring at Drain Voltage: {Vd} V")
            data = IdVg_single_Vd(
                b1500=b1500, smu_gate=smu_gate, smu_drain=smu_drain,
                smu_source=smu_source, gate_start=gate_start,
                gate_stop=gate_stop, gate_step=gate_step, drain_voltage=Vd,
                Irange=Irange, Vrange=Vrange,
            )
            data['Drain_Voltage'] = Vd
            data['Cycle'] = cycle
            plotter.update(data, label=f'Vd={Vd} V  cyc{cycle}')
            all_data = pd.concat([all_data, data], ignore_index=True)
    return all_data


def live_IdVd_single_Vg(plotter, b1500, smu_gate, smu_drain, smu_source,
                         drain_start, drain_stop, drain_step, gate_voltage,
                         Irange='1 nA limited auto ranging',
                         Vrange='2 V limited auto ranging',
                         label=None):
    """
    Run a single Id-Vd sweep and immediately update the live plot.

    Parameters mirror IdVd_single_Vg() in FET_three_terminal.py.
    plotter : LivePlotter  instance to update after the sweep.
    label   : str          legend label (defaults to 'Vg=<gate_voltage> V').
    """
    data = IdVd_single_Vg(
        b1500=b1500, smu_gate=smu_gate, smu_drain=smu_drain,
        smu_source=smu_source, drain_start=drain_start, drain_stop=drain_stop,
        drain_step=drain_step, gate_voltage=gate_voltage,
        Irange=Irange, Vrange=Vrange,
    )
    plotter.update(data, label=label or f'Vg={gate_voltage} V')
    return data


def live_IdVd_multi_Vg(plotter, b1500, smu_gate, smu_drain, smu_source,
                        drain_start, drain_stop, drain_step, gate_list,
                        Irange='1 nA limited auto ranging',
                        Vrange='2 V limited auto ranging'):
    """
    Run Id-Vd sweeps at each gate voltage in gate_list, updating the live
    plot after every sweep.

    Parameters mirror IdVd_multi_Vg() in FET_three_terminal.py.
    plotter : LivePlotter  instance to update after each sweep.
    """
    all_data = pd.DataFrame()
    for Vg in gate_list:
        print(f"Measuring at Gate Voltage: {Vg} V")
        data = IdVd_single_Vg(
            b1500=b1500, smu_gate=smu_gate, smu_drain=smu_drain,
            smu_source=smu_source, drain_start=drain_start,
            drain_stop=drain_stop, drain_step=drain_step, gate_voltage=Vg,
            Irange=Irange, Vrange=Vrange,
        )
        data['Gate_Voltage'] = Vg
        plotter.update(data, label=f'Vg={Vg} V')
        all_data = pd.concat([all_data, data], ignore_index=True)
    return all_data


def live_IdVd_multi_Vg_multi_cycle(plotter, b1500, smu_gate, smu_drain,
                                    smu_source, drain_start, drain_stop,
                                    drain_step, gate_list, num_cycles=1,
                                    Irange='1 nA limited auto ranging',
                                    Vrange='2 V limited auto ranging'):
    """
    Run multiple cycles of multi-Vg Id-Vd sweeps, updating the live plot
    after each individual sweep.

    Parameters mirror IdVd_multi_Vg_multi_cycle() in FET_three_terminal.py.
    plotter : LivePlotter  instance to update after each sweep.
    """
    all_data = pd.DataFrame()
    for cycle in range(1, num_cycles + 1):
        print(f"Starting measurement cycle {cycle} of {num_cycles}")
        for Vg in gate_list:
            print(f"  Measuring at Gate Voltage: {Vg} V")
            data = IdVd_single_Vg(
                b1500=b1500, smu_gate=smu_gate, smu_drain=smu_drain,
                smu_source=smu_source, drain_start=drain_start,
                drain_stop=drain_stop, drain_step=drain_step,
                gate_voltage=Vg, Irange=Irange, Vrange=Vrange,
            )
            data['Gate_Voltage'] = Vg
            data['Cycle'] = cycle
            plotter.update(data, label=f'Vg={Vg} V  cyc{cycle}')
            all_data = pd.concat([all_data, data], ignore_index=True)
    return all_data
