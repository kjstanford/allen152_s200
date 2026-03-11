import qcodes as qc
from qcodes.instrument_drivers.Keysight.keysightb1500 import KeysightB1500, constants
from qcodes.dataset import (
    initialise_database,
    Measurement,
    load_or_create_experiment,
    plot_dataset,
)
import numpy as np
import pandas as pd
import os
import datetime
import matplotlib.pyplot as plt
import yaml

sample_name_id_map = {'cap_structures_test': 'S[0]'}

script_name = os.path.splitext(os.path.basename(__file__))[0]

# Define Measurement Settings
settings = {
    'sample_name': 'cap_structures_test',
    'device_group': 'G[mism]_W[200u]',
    'sweep_smu': 'smu3',
    'ground_smu': 'smu4',
    'start_voltage': -3.0,
    'end_voltage': 3.0,
    'num_steps': 21,
    'compliance': 100e-3
}

# 1. Initialize QCoDeS Database and Experiment
initialise_database()
experiment = load_or_create_experiment(
    experiment_name="B1500A_2T_IV_Test", sample_name=settings['sample_name']
)

# 2. Connect to Instrument
# Using the address found in your initialize_smus.py
resource_name = "GPIB0::16::INSTR"
try:
    # Close existing instance if it exists to avoid conflicts
    KeysightB1500.find_instrument("b1500").close()
except KeyError:
    pass

b1500 = KeysightB1500("b1500", resource_name)

# 3. Define SMUs
# The driver automatically detects modules and assigns them to b1500.smu1, b1500.smu2, etc.
smu_sweep = getattr(b1500, settings['sweep_smu'])  # High side (Sweep Source)
smu_ground = getattr(b1500, settings['ground_smu'])  # Low side (Ground)

# Enable channels
smu_sweep.enable_outputs()
smu_ground.enable_outputs()

# 4. Configure Sweep Parameters
# Configure Sweep SMU
# We use setup_staircase_sweep to define the sweep parameters
smu_sweep.setup_staircase_sweep(
    v_start=settings['start_voltage'],
    v_end=settings['end_voltage'],
    n_steps=settings['num_steps'],
    sweep_mode=3,  # 3 corresponds to Linear Double Sweep (Start -> End -> Start)
    v_src_range=constants.VOutputRange.AUTO,
    i_comp=settings['compliance'],  # 100mA compliance
    i_meas_range=constants.IMeasRange.AUTO,
)

# Configure Ground SMU
# Force 0V and measure current
smu_ground.voltage(0)
smu_ground.measurement_operation_mode(1)  # 1: Compliance Side
smu_ground.current_measurement_range(constants.IMeasRange.AUTO)

# 5. Set Measurement Mode
# This tells the mainframe we are doing a Staircase Sweep using these two channels
b1500.set_measurement_mode(
    mode=constants.MM.Mode.STAIRCASE_SWEEP,
    channels=(smu_sweep.channels[0], smu_ground.channels[0]),
)

# 6. Prepare Measurement Object
meas = Measurement(exp=experiment)

# Configure the MultiParameter that runs the sweep
# We name the outputs to match the channels dynamically
b1500.run_iv_staircase_sweep.set_names_labels_and_units(
    names=(f"{smu_sweep.short_name}_current", f"{smu_ground.short_name}_current"),
    labels=(f"{smu_sweep.short_name.upper()} Current", f"{smu_ground.short_name.upper()} Current"),
    units=("A", "A"),
)

# Register the parameter
meas.register_parameter(b1500.run_iv_staircase_sweep)

print("Starting Measurement...")

# 7. Run Measurement
with meas.run() as datasaver:
    # This single call triggers the sweep and returns all data
    data = b1500.run_iv_staircase_sweep()
    
    # Save data to QCoDeS database
    datasaver.add_result((b1500.run_iv_staircase_sweep, data))
    
    dataset = datasaver.dataset

print("Measurement complete.")

# 8. Process and Save Data (Pandas)
# Convert QCoDeS dataset to pandas DataFrame
df = dataset.to_pandas_dataframe()

# The dataframe index usually contains the setpoints (Voltage).
# We reset index to make Voltage a column.
df = df.reset_index()

# Rename columns for clarity (QCoDeS names can be verbose)
# The setpoint column name depends on the driver internals, usually 'b1500_smu1_...'
# We'll identify columns dynamically or just map them if known.
# Typical structure: 'b1500_smuX_voltage', 'smuX_current', 'smuY_current'
print("Columns found:", df.columns)

# Save to CSV
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

# 9. Calculate Resistance
# Assuming Sweep SMU Current vs Sweep SMU Voltage (Setpoint)
# We need to find the voltage column name. It usually contains 'voltage'.
voltage_col = [c for c in df.columns if 'voltage' in c.lower()][0]
current_col = [c for c in df.columns if 'current' in c.lower() and smu_sweep.short_name in c.lower()][0]

voltages = df[voltage_col].to_numpy()
currents = df[current_col].to_numpy()

# Filter data to exclude compliance/saturation regions for the linear fit
# We select points where the current is within the linear region (e.g., < 95% of max current)
abs_currents = np.abs(currents)
max_current = np.max(abs_currents)
mask = abs_currents < (0.95 * max_current)

if np.sum(mask) > 2:
    fit = np.polyfit(currents[mask], voltages[mask], 1)
else:
    fit = np.polyfit(currents, voltages, 1)

resistance = fit[0]

print(f"Measured Resistance: {resistance:.4e} Ohms")

# 10. Plot
fig = plt.figure()
plt.plot(voltages, currents, 'o-', label='Measured')
plt.plot(np.polyval(fit, currents), currents, 'r--', label=f'Fit (R={resistance:.2e} $\\Omega$)')
plt.xlabel('Voltage (V)')
plt.ylabel('Current (A)')
plt.title('2-Terminal IV Curve')
plt.legend()
plt.grid(True)
plt.show(block=False)
plt.pause(5)

# Close connection
b1500.close()

# Save Plot and Data for successful sweep
main_save_dir = os.path.join("main_saved_data", script_name, sample_name_id_map.get(settings['sample_name'], 'Unknown'), settings['device_group'])
os.makedirs(main_save_dir, exist_ok=True)
if input("Save plot? (y/n): ").lower() == 'y':
    Ridx = input("Enter device row index [start from 1]: ")
    Cidx = input("Enter device column index [start from 1]: ")
    runidx = input("Enter run index [start from 1]: ")
    device_pos = f'R[{Ridx}]_C[{Cidx}]_run[{runidx}]'
    plot_path = os.path.join(main_save_dir, f"{script_name}_{sample_name_id_map.get(settings['sample_name'], 'Unknown')}_{settings['device_group']}_{device_pos}_{timestamp}.png")
    fig.savefig(plot_path)
    print(f"Plot saved to: {plot_path}")
    csv_path = os.path.join(main_save_dir, f"{script_name}_{sample_name_id_map.get(settings['sample_name'], 'Unknown')}_{settings['device_group']}_{device_pos}_{timestamp}.csv")
    df.to_csv(csv_path, index=False)
    print(f"Data saved to: {csv_path}")
    settings_path = os.path.join(main_save_dir, f"{script_name}_{sample_name_id_map.get(settings['sample_name'], 'Unknown')}_{settings['device_group']}_{device_pos}_{timestamp}_settings.yaml")
    with open(settings_path, 'w') as f:
        yaml.dump(output_settings, f, sort_keys=False)
    print(f"Settings saved to: {settings_path}")
plt.close()
