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
    """
    Return the single-letter channel identifier used in B1500A FMT 21 ASCII output.

    The B1500A encodes each measurement channel as a letter in its raw data string
    (C = slot 1, D = slot 2, E = slot 3, F = slot 4).  This helper maps an SMU
    object back to that letter so parsed DataFrame columns (e.g. 'E_Current') can
    be addressed by terminal name rather than by raw channel letter.

    Parameters
    ----------
    smu_id : SMU instance
        One of b1500.smu1 through b1500.smu4.

    Returns
    -------
    str
        Single uppercase letter ('C', 'D', 'E', or 'F').

    Raises
    ------
    ValueError
        If smu_id does not match any of the four expected SMU slots.
    """
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

# --- Configuration ---
smu_gate = b1500.smu3    # Gate (Sweep)
smu_drain = b1500.smu2   # Drain (Bias) - Change to smu1 if needed
smu_source = b1500.smu4  # Source (Ground)

gate_start = -2
gate_end = 2
gate_step = 0.025
num_points = int((gate_end - gate_start) / gate_step) + 1
drain_voltage = 0.05      # V_DS Bias

# 1. Set Data Output Format
# Format 21: ASCII data format (12 digits data + 1 digit status)
# Mode 1: Returns data with channel identifiers
b1500.data_format(21, mode=1)

# 2. Choose Measurement Mode
# 'STAIRCASE_SWEEP': Standard DC sweep
# We include all 3 SMUs to measure currents at Gate, Drain, and Source
b1500.meas_mode('STAIRCASE_SWEEP', smu_gate, smu_drain, smu_source)

# 3. Configure SMUs
for smu in [smu_gate, smu_drain, smu_source]:
    smu.enable()
    smu.adc_type = 'HRADC'
    smu.meas_range_current = '1 nA limited auto ranging'
    smu.meas_op_mode = 'COMPLIANCE_SIDE'

# 4. ADC Integration Settings
b1500.adc_setup('HRADC', 'AUTO', 6)

# 5. Sweep Timing
b1500.sweep_timing(hold=0, delay=0, step_delay=0)

# 6. Sweep Abort Conditions
b1500.sweep_auto_abort(False, post='STOP')

# 7. Configure Sweep Source (Gate)
smu_gate.staircase_sweep_source('VOLTAGE', 'LINEAR_DOUBLE', '2 V limited auto ranging', gate_start, gate_end, num_points, 0.01)

# 8. Configure Constant Sources
smu_drain.force('VOLTAGE', '2 V limited auto ranging', drain_voltage, 0.01)
smu_source.force('VOLTAGE', '2 V limited auto ranging', 0, 0.01)

# 9. Execute Measurement
b1500.check_errors()
b1500.clear_buffer()
b1500.clear_timer()
mstart_time = time.time()
b1500.send_trigger()

# 10. Read Data
b1500.check_idle() # Wait for completion

if not b1500.check_errors():
    print("Measurement successful!")
else:
    print("Measurement completed with errors (check instrument logs).")

raw_data_str = b1500.read()
mend_time = time.time()
print(f"Measurement Runtime: {mend_time - mstart_time:.4f} s")

# Parse Data
data_list = []
for item in raw_data_str.strip().split(','):
    if len(item) < 5: continue
    item_dict = {}
    item_dict['Value'] = float(item[-13:])
    item_dict['Channel'] = item[-15]
    item_dict['Type'] = 'Current' if item[-14] == 'I' else 'Voltage'
    data_list.append(item_dict)

df = pd.DataFrame(data_list)

# Determine items per step dynamically
# Typically: Gate(V), Gate(I), Drain(I), Source(I) -> 4 items per step
unique_params = df[['Channel', 'Type']].drop_duplicates()
items_per_step = len(unique_params)
print(f"Detected {items_per_step} items per measurement step.")

df['Group_ID'] = df.index // items_per_step
df['New_Column'] = df['Channel'] + '_' + df['Type']
df_pivoted = df.pivot(index='Group_ID', columns='New_Column', values='Value')
df_pivoted.columns.name = None
df_pivoted = df_pivoted.reset_index(drop=True)
data = df_pivoted

# 11. Plot Transfer Curve
gate_ch = channel(smu_gate)
drain_ch = channel(smu_drain)

vg_col = f"{gate_ch}_Voltage"
id_col = f"{drain_ch}_Current"
ig_col = f"{gate_ch}_Current"

if vg_col in data.columns and id_col in data.columns:
    plt.figure()
    plt.semilogy(data[vg_col], np.abs(data[id_col]), 'o-', label=f'Drain Current (Vds={drain_voltage}V)')
    if ig_col in data.columns:
        plt.semilogy(data[vg_col], np.abs(data[ig_col]), 'x--', label='Gate Current')
    plt.xlabel('Gate Voltage (V)')
    plt.ylabel('Current (A)')
    plt.title('3T Transfer Characteristic')
    plt.legend()
    plt.grid(True, which="both", ls="-")
    plt.show()

# Save Data
script_name = os.path.splitext(os.path.basename(__file__))[0]
save_dir = os.path.join("saved_data", script_name)
os.makedirs(save_dir, exist_ok=True)

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
descriptor = input('Enter a descriptor for the file: ')
if descriptor:
    timestamp += f"_{descriptor}"
csv_path = os.path.join(save_dir, f"{script_name}_{timestamp}.csv")
data.to_csv(csv_path, index=False)
print(f"Data saved to: {csv_path}")

end_time = time.time()
print(f"Total Runtime: {end_time - start_time:.4f} s")