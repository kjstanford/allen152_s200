import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import time
from math import ceil, floor
from data_processing_utils.IdVg_param_extract import *
from keithley4200_utils.k4200_helpers import *
from S200_utils.chuck_control import *

def measure_initial_scan_v2(my4200, gatechan, sourcechan, drainchan, configs={}, descriptor=None, mode=None, save_dir=None, W=None, L=None):
    """
    Measure the initial ID-VG scan using the Keithley 4200 SMU.

    Parameters:
    - my4200: Keithley 4200 instance
    - gatechan: Gate channel number
    - sourcechan: Source channel number
    - drainchan: Drain channel number
    - descriptor: Optional descriptor for the measurement
    - configs: Dictionary of configuration parameters
    - mode: Optional mode for data saving
    - save_dir: Optional directory to save the data
    - W: Optional width of the device
    - L: Optional length of the device

    Returns:
    - skip_device_flag: Boolean flag indicating if the device should be skipped
    - new_vgs_start: New starting gate voltage
    - Vt_sat: Saturated threshold voltage
    """

    print("\n################################################")
    print("Starting initial Id-Vg scan to evaluate device...")
    skip_device_flag = False
    vgs_start = configs.get('vgs_start', -0.5)
    start_limit = configs.get('start_limit', -2.0)
    vgs_stop = configs.get('vgs_stop', 1.0)
    vgs_step = configs.get('vgs_step', 0.05)
    vds_const = configs.get('vds_sat', 1.5)
    new_vgs_start = vgs_start

    if mode == 'save':
        test_name = 'IdVg_initial_scan'
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if descriptor is not None:
            filename = f"{test_name}_{timestamp}_{descriptor}.csv"
        else:
            filename = f"{test_name}_{timestamp}.csv"

        if save_dir is not None:
            os.makedirs(save_dir, exist_ok=True)
            csv_save_path = os.path.join(save_dir, filename)
        else:
            raise ValueError("save_dir must be provided when mode is 'save'.")

        fig_save_path = csv_save_path.replace('.csv', '.png')

    else:
        fig_save_path = None
    
    # Perform the ID-VG sweep using the PMU
    data = idvg_sweep_pmu(my4200=my4200, vgs_start=vgs_start, vgs_stop=vgs_stop, vgs_step=vgs_step, vds_const=vds_const, gatechan=gatechan, drainchan=drainchan, sourcechan=sourcechan, dual_sweep=1, fig_save_path=fig_save_path)

    if mode == 'save':
        data.to_csv(csv_save_path, index=False)
        print(f"Data saved to {csv_save_path}")

    Vg_data = data['VG'].to_numpy()
    Ig_data = data['IG'].to_numpy()
    Id_data = data['ID'].to_numpy()

    Vg_data_half = get_sweeps(Vg_data)['f']
    Id_data_half = get_sweeps(Id_data)['f']

    target_Id = 100e-9 if W is None or L is None else 100e-9 * (W / L)
    Vt_sat = Vt_at_constant_Id(Vg_data_half, Id_data_half, target_Id=target_Id)
    print(f"Vt @ Id = {target_Id:.2e} A: {Vt_sat:.4f} V")

    if np.isnan(Vt_sat) or Vt_sat is None:
        print("Failed to extract Vt, device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_vgs_start, Vt_sat

    if Vt_sat < -3.5 or Vt_sat > 2.5:
        print("Extracted Vt is out of expected range (-3.5 V to 2.5 V), device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_vgs_start, Vt_sat
    else:
        print("Extracted Vt within acceptable range.")

    if max(Ig_data) > 1e-9:
        print("Gate leakage current exceeds 1 nA, device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_vgs_start, Vt_sat
    else:
        print("Gate leakage current within acceptable limits.")

    if max(Id_data) < 1e-7:
        print("Maximum drain current is below 100 nA, device is not good enough.")
        skip_device_flag = True
        return skip_device_flag, new_vgs_start, Vt_sat
    else:
        print("Maximum drain current within acceptable limits.")

    if min(Id_data) < 1e-12 or max(Id_data) > 1e-7 :
        if max(Id_data) / min(Id_data) < 100:
            print("Drain current range is less than two decades, device may be faulty.")
            skip_device_flag = True
            return skip_device_flag, new_vgs_start, Vt_sat
        else:
            print("Drain current range within acceptable limits.")

    if min(Id_data) <= 2.5e-12:
        print("Drain current is below 2.5 pA, calculating Voff.")
        Voff = Vt_at_constant_Id(Vg_data_half, Id_data_half, Id_target=2.5e-12)
        print(f"Voff = {Voff} V defined at Id = 2.5 pA")
        new_vgs_start = floor((Voff - 0.5)/vgs_step) * vgs_step
        print(f"New starting gate voltage: {new_vgs_start} V")
    else:
        print("Drain current is above 2.5 pA, using start limit.")
        new_vgs_start = start_limit

    return skip_device_flag, new_vgs_start, Vt_sat

def measure_main_IdVg(my4200, gatechan, sourcechan, drainchan, vgs_start, configs={}, descriptor=None, mode=None, save_dir=None):
    """
    Measure the main ID-VG scan using the Keithley 4200 SMU.

    Parameters:
    - my4200: Keithley 4200 instance
    - gatechan: Gate channel number
    - sourcechan: Source channel number
    - drainchan: Drain channel number
    - vgs_start: Starting gate voltage for the main sweep
    - configs: Dictionary of configuration parameters
    - descriptor: Optional descriptor for the measurement
    - mode: Optional mode for data saving
    - save_dir: Optional directory to save the data

    Returns:
    - None
    """
    print("\n################################################")
    print("Starting main Id-Vg scan...")

    vgs_stop = configs.get('vgs_stop', 2.0)
    vgs_step = configs.get('vgs_step', 0.05)
    vds_lin = configs.get('vds_lin', 0.05)
    vds_sat = configs.get('vds_sat', 1.5)
    num_cycles = configs.get('num_cycles', 1)

    for cycle in range(num_cycles):
        for vds_const in [vds_lin, vds_sat]:
            if mode == 'save':
                test_name = 'IdVg_main_scan'
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                if descriptor is not None:
                    filename = f"{test_name}_{timestamp}_{descriptor}_{vds_const}_{cycle}.csv"
                else:
                    filename = f"{test_name}_{timestamp}_{vds_const}_{cycle}.csv"

                if save_dir is not None:
                    os.makedirs(save_dir, exist_ok=True)
                    csv_save_path = os.path.join(save_dir, filename)
                else:
                    raise ValueError("save_dir must be provided when mode is 'save'.")

                fig_save_path = csv_save_path.replace('.csv', '.png')

            else:
                fig_save_path = None

            # Perform the ID-VG sweep using the PMU
            data = idvg_sweep_pmu(my4200=my4200, vgs_start=vgs_start, vgs_stop=vgs_stop, vgs_step=vgs_step, vds_const=vds_const, gatechan=gatechan, drainchan=drainchan, sourcechan=sourcechan, dual_sweep=1, fig_save_path=fig_save_path)

            if mode == 'save':
                data.to_csv(csv_save_path, index=False)
                print(f"Data saved to {csv_save_path}")

    print("Main IdVg measurement sequence completed.")
    print("################################################\n")

def measure_all_v2(my4200, gatechan, sourcechan, drainchan, _meas={}, descriptor=None, mode=None, save_dir=None, W=None, L=None):
    """
    Measure both the initial and main ID-VG scans using the Keithley 4200 SMU.

    Parameters:
    - my4200: Keithley 4200 instance
    - gatechan: Gate channel number
    - sourcechan: Source channel number
    - drainchan: Drain channel number
    - configs: Dictionary of configuration parameters
    - descriptor: Optional descriptor for the measurement
    - mode: Optional mode for data saving
    - save_dir: Optional directory to save the data
    - W: Optional width of the device
    - L: Optional length of the device

    Returns:
    - None
    """
    skip_device_flag, new_vgs_start, Vt_sat = measure_initial_scan_v2(my4200=my4200, gatechan=gatechan, sourcechan=sourcechan, drainchan=drainchan, configs=_meas, descriptor=descriptor, mode=mode, save_dir=save_dir, W=W, L=L)

    vgs_stop = _meas.get('vgs_stop', None)
    if skip_device_flag:
        print("SKIPPING DEVICE BASED ON INITIAL SCAN EVALUATION.....\n")
        return

    print("DEVICE PASSED INITIAL SCAN EVALUATION.")
    print(f"Proceeding with main measurement sequence with gate voltage range {new_vgs_start} V to {vgs_stop} V and Vt_sat = {Vt_sat} V\n")
    measure_main_IdVg(my4200=my4200, gatechan=gatechan, sourcechan=sourcechan, drainchan=drainchan, vgs_start=new_vgs_start, configs=_meas, descriptor=descriptor, mode=mode, save_dir=save_dir)
