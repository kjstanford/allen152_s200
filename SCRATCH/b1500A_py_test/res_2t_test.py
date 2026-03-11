import time
start_time = time.time()

from initialize_smus import *
import numpy as np
import warnings
import os
import datetime
import pandas as pd
import matplotlib.pyplot as plt

def channel(smu_id):
    if smu_id == b1500.smu1:
        return 'C'
    elif smu_id == b1500.smu2:
        return 'D'
    elif smu_id == b1500.smu3:
        return 'E'
    elif smu_id == b1500.smu4:
        return 'F'
    else:
        raise ValueError("Invalid SMU ID")

# 1. Set Data Output Format
# Format 21: ASCII data format (12 digits data + 1 digit status)
# Mode 1: Returns data with channel identifiers (e.g., "SMU1", "Current")
b1500.data_format(21, mode=1)

# 2. Choose Measurement Mode
# 'STAIRCASE_SWEEP': Standard DC sweep (IV curve)
# Other options: 'SAMPLING' (Time domain), 'QUASI_PULSED_SPOT', 'MULTI_CHANNEL_SWEEP'
smuh = b1500.smu3
smul = b1500.smu4
b1500.meas_mode('STAIRCASE_SWEEP', smuh, smul)

# 3. Configure SMUs
for smu in [smuh, smul]:
    smu.enable()
    
    # ADC Type: 'HRADC' (High Resolution) or 'HSDADC' (High Speed)
    smu.adc_type = 'HRADC'
    
    smu.meas_range_current = 'Auto Ranging'
    
    # Measurement Operation Mode:
    # 'COMPLIANCE_SIDE': Measures the parameter limited by compliance (e.g., Current if forcing Voltage)
    # 'FORCE_SIDE': Measures the parameter being forced
    # 'COMPLIANCE_AND_FORCE_SIDE': Measures both
    smu.meas_op_mode = 'COMPLIANCE_SIDE'

# 4. ADC Integration Settings
# Mode 'AUTO': Automatically sets averaging based on range.
# Mode 'PLC': Power Line Cycles (e.g., 1 PLC = 1/50s or 1/60s integration). Good for noise rejection.
# Mode 'MANUAL': Specific number of samples.
b1500.adc_setup('HRADC', 'AUTO', 6)

# 5. Sweep Timing
# hold: Time before starting sweep (0s)
# delay: Time after hold before first step (0s)
# step_delay: Delay between steps (0s for max speed)
b1500.sweep_timing(hold=0, delay=0, step_delay=0)

# 6. Sweep Abort Conditions
# post='STOP': Output returns to the stop value after sweep. 'START' returns to start value.
b1500.sweep_auto_abort(False, post='STOP')

# 7. Configure Sweep Source (SMU1)
# Mode: 'LINEAR_DOUBLE' (Sweep Start -> Stop -> Start)
# Other modes: 'LINEAR_SINGLE' (Start -> Stop), 'LOG_SINGLE', 'LOG_DOUBLE'
nop = 21 # Number of points
smuh.staircase_sweep_source('VOLTAGE', 'LINEAR_DOUBLE', 'Auto Ranging', -3, 3, nop, 0.01)

# 8. Configure Constant Source (SMU2 - Ground)
smul.force('VOLTAGE', 'Auto Ranging', 0, 0.01)

# 9. Execute Measurement
b1500.check_errors()
b1500.clear_buffer()
b1500.clear_timer()
mstart_time = time.time()
b1500.send_trigger()

# 10. Read Data
b1500.check_idle() # Wait for completion

# Check for errors to confirm success
if not b1500.check_errors():
    print("Measurement successful!")
else:
    raise ValueError("Measurement failed due to errors.")

# Read raw data string directly to bypass driver shaping errors
raw_data_str = b1500.read()

mend_time = time.time()
print(f"Measurement Runtime: {mend_time - mstart_time:.4f} s")

raw_data_str_list = raw_data_str.strip().split(',')

# Parse the comma-separated string
# FMT 21 returns ASCII (13 digits data with header)
data_list = []
for item in raw_data_str.strip().split(','):
    if len(item) < 5: continue
    item_dict = {}
    item_dict['Value'] = float(item[-13:])
    item_dict['Channel'] = item[-15]
    item_dict['Type'] = 'Current' if item[-14] == 'I' else 'Voltage'
    data_list.append(item_dict)

# Convert list of dictionaries to pandas DataFrame
df = pd.DataFrame(data_list)

# 2. Create a "Group ID" for every 3 consecutive rows
# Since the index is 0, 1, 2, 3, 4, 5... 
# Integer division (// 3) gives 0, 0, 0, 1, 1, 1...
df['Group_ID'] = df.index // 3

# 3. Create the new column name combining Channel and Type
df['New_Column'] = df['Channel'] + '_' + df['Type']

# 4. Pivot the table
# index='Group_ID' -> Consolidates rows with the same ID
# columns='New_Column' -> Turns the values in this column into headers
# values='Value' -> The actual numbers to put in the cells
df_pivoted = df.pivot(index='Group_ID', columns='New_Column', values='Value')

# 5. Clean up (optional)
# Remove the index name and reset it
df_pivoted.columns.name = None
df_pivoted = df_pivoted.reset_index(drop=True)

data = df_pivoted


# Save Data to CSV
script_name = os.path.splitext(os.path.basename(__file__))[0]
save_dir = os.path.join("saved_data", script_name)
os.makedirs(save_dir, exist_ok=True)

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
csv_path = os.path.join(save_dir, f"{script_name}_{timestamp}.csv")
data.to_csv(csv_path, index=False)
print(f"Data saved to: {csv_path}")

# 11. Process Data and Calculate R
currents = data[f"{channel(smuh)}_Current"].to_numpy()
voltages = data[f"{channel(smuh)}_Voltage"].to_numpy()

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

end_time = time.time()
print(f"Total Runtime: {end_time - start_time:.4f} s")

# 10. Plot
plt.figure()
plt.plot(voltages, currents, 'o-', label='Measured')
plt.plot(np.polyval(fit, currents), currents, 'r--', label=f'Fit (R={resistance:.2e} $\\Omega$)')
plt.xlabel('Voltage (V)')
plt.ylabel('Current (A)')
plt.title('2-Terminal IV Curve')
plt.legend()
plt.grid(True)
plt.show()