"""
3-Terminal FET Measurement Script
==================================
Runs automated Id-Vg and Id-Vd IV sweeps on a Keysight B1500A via a FormFactor S200 probe station.

Usage
-----
    python fet_gen_workflow.py --config <path_to_config.json>

Example
-------
    python fet_gen_workflow.py --config configs/fet_gen_example_config.json

Config File Parameters (JSON)
------------------------------
miscellaneous:
    mode              str           Execution mode: "save" (measure + save), "nosave" (measure only), "debug" (skip hardware)
    save_dir          str           Output directory for CSV and PNG files (e.g. "saved_data/my_run")

measurement:
    Irange            str           Current measurement range passed to B1500A SMUs (e.g. "1 nA limited auto ranging")
    Vrange            str           Voltage measurement range passed to B1500A SMUs (e.g. "2 V limited auto ranging")
    default_start     float         Initial gate sweep start in V (e.g. -3.0)
    start_limit       float         Hard lower bound on gate start; device is skipped if this would be exceeded (e.g. -3.5)
    default_stop      float         Gate sweep stop in V (e.g. 3.0)
    stop_limit        float         Hard upper bound on gate stop (e.g. 3.5)
    scan_step         float         Step size for the quick initial scan in V (e.g. 0.1)
    main_step         float         Step size for the main high-resolution sweep in V (e.g. 0.025)
    Vdlin             float         Drain bias used in initial linear-region scan (e.g. 0.05)
    Vdsat             float         Drain bias used in initial saturation-region scan (e.g. 1.0)
    IdVg_drain_list   list[float]   Drain voltages swept during main Id-Vg measurement (e.g. [0.05, 1.0])
    IdVd_sweep_start  float         Drain sweep start for Id-Vd measurement in V (e.g. 0.0)
    IdVd_sweep_stop   float         Drain sweep stop for Id-Vd measurement in V (e.g. 1.0)
    IdVd_sweep_step   float         Drain sweep step size in V (e.g. 0.025)
    Vov_list          list[float]   Gate overdrive voltages (Vov = Vg - Vt) for Id-Vd gate bias list (e.g. [1.0, 1.25, ...])
    IdVg_cycles       int           Number of repeated Id-Vg sweep cycles (e.g. 2)
    IdVd_cycles       int           Number of repeated Id-Vd sweep cycles (e.g. 1)

sample:
    W_um              float         Channel width in um (used for normalised Vt extraction, e.g. 10.0)
    start_DieR_idx    int           Die row index to start from (0-indexed from bottom)
    start_DieC_idx    int           Die column index to start from (0-indexed from left)
    DieR_idx_list     list[int]     Die rows to measure
    DieC_idx_list     list[int]     Die columns to measure
    die_x_pitch       float         Die centre-to-centre pitch in X in microns
    die_y_pitch       float         Die centre-to-centre pitch in Y in microns

dev-group:
    dev_group_name    str           Device group name
    dev_x_name        str           Device key in X direction
    dev_y_name        str           Device key in Y direction
    start_dev_x_idx   int           Device index to start from in X direction
    start_dev_y_idx   int           Device index to start from in Y direction
    dev_x_idx_list    list[int]     Device indices in X direction
    dev_y_idx_list    list[int]     Device indices in Y direction
    dev_x_map         dict          Mapping from device x indices to device x values in X direction
    dev_y_map         dict          Mapping from device y indices to device y values in Y direction
    dev_x_pitch       float         Device-to-device pitch in X direction in microns
    dev_y_pitch       float         Device-to-device pitch in Y direction in microns (negative = move up)
    dev_x_pitch_list  list[float]   List of device-to-device pitches in X direction in microns
    dev_y_pitch_list  list[float]   List of device-to-device pitches in Y direction in microns
    skip_combinations list          List of (DieR, DieC, dev_x_idx, dev_y_idx) tuples to skip
"""

import argparse
import json
import os

def _parse_args():
    p = argparse.ArgumentParser(description='3-terminal FET measurement script (v1)')
    p.add_argument('--config', required=True, help='Path to JSON config file')
    return p.parse_args()

_args = _parse_args()
with open(_args.config) as _f:
    _cfg = json.load(_f)

_misc = _cfg.get('miscellaneous', {})
_meas = _cfg.get('measurement', {})
_sample = _cfg.get('sample', {})
_dev_grp = _cfg.get('dev-group', {})

# from data_processing_utils.IdVg_param_extract import *
if _misc.get('mode', 'debug') != 'debug':
    from b1500A_utils.initialize_smus import *
    # from b1500A_utils.FET_three_terminal import *
    from S200_utils.initialize_s200 import *
    # from S200_utils.chuck_control import *
    from e4980A_utils.comm_test import *
    from e4980A_utils.qcodes_cv import *

# import numpy as np
# import pandas as pd
# import matplotlib.pyplot as plt
# import time
# from math import ceil, floor

from main_utils.main_funs import *

current_dir = os.getcwd()

mylcr_meter = KeysightE4980A('lcr_meter', settings['lcr_meter_address'])
myb1500 = b1500
myprober = prober
smu_gate = b1500.smu3
smu_drain = b1500.smu2
smu_source = b1500.smu4

if __name__ == '__main__':
    main_multi_measure(_misc=_misc, _meas=_meas, _sample=_sample, _dev_grp=_dev_grp, myb1500=myb1500, smu_gate=smu_gate, smu_drain=smu_drain, smu_source=smu_source, prober=myprober)
    # main_cvf_measure(_misc=_misc, _meas=_meas, _sample=_sample, _dev_grp=_dev_grp, lcr_meter=mylcr_meter, prober=myprober)
    prober.close()
    rm.close()



