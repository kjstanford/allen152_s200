"""
3-Terminal FET Measurement Script
==================================
Runs automated Id-Vg and Id-Vd IV sweeps on a Keysight B1500A via a Cascade S200 probe station.

Usage
-----
    python main_3terminal_fet.py --config <path_to_config.json>

Example
-------
    python main_3terminal_fet.py --config configs/main_3terminal_fet_config.json

Config File Parameters (JSON)
------------------------------
Top-level:
    mode        str   Execution mode: "save" (measure + save), "nosave" (measure only), "debug" (skip hardware)
    save_dir    str   Output directory for CSV and PNG files (e.g. "saved_data/my_run")

instrument:
    Irange      str   Current measurement range passed to B1500A SMUs (e.g. "1 nA limited auto ranging")
    Vrange      str   Voltage measurement range passed to B1500A SMUs (e.g. "2 V limited auto ranging")

device:
    W_nm        float Channel width in nm (used for normalised Vt extraction, e.g. 10000)

gate_voltage:
    default_start   float   Initial gate sweep start in V (e.g. -3.0)
    start_limit     float   Hard lower bound on gate start; device is skipped if this would be exceeded (e.g. -3.5)
    default_stop    float   Gate sweep stop in V (e.g. 3.0)
    stop_limit      float   Hard upper bound on gate stop (e.g. 3.5)
    scan_step       float   Step size for the quick initial scan in V (e.g. 0.1)
    main_step       float   Step size for the main high-resolution sweep in V (e.g. 0.025)

drain_voltage:
    Vdlin           float         Drain bias used in initial linear-region scan (e.g. 0.05)
    Vdsat           float         Drain bias used in initial saturation-region scan (e.g. 1.0)
    IdVg_drain_list list[float]   Drain voltages swept during main Id-Vg measurement (e.g. [0.05, 1.0])
    IdVd_sweep_start float        Drain sweep start for Id-Vd measurement in V (e.g. 0.0)
    IdVd_sweep_stop  float        Drain sweep stop for Id-Vd measurement in V (e.g. 1.0)
    IdVd_sweep_step  float        Drain sweep step size in V (e.g. 0.025)
    Vov_list        list[float]   Gate overdrive voltages (Vov = Vg - Vt) for Id-Vd gate bias list (e.g. [1.0, 1.25, ...])

measurement:
    IdVg_cycles     int   Number of repeated Id-Vg sweep cycles (e.g. 2)
    IdVd_cycles     int   Number of repeated Id-Vd sweep cycles (e.g. 1)

wafer_layout:
    start_DieR_idx  int           Die row index to start from (0-indexed from bottom)
    start_DieC_idx  int           Die column index to start from (0-indexed from left)
    start_LcR_idx   int           Contact-length cluster row index to start from
    start_LcC_idx   int           Contact-length cluster column index to start from
    DieR_idx_list   list[int]     Die rows to measure
    DieC_idx_list   list[int]     Die columns to measure
    die_x_pitch     float         Die centre-to-centre pitch in X in microns
    die_y_pitch     float         Die centre-to-centre pitch in Y in microns
    Lc_list         list[list]    2D array of contact lengths in nm indexed [LcR][LcC]
    LcR_idx_list    list[int]     Lc cluster row indices to iterate over
    LcC_idx_list    list[int]     Lc cluster column indices to iterate over
    Lc_x_pitch      float         Lc cluster centre-to-centre pitch in X in microns
    Lc_y_pitch      float         Lc cluster centre-to-centre pitch in Y in microns
    dev_code_list   list[str]     Device letter codes within each L row (e.g. ["A","B",...,"L"])
    L_list          list[int]     Channel lengths in nm to measure (e.g. [60, 80, ..., 2000])
    L_skip_list     list[int]     Channel lengths to skip entirely (e.g. [1000, 2000])
    dev_x_pitch     float         Device-to-device pitch in X within an L row in microns
    dev_y_pitch     float         Device-to-device pitch in Y between L rows in microns (negative = move up)
    reverse_L       bool          If true, iterate L_list in reverse and flip dev_y_pitch sign
    skip_combinations list        List of (DieR, DieC, LcR, LcC, L_idx, dev_code) tuples to skip
"""

import argparse
import json
import os

def _parse_args():
    p = argparse.ArgumentParser(description='3-terminal FET measurement script')
    p.add_argument('--config', required=True, help='Path to JSON config file')
    return p.parse_args()

_args = _parse_args()
with open(_args.config) as _f:
    _cfg = json.load(_f)

mode = _cfg.get('mode', 'save')

from data_processing_utils.IdVg_param_extract import *

if mode != 'debug':
    from b1500A_utils.initialize_smus import *
    from b1500A_utils.FET_three_terminal import *
    from S200_utils.initialize_s200 import *
    from S200_utils.chuck_control import *
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import time
from math import ceil, floor

current_dir = os.getcwd()

myb1500 = b1500
smu_gate = b1500.smu3
smu_drain = b1500.smu2
smu_source = b1500.smu4

_gv   = _cfg['gate_voltage']
_dv   = _cfg['drain_voltage']
_meas = _cfg['measurement']
_inst = _cfg.get('instrument', {})

default_gate_start = _gv['default_start']
gate_start_limit   = _gv['start_limit']
default_gate_stop  = _gv['default_stop']
gate_stop_limit    = _gv['stop_limit']
scan_gate_step     = _gv['scan_step']
main_gate_step     = _gv['main_step']

default_Vdlin   = _dv['Vdlin']
default_Vdsat   = _dv['Vdsat']
IdVg_drain_list = _dv['IdVg_drain_list']
drain_start     = _dv['IdVd_sweep_start']
drain_stop      = _dv['IdVd_sweep_stop']
drain_step      = _dv['IdVd_sweep_step']
Vov_list        = _dv['Vov_list']

W        = _cfg['device']['W_nm']
save_dir = _cfg['save_dir']

num_cycles_IdVg = _meas['IdVg_cycles']
num_cycles_IdVd = _meas['IdVd_cycles']

Irange = _inst.get('Irange', '1 nA limited auto ranging')
Vrange = _inst.get('Vrange', '2 V limited auto ranging')

cycle_colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k']

def measure_initial_scan(gate_start=default_gate_start, gate_stop=default_gate_stop, gate_step=scan_gate_step, L=None, data_all=None, descriptor=None):
    print("\n################################################")
    print("Starting initial Id-Vg scan to evaluate device...")
    remeasure_flag = False
    skip_device_flag = False
    new_gate_start = gate_start
    new_gate_stop = gate_stop

    if mode == 'debug' and data_all is not None:
        data = data_all[data_all['Drain_Voltage'] == default_Vdlin]
    else:
        if myb1500 is None or smu_gate is None or smu_drain is None or smu_source is None:
            raise Exception("B1500 and SMUs must be initialized before calling measure_initial_scan in non-debug mode.")

        # Initial Id-Vg scan to check if device is working / measuring VT
        data = IdVg_single_Vd(
            b1500=myb1500,
            smu_gate=smu_gate,
            smu_drain=smu_drain,
            smu_source=smu_source,
            gate_start=gate_start,
            gate_stop=gate_stop,
            gate_step=gate_step,
            drain_voltage=default_Vdlin,
            Irange=Irange,
            Vrange=Vrange
        )

        # Plot Id-Vg curve
        plt.figure(figsize=(8, 6))
        plt.semilogy(data['Gate_Voltage'].to_numpy(), np.abs(data['Drain_Current'].to_numpy()), label=f'Vd = {default_Vdlin} V')
        plt.xlabel('Gate Voltage (V)')
        plt.ylabel('Drain Current (A)')
        plt.title('Initial Id-Vg Scan')
        plt.legend()
        plt.grid(True)
        plt.show(block=False)
        plt.pause(1)

        if mode == 'save':
            test_name = 'IdVg_initial_scan'
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            if descriptor is not None:
                timestamp += f"_{descriptor}"
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, f"{test_name}_{timestamp}.csv")
            data.to_csv(save_path, index=False)
            plt.savefig(save_path.replace('.csv', '.png'))
            print(f"Data saved to: {save_path}")

        plt.close()

    Vg_data = data['Gate_Voltage'].to_numpy()
    Id_data = np.abs(data['Drain_Current'].to_numpy())
    Ig_data = np.abs(data['Gate_Current'].to_numpy())

    Vg_data_half = get_sweeps(Vg_data)['f']
    Id_data_half = get_sweeps(Id_data)['f']
    Vt_lin = Vt_at_constant_Id(Vg_data_half, Id_data_half, Id_target=10e-9 * W / L)
    print(f"Vt @ Id = 10 nA * W / L: {Vt_lin} V")

    if np.isnan(Vt_lin) or Vt_lin is None:
        print("Failed to extract Vt, device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, new_gate_stop, Vt_lin

    if Vt_lin < -2 or Vt_lin > 1.5:
        print("Extracted Vt is out of expected range (-2 V to 1.5 V), device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, new_gate_stop, Vt_lin
    else:
        print("Extracted Vt within acceptable range.")

    if max(Ig_data) > 1e-9:
        print("Gate leakage current exceeds 1 nA, device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, new_gate_stop, Vt_lin
    else:
        print("Gate leakage current within acceptable limits.")

    if max(Id_data) < 1e-9:
        print("Maximum drain current is below 1 nA, device may be non-functional.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, new_gate_stop, Vt_lin
    else:
        print("Maximum drain current within acceptable limits.")

    if min(Id_data) < 1e-12 or max(Id_data) > 1e-7 :
        if max(Id_data) / min(Id_data) < 100:
            print("Drain current range is less than two decades, device may be faulty.")
            skip_device_flag = True
            return skip_device_flag, new_gate_start, new_gate_stop, Vt_lin
        else:
            print("Drain current range within acceptable limits.")

    # if min(Id_data) > 5e-13:
    #     print("Minimum drain current is above 0.5 pA, full range not covered.")
    #     new_gate_start = gate_start - 0.5
    #     if new_gate_start < gate_start_limit:
    #         skip_device_flag = True
    #         print("Cannot extend gate_start further without exceeding limits, skipping device.")
    #         return skip_device_flag, new_gate_start, new_gate_stop, Vt_lin
    #     else:
    #         remeasure_flag = True
    #     print(f"Changing gate_start to {new_gate_start} V for re-measurement.")

    # reqd_gate_stop = ceil(Vt_lin*2)/2 + 2.0
    # if reqd_gate_stop > gate_stop:
    #     print(f"Changing gate_stop to {reqd_gate_stop} V for re-measurement.")
    #     new_gate_stop = reqd_gate_stop
    #     if new_gate_stop > gate_stop_limit:
    #         skip_device_flag = True
    #         print("Cannot extend gate_stop further without exceeding limits, skipping device.")
    #         remeasure_flag = False
    #         return skip_device_flag, new_gate_start, new_gate_stop, Vt_lin
    #     else:
    #         remeasure_flag = True

    # assert new_gate_start <= gate_start, "new_gate_start exceeds original gate_start!"
    # assert new_gate_stop >= gate_stop, "new_gate_stop is less than original gate_stop!"
    # if remeasure_flag and not skip_device_flag:
    #     print("Re-measuring device with updated gate voltage range...")
    #     return measure_initial_scan(gate_start=new_gate_start, gate_stop=new_gate_stop, gate_step=gate_step, L=L, data_all=data_all)
    # else:
    #     return skip_device_flag, new_gate_start, new_gate_stop, Vt_lin
    return skip_device_flag, new_gate_start, new_gate_stop, Vt_lin

def measure_initial_scan_v2(gate_start=default_gate_start, gate_stop=default_gate_stop, gate_step=scan_gate_step, L=None, data_all=None, descriptor=None):
    print("\n################################################")
    print("Starting initial Id-Vg scan to evaluate device...")
    remeasure_flag = False
    skip_device_flag = False
    new_gate_start = gate_start
    new_gate_stop = gate_stop

    if mode == 'debug' and data_all is not None:
        data = data_all[data_all['Drain_Voltage'] == default_Vdsat]
    else:
        if myb1500 is None or smu_gate is None or smu_drain is None or smu_source is None:
            raise Exception("B1500 and SMUs must be initialized before calling measure_initial_scan in non-debug mode.")

        # Initial Id-Vg scan to check if device is working / measuring VT
        data = IdVg_single_Vd(
            b1500=myb1500,
            smu_gate=smu_gate,
            smu_drain=smu_drain,
            smu_source=smu_source,
            gate_start=gate_start,
            gate_stop=gate_stop,
            gate_step=gate_step,
            drain_voltage=default_Vdsat,
            Irange=Irange,
            Vrange=Vrange
        )

        # Plot Id-Vg curve
        plt.figure(figsize=(8, 6))
        plt.semilogy(data['Gate_Voltage'].to_numpy(), np.abs(data['Drain_Current'].to_numpy()), label=f'Vd = {default_Vdsat} V')
        plt.xlabel('Gate Voltage (V)')
        plt.ylabel('Drain Current (A)')
        plt.title(f'Initial Id-Vg Scan at Vd = {default_Vdsat} V')
        plt.legend()
        plt.grid(True)
        plt.show(block=False)
        plt.pause(1)

        if mode == 'save':
            test_name = 'IdVg_initial_scan'
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            if descriptor is not None:
                timestamp += f"_{descriptor}"
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, f"{test_name}_{timestamp}.csv")
            data.to_csv(save_path, index=False)
            plt.savefig(save_path.replace('.csv', '.png'))
            print(f"Data saved to: {save_path}")

        plt.close()

    Vg_data = data['Gate_Voltage'].to_numpy()
    Id_data = np.abs(data['Drain_Current'].to_numpy())
    Ig_data = np.abs(data['Gate_Current'].to_numpy())

    Vg_data_half = get_sweeps(Vg_data)['f']
    Id_data_half = get_sweeps(Id_data)['f']
    Vt_sat = Vt_at_constant_Id(Vg_data_half, Id_data_half, Id_target=100e-9 * W / L)
    print(f"Vt @ Id = 100 nA * W / L: {Vt_sat} V")

    if np.isnan(Vt_sat) or Vt_sat is None:
        print("Failed to extract Vt, device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, new_gate_stop, Vt_sat

    if Vt_sat < -3.5 or Vt_sat > 2:
        print("Extracted Vt is out of expected range (-3.5 V to 2 V), device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, new_gate_stop, Vt_sat
    else:
        print("Extracted Vt within acceptable range.")

    if max(Ig_data) > 1e-9:
        print("Gate leakage current exceeds 1 nA, device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, new_gate_stop, Vt_sat
    else:
        print("Gate leakage current within acceptable limits.")

    if max(Id_data) < 1e-7:
        print("Maximum drain current is below 100 nA, device is not good enough.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, new_gate_stop, Vt_sat
    else:
        print("Maximum drain current within acceptable limits.")

    if min(Id_data) < 1e-12 or max(Id_data) > 1e-7 :
        if max(Id_data) / min(Id_data) < 100:
            print("Drain current range is less than two decades, device may be faulty.")
            skip_device_flag = True
            return skip_device_flag, new_gate_start, new_gate_stop, Vt_sat
        else:
            print("Drain current range within acceptable limits.")

    if min(Id_data) <= 2.5e-12:
        Voff = Vt_at_constant_Id(Vg_data_half, Id_data_half, Id_target=2.5e-12)
        print(f"Voff = {Voff} V defined at Id = 2.5 pA")
        new_gate_start = floor((Voff - 0.5)/scan_gate_step) * scan_gate_step

    if min(Id_data) > 2.5e-12:
        new_gate_start = gate_start_limit

    return skip_device_flag, new_gate_start, new_gate_stop, Vt_sat

def measure_main_IdVg(gate_start, gate_stop, gate_step, descriptor=None):
    print("\n################################################")
    print("Starting main Id-Vg measurement sequence...")

    if mode == 'debug':
        print("Debug mode: Skipping main Id-Vg measurement sequence.")
        return

    if myb1500 is None or smu_gate is None or smu_drain is None or smu_source is None:
        raise Exception("B1500 and SMUs must be initialized before calling measure_main_IdVg in non-debug mode.")

    # Main Id-Vg measurement at multiple drain voltages
    data = IdVg_multi_Vd_multi_cycle(
        b1500=myb1500,
        smu_gate=smu_gate,
        smu_drain=smu_drain,
        smu_source=smu_source,
        gate_start=gate_start,
        gate_stop=gate_stop,
        gate_step=gate_step,
        drain_list=IdVg_drain_list,
        num_cycles=num_cycles_IdVg,
        Irange=Irange,
        Vrange=Vrange
    )

    # Plot Id-Vg curves for different drain voltages
    plt.figure(figsize=(8, 6))
    for cycle in data['Cycle'].unique():
        cycle_data = data[data['Cycle'] == cycle]
        for Vd in cycle_data['Drain_Voltage'].unique():
            Vd_data = cycle_data[cycle_data['Drain_Voltage'] == Vd]
            plt.semilogy(Vd_data['Gate_Voltage'].to_numpy(), np.abs(Vd_data['Drain_Current'].to_numpy()), label=f'Vd = {Vd} V', color=cycle_colors[(cycle-1) % len(cycle_colors)])
    plt.xlabel('Gate Voltage (V)')
    plt.ylabel('Drain Current (A)')
    plt.title('Id-Vg Curves for Different Drain Voltages')
    # plt.legend()
    plt.grid(True)
    plt.show(block=False)
    plt.pause(1)

    if mode == 'save':
        test_name = 'IdVg_main'
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if descriptor is not None:
            timestamp += f"_{descriptor}"
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f"{test_name}_{timestamp}.csv")
        data.to_csv(save_path, index=False)
        plt.savefig(save_path.replace('.csv', '.png'))
        print(f"Data saved to : {save_path}")

    plt.close()

    print("Main IdVg measurement sequence completed.")
    print("################################################\n")

def measure_main_IdVd(Vt_lin, descriptor=None):
    print("\n################################################")
    print("Starting main Id-Vd measurement sequence...")

    if mode == 'debug':
        print("Debug mode: Skipping main Id-Vd measurement sequence.")
        return
    gate_list = [Vov + Vt_lin for Vov in Vov_list if (Vov + Vt_lin) <= gate_stop_limit]

    if myb1500 is None or smu_gate is None or smu_drain is None or smu_source is None:
        raise Exception("B1500 and SMUs must be initialized before calling measure_main_IdVd in non-debug mode.")

    # Main Id-Vd measurement at different gate voltages
    data = IdVd_multi_Vg_multi_cycle(
        b1500=myb1500,
        smu_gate=smu_gate,
        smu_drain=smu_drain,
        smu_source=smu_source,
        gate_list=gate_list,
        drain_start=drain_start,
        drain_stop=drain_stop,
        drain_step=drain_step,
        num_cycles=num_cycles_IdVd,
        Irange=Irange,
        Vrange=Vrange
    )

    # Plot Id-Vd curves for different gate voltages
    plt.figure(figsize=(8, 6))
    for cycle in data['Cycle'].unique():
        cycle_data = data[data['Cycle'] == cycle]
        for Vg in cycle_data['Gate_Voltage'].unique():
            Vg_data = cycle_data[cycle_data['Gate_Voltage'] == Vg]
            plt.plot(Vg_data['Drain_Voltage'].to_numpy(), np.abs(Vg_data['Drain_Current'].to_numpy()), label=f'Vg = {Vg} V', color = cycle_colors[(cycle-1) % len(cycle_colors)])
    plt.xlabel('Drain Voltage (V)')
    plt.ylabel('Drain Current (A)')
    plt.title('Id-Vd Curves for Different Gate Voltages')
    # plt.legend()
    plt.grid(True)
    plt.show(block=False)
    plt.pause(1)

    if mode == 'save':
        test_name = 'IdVd_main'
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if descriptor is not None:
            timestamp += f"_{descriptor}"
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f"{test_name}_{timestamp}.csv")
        data.to_csv(save_path, index=False)
        plt.savefig(save_path.replace('.csv', '.png'))
        print(f"Data saved to : {save_path}")

    plt.close()

    print("Main IdVd measurement sequence completed.")
    print("################################################\n")

def measure_all(L, descriptor=None):
    skip_device_flag, new_gate_start, new_gate_stop, Vt_lin = measure_initial_scan(L=L, descriptor=descriptor)
    if skip_device_flag:
        print("SKIPPING DEVICE BASED ON INITIAL SCAN EVALUATION.....\n")
    else:
        print("DEVICE PASSED INITIAL SCAN EVALUATION.")
        print(f"Proceeding with main measurement sequence with gate voltage range {new_gate_start} V to {new_gate_stop} V and Vt_lin = {Vt_lin} V\n")
        measure_main_IdVg(gate_start=new_gate_start, gate_stop=new_gate_stop, gate_step=main_gate_step, descriptor=descriptor)
        # measure_main_IdVd(Vt_lin=Vt_lin)

def measure_all_v2(L, descriptor=None):
    skip_device_flag, new_gate_start, new_gate_stop, Vt_sat = measure_initial_scan_v2(L=L, descriptor=descriptor)
    if skip_device_flag:
        print("SKIPPING DEVICE BASED ON INITIAL SCAN EVALUATION.....\n")
    else:
        print("DEVICE PASSED INITIAL SCAN EVALUATION.")
        print(f"Proceeding with main measurement sequence with gate voltage range {new_gate_start} V to {new_gate_stop} V and Vt_sat = {Vt_sat} V\n")
        measure_main_IdVg(gate_start=new_gate_start, gate_stop=new_gate_stop, gate_step=main_gate_step, descriptor=descriptor)

# if __name__ == "__main__"
#     move_contact_height(prober=prober)
#     measure_all(L=40)
#     move_separation_height(prober=prober)
#     prober.close()
#     rm.close()

def main():
    layout = _cfg['wafer_layout']
    start_DieR_idx = layout['start_DieR_idx']
    start_DieC_idx = layout['start_DieC_idx']
    start_LcR_idx  = layout['start_LcR_idx']
    start_LcC_idx  = layout['start_LcC_idx']
    dev_x_pitch    = layout['dev_x_pitch']
    dev_y_pitch    = layout['dev_y_pitch']
    dev_code_list  = layout['dev_code_list']
    L_list         = layout['L_list']
    reverse_L      = layout.get('reverse_L', False)
    if reverse_L:
        L_list = L_list[::-1]
        dev_y_pitch = -dev_y_pitch
    Lc_x_pitch   = layout['Lc_x_pitch']
    Lc_y_pitch   = layout['Lc_y_pitch']
    Lc_list      = layout['Lc_list']
    LcR_idx_list = layout['LcR_idx_list']
    LcC_idx_list = layout['LcC_idx_list']
    DieR_idx_list = layout['DieR_idx_list']
    DieC_idx_list = layout['DieC_idx_list']
    die_x_pitch   = layout['die_x_pitch']
    die_y_pitch   = layout['die_y_pitch']
    L_skip_list   = layout.get('L_skip_list', [])
    skip_combinations = [tuple(c) for c in layout.get('skip_combinations', [])]

    current_x_displace_from_origin = 0
    current_y_displace_from_origin = 0

    print(f"Starting position: start_DieR_idx = {start_DieR_idx}, start_DieC_idx = {start_DieC_idx}, start_LcR_idx = {start_LcR_idx}, start_LcC_idx = {start_LcC_idx}")

    for DieR_idx in DieR_idx_list:
        for DieC_idx in DieC_idx_list:
            for LcR_idx in LcR_idx_list:
                for LcC_idx in LcC_idx_list:
                    for L_idx, L in enumerate(L_list):
                        for dev_idx, dev_code in enumerate(dev_code_list):
                            measured_previously = False
                            Lc = Lc_list[LcR_idx][LcC_idx]
                            descriptor = f"DieR{DieR_idx}_DieC{DieC_idx}_LcR{LcR_idx}_LcC{LcC_idx}_Lc{Lc}nm_L{L}nm_Dev{dev_code}"

                            if L in L_skip_list:
                                continue

                            # if Lc not in [60, 80]:
                            #     continue

                            if (DieR_idx, DieC_idx, LcR_idx, LcC_idx, L_idx, dev_code) in skip_combinations:
                                print(f"Skipping Die Row={DieR_idx}, Column={DieC_idx}, Lc={Lc} nm, L={L} nm, DevCode={dev_code} as per skip list.")
                                continue
                            # Walk through the directory and subdirectories
                            for root, dirs, files in os.walk(save_dir):
                                if 'IGNORE' in root:
                                    continue
                                for file in files:
                                    if file.endswith('.csv'): # and 'main' in file:
                                        if descriptor in file:
                                            print(f"Data for Die Row={DieR_idx}, Column={DieC_idx}, Lc={Lc} nm, L={L} nm, DevCode={dev_code} already exists, skipping measurement.")
                                            measured_previously = True
                                            break

                            if measured_previously:
                                    continue

                            print(f"Moving to Die Row={DieR_idx}, Column={DieC_idx}, Lc={Lc} nm, L={L} nm, DevCode={dev_code}...")
                            reqd_x_displace_from_origin = die_x_pitch * (DieC_idx-start_DieC_idx) + Lc_x_pitch * (LcC_idx-start_LcC_idx) + dev_x_pitch * dev_idx
                            reqd_y_displace_from_origin = die_y_pitch * (DieR_idx-start_DieR_idx) + Lc_y_pitch * (LcR_idx-start_LcR_idx) + dev_y_pitch * L_idx
                            move_relative(prober=prober, x_microns=reqd_x_displace_from_origin - current_x_displace_from_origin, y_microns=reqd_y_displace_from_origin - current_y_displace_from_origin)
                            current_x_displace_from_origin = reqd_x_displace_from_origin
                            current_y_displace_from_origin = reqd_y_displace_from_origin
                            print(f"Measuring device with Lc={Lc} nm, L={L} nm, DevCode={dev_code}, DieR={DieR_idx}, DieC={DieC_idx} at position X={current_x_displace_from_origin} um, Y={current_y_displace_from_origin} um")
                            # time.sleep(2)
                            move_contact_height(prober=prober)
                            measure_all_v2(L=L, descriptor=descriptor)
                            move_separation_height(prober=prober)
                            # time.sleep(2)

if __name__ == "__main__":
    main()
    prober.close()
    rm.close()
