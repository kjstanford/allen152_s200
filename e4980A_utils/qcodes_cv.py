import qcodes as qc
from qcodes.instrument_drivers.Keysight.keysight_e4980a import KeysightE4980A, KeysightE4980AMeasurements
from qcodes.dataset import initialise_database, new_experiment
import numpy as np
import os
import datetime
import matplotlib.pyplot as plt
import yaml
import time
import pandas as pd

# default settings
# Define Measurement Settings
settings = {
    'lcr_meter_address': 'GPIB0::17::INSTR',
    'sample_name': 'def',
    'device_group': 'def',
    'frequency': 1e5,  # 100 kHz
    'measurement_function': 'CPRP',  # Corresponds to KeysightE4980AMeasurements.CPRP
    'ac_voltage_level': 0.03,
    'dc_bias_enabled': True,
    'start_volt': -2,
    'stop_volt': 2,
    'sweep_mode': 'double',  # 'single' or 'double'
    'step_volt': 0.05,
    'num_points': 51,  # Total points for single sweep (will be doubled for double sweep)
    'start_freq': 1e3,  # Start frequency for C-V-F sweep
    'stop_freq': 1e6,   # Stop frequency for C-V-F sweep
    'num_freq_decade': 5,  # Number of frequency points per decade for C-V-F sweep
    'delay': 0.1
}

class CVMeasurement:
    def __init__(self, settings, lcr_meter=None):
        self.settings = settings
        self.lcr_meter = lcr_meter if lcr_meter is not None else KeysightE4980A('lcr_meter', self.settings['lcr_meter_address'])
        self.lcr_meter.write('*RST')  # Reset instrument to default state to ensure correct data format
        self.lcr_meter.write('*CLS')  # Clear status/error queue
        self.lcr_meter.timeout(30)  # Increase timeout to 30s
        self.lcr_meter.write(":TRIG:SOUR INT")  # Ensure internal trigger (continuous mode)
        self.lcr_meter.frequency(self.settings['frequency'])
        self.lcr_meter.measurement_function(getattr(KeysightE4980AMeasurements, self.settings['measurement_function']))
        self.lcr_meter.voltage_level(self.settings['ac_voltage_level'])
        self.lcr_meter.dc_bias_enabled(self.settings['dc_bias_enabled'])

        # Print the initial settings for verification
        print("Initialized CV Measurement with settings:")
        for key, value in self.settings.items():
            print(f"  {key}: {value}")

    def perform_cv_sweep(self):
        print(f"{'Set (V)':<10} {'Read (V)':<10} {'Cap (F)':<15} {'Diss':<10} {'Dir':<5}")
        self.results = {'voltage': [], 'voltage_readback': [], 'capacitance': [], 'dissipation': [], 'direction': []}

        if self.settings['sweep_mode'] == 'double':
            if self.settings['step_volt'] is not None:
                v_sweep_fwd = np.arange(self.settings['start_volt'], self.settings['stop_volt'] + self.settings['step_volt'], self.settings['step_volt'])
                v_sweep_bwd = np.arange(self.settings['stop_volt'], self.settings['start_volt'] - self.settings['step_volt'], -self.settings['step_volt'])
                v_sweep = np.concatenate([v_sweep_fwd, v_sweep_bwd])
                directions = ['fwd'] * len(v_sweep_fwd) + ['bwd'] * len(v_sweep_bwd)
            else:
                v_sweep = np.concatenate([np.linspace(self.settings['start_volt'], self.settings['stop_volt'], self.settings['num_points']),
                                        np.linspace(self.settings['stop_volt'], self.settings['start_volt'], self.settings['num_points'])])
                directions = ['fwd'] * self.settings['num_points'] + ['bwd'] * self.settings['num_points']
        else:
            if self.settings['step_volt'] is not None:
                v_sweep = np.arange(self.settings['start_volt'], self.settings['stop_volt'] + self.settings['step_volt'], self.settings['step_volt'])
                directions = ['fwd'] * len(v_sweep)
            else:
                v_sweep = np.linspace(self.settings['start_volt'], self.settings['stop_volt'], self.settings['num_points'])
                directions = ['fwd'] * self.settings['num_points']

        for v, d in zip(v_sweep, directions):
            self.lcr_meter.dc_bias_voltage_level(v)
            time.sleep(self.settings['delay'])
            v_read = self.lcr_meter.dc_bias_voltage_level()
            meas = self.lcr_meter.measurement()
            print(f"{v:<10.4f} {v_read:<10.4f} {meas[0]:<15.4e} {meas[1]:<10.4e} {d:<5}")
            self.results['voltage'].append(v)
            self.results['voltage_readback'].append(v_read)
            self.results['capacitance'].append(meas[0])
            self.results['dissipation'].append(meas[1])
            self.results['direction'].append(d)

        self.results_df = pd.DataFrame(self.results)
        return self.results_df
    
    def perform_cvf_sweep(self):
        # Similar to perform_cv_sweep but with additional frequency sweep logic
        print(f"{'Set (V)':<10} {'Read (V)':<10} {'Freq (Hz)':<10} {'Cap (F)':<10} {'Diss':<10} {'Dir':<10}")
        self.results = {'voltage': [], 'voltage_readback': [], 'frequency': [], 'capacitance': [], 'dissipation': [], 'direction': []}
        freqs = np.logspace(np.log10(self.settings['start_freq']), np.log10(self.settings['stop_freq']), self.settings['num_freq_decade'] * int(np.log10(self.settings['stop_freq'] / self.settings['start_freq'])))
        if self.settings['sweep_mode'] == 'double':
            if self.settings['step_volt'] is not None:
                v_sweep_fwd = np.arange(self.settings['start_volt'], self.settings['stop_volt'] + self.settings['step_volt'], self.settings['step_volt'])
                v_sweep_bwd = np.arange(self.settings['stop_volt'], self.settings['start_volt'] - self.settings['step_volt'], -self.settings['step_volt'])
                v_sweep = np.concatenate([v_sweep_fwd, v_sweep_bwd])
                directions = ['fwd'] * len(v_sweep_fwd) + ['bwd'] * len(v_sweep_bwd)
            else:
                v_sweep = np.concatenate([np.linspace(self.settings['start_volt'], self.settings['stop_volt'], self.settings['num_points']),
                                        np.linspace(self.settings['stop_volt'], self.settings['start_volt'], self.settings['num_points'])])
                directions = ['fwd'] * self.settings['num_points'] + ['bwd'] * self.settings['num_points']
        else:
            if self.settings['step_volt'] is not None:
                v_sweep = np.arange(self.settings['start_volt'], self.settings['stop_volt'] + self.settings['step_volt'], self.settings['step_volt'])
                directions = ['fwd'] * len(v_sweep)
            else:
                v_sweep = np.linspace(self.settings['start_volt'], self.settings['stop_volt'], self.settings['num_points'])
                directions = ['fwd'] * self.settings['num_points']


        for v, d in zip(v_sweep, directions):
            self.lcr_meter.dc_bias_voltage_level(v)
            for f in freqs:
                self.lcr_meter.frequency(f)
                time.sleep(self.settings['delay'])
                v_read = self.lcr_meter.dc_bias_voltage_level()
                meas = self.lcr_meter.measurement()
                print(f"{v:<10.4f} {v_read:<10.4f} {f:<10.2e} {meas[0]:<10.4e} {meas[1]:<10.4e} {d:<10}")
                self.results['voltage'].append(v)
                self.results['voltage_readback'].append(v_read)
                self.results['frequency'].append(f)
                self.results['capacitance'].append(meas[0])
                self.results['dissipation'].append(meas[1])
                self.results['direction'].append(d)

        self.results_df = pd.DataFrame(self.results)
        return self.results_df
        
        