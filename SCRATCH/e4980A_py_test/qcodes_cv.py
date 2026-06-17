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

sample_name_id_map = {'cap_structures_test': 'S[0]'}

script_name = os.path.splitext(os.path.basename(__file__))[0]

# Define Measurement Settings
settings = {
    'sample_name': 'cap_structures_test',
    'device_group': 'G[mim]_W[200u]',
    'frequency': 1e6,
    'measurement_function': 'CPRP',  # Corresponds to KeysightE4980AMeasurements.CPRP
    'ac_voltage_level': 0.03,
    'dc_bias_enabled': True,
    'start_volt': -3.5,
    'stop_volt': 2,
    'sweep_mode': 'double',  # 'single' or 'double'
    'num_points': 21,
    'delay': 0.1
}

# 1. Initialize the QCoDeS database
initialise_database()
new_experiment(name='CV_Sweep_E4980A', sample_name=settings['sample_name'])
# 2. Connect to the Keysight E4980A
# Replace 'USB0::...' with your actual VISA resource address
lcr_meter = KeysightE4980A('lcr_meter', 'GPIB0::17::INSTR')
lcr_meter.write('*RST')  # Reset instrument to default state to ensure correct data format
lcr_meter.write('*CLS')  # Clear status/error queue
lcr_meter.timeout(30)  # Increase timeout to 30s
lcr_meter.write(":TRIG:SOUR INT")  # Ensure internal trigger (continuous mode)

# 3. Configure the LCR Meter
lcr_meter.frequency(settings['frequency'])
lcr_meter.measurement_function(getattr(KeysightE4980AMeasurements, settings['measurement_function']))
lcr_meter.voltage_level(settings['ac_voltage_level'])
lcr_meter.dc_bias_enabled(settings['dc_bias_enabled'])

# Print current settings to verify
print(f"Frequency: {lcr_meter.frequency()} Hz")
print(f"Function: {lcr_meter.measurement_function()}")
print(f"AC Voltage: {lcr_meter.voltage_level()} V")
print(f"DC Bias Enabled: {lcr_meter.dc_bias_enabled()}")
print(f"DC Bias Voltage: {lcr_meter.dc_bias_voltage_level()} V")

# 4. Define Sweep Parameters for C-V Measurement (DC Bias Sweep)

# 5. Run the Sweep (Manual Loop)
print(f"{'Set (V)':<10} {'Read (V)':<10} {'Cap (F)':<15} {'Diss':<10} {'Dir':<5}")
results = {'voltage': [], 'voltage_readback': [], 'capacitance': [], 'dissipation': [], 'direction': []}

if settings['sweep_mode'] == 'double':
    v_sweep = np.concatenate([np.linspace(settings['start_volt'], settings['stop_volt'], settings['num_points']),
                              np.linspace(settings['stop_volt'], settings['start_volt'], settings['num_points'])])
    directions = ['fwd'] * settings['num_points'] + ['bwd'] * settings['num_points']
else:
    v_sweep = np.linspace(settings['start_volt'], settings['stop_volt'], settings['num_points'])
    directions = ['fwd'] * settings['num_points']

for v, d in zip(v_sweep, directions):
    lcr_meter.dc_bias_voltage_level(v)
    time.sleep(settings['delay'])
    v_read = lcr_meter.dc_bias_voltage_level()
    meas = lcr_meter.measurement()
    print(f"{v:<10.4f} {v_read:<10.4f} {meas[0]:<15.4e} {meas[1]:<10.4e} {d:<5}")
    results['voltage'].append(v)
    results['voltage_readback'].append(v_read)
    results['capacitance'].append(meas[0])
    results['dissipation'].append(meas[1])
    results['direction'].append(d)

df = pd.DataFrame(results)

# Save Data to CSV
save_dir = os.path.join("saved_data", script_name)
os.makedirs(save_dir, exist_ok=True)

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
csv_path = os.path.join(save_dir, f"{script_name}_{timestamp}.csv")
df.to_csv(csv_path, index=False)
print(f"Data saved to: {csv_path}")

# Save Settings to YAML
settings_path = os.path.join(save_dir, f"{script_name}_{timestamp}_settings.yaml")
output_settings = settings.copy()
output_settings.update({'timestamp': timestamp, 'script_name': script_name})
with open(settings_path, 'w') as f:
    yaml.dump(output_settings, f, sort_keys=False)
print(f"Settings saved to: {settings_path}")

measured_C = np.mean(df['capacitance'].to_numpy())  # Extract Capacitance data
print(f"Measured Capacitance: {measured_C*1e12:.2f} pF")

# 6. Close the Connection
lcr_meter.dc_bias_enabled(False)
lcr_meter.dc_bias_voltage_level(0)
lcr_meter.voltage_level(0)
lcr_meter.write('*CLS')  # Clear status/error queue

# Disconnect
lcr_meter.close()

# Plotting
fig = plt.figure()
voltage_col = next((c for c in df.columns if 'voltage' in c.lower() or 'bias' in c.lower()), None)
x_data = df[voltage_col] if voltage_col else np.linspace(settings['start_volt'], settings['stop_volt'], settings['num_points'])
xlabel = voltage_col if voltage_col else 'Voltage (V)'

if 'direction' in df.columns:
    fwd_mask = df['direction'] == 'fwd'
    bwd_mask = df['direction'] == 'bwd'
    plt.plot(df[fwd_mask][voltage_col], df[fwd_mask]['capacitance'], 'b.-', label='Forward')
    plt.plot(df[bwd_mask][voltage_col], df[bwd_mask]['capacitance'], 'r.-', label='Backward')
    plt.legend()
else:
    plt.plot(x_data, df['capacitance'], 'o-')

plt.xlabel(xlabel)
plt.ylabel('Capacitance (F)')
plt.title(f'C-V Sweep: {script_name}')
plt.grid(True)
plt.tight_layout()
plt.show(block=False)
plt.pause(5)

# Save Plot and Data for successful sweep
main_save_dir = os.path.join("main_saved_data", script_name, sample_name_id_map[settings['sample_name']], settings['device_group'])
os.makedirs(main_save_dir, exist_ok=True)
if input("Save plot? (y/n): ").lower() == 'y':
    Ridx = input("Enter device row index [start from 1]: ")
    Cidx = input("Enter device column index [start from 1]: ")
    runidx = input("Enter run index [start from 1]: ")
    device_pos = f'R[{Ridx}]_C[{Cidx}]_run[{runidx}]'
    plot_path = os.path.join(main_save_dir, f"{script_name}_{sample_name_id_map[settings['sample_name']]}_{settings['device_group']}_{device_pos}_{timestamp}.png")
    fig.savefig(plot_path)
    print(f"Plot saved to: {plot_path}")
    csv_path = os.path.join(main_save_dir, f"{script_name}_{sample_name_id_map[settings['sample_name']]}_{settings['device_group']}_{device_pos}_{timestamp}.csv")
    df.to_csv(csv_path, index=False)
    print(f"Data saved to: {csv_path}")
    settings_path = os.path.join(main_save_dir, f"{script_name}_{sample_name_id_map[settings['sample_name']]}_{settings['device_group']}_{device_pos}_{timestamp}_settings.yaml")
    with open(settings_path, 'w') as f:
        yaml.dump(output_settings, f, sort_keys=False)
    print(f"Settings saved to: {settings_path}")
plt.close()