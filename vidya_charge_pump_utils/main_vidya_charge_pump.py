import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import time
from math import ceil, floor
from keithley4200_utils.k4200_helpers import *
from S200_utils.chuck_control import *

def measure_initial_scan_v2(my4200, gatechan, sourcechan, drainchan, vgs_start, vgs_stop, vgs_step, vds_const, dual_sweep=1, descriptor=None, mode=None, save_dir=None):
    """
    Measure the initial ID-VG scan using the Keithley 4200 SMU.

    Parameters:
    - my4200: Keithley 4200 instance
    - gatechan: Gate channel number
    - sourcechan: Source channel number
    - drainchan: Drain channel number
    - vgs_start: Starting gate voltage
    - vgs_stop: Stopping gate voltage
    - vgs_step: Step size for gate voltage
    - vds_const: Constant drain-source voltage
    - dual_sweep: Flag for dual sweep (default is 1)
    - descriptor: Optional descriptor for the measurement
    - mode: Optional mode for data saving
    - save_dir: Optional directory to save the data

    Returns:
    - data: DataFrame containing the measured data
    """

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
    data = idvg_sweep_pmu(my4200=my4200, vgs_start=vgs_start, vgs_stop=vgs_stop, vgs_step=vgs_step, vds_const=vds_const, gatechan=gatechan, drainchan=drainchan, sourcechan=sourcechan, dual_sweep=dual_sweep, fig_save_path=fig_save_path)

    if mode == 'save':
        data.to_csv(csv_save_path, index=False)
        print(f"Data saved to {csv_save_path}")