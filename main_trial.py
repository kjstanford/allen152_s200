from b1500A_utils.initialize_smus import *
from b1500A_utils.FET_three_terminal import IdVg_single_Vd, IdVg_multi_Vd
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from S200_utils.initialize_s200 import *
from S200_utils.chuck_control import *
import time
import os

mode = 'nosave'  

def measure(descriptor = None):
    data = IdVg_multi_Vd(
        b1500,
        smu_gate=b1500.smu4,
        smu_drain=b1500.smu2,
        smu_source=b1500.smu3,
        gate_start=-2,
        gate_stop=2,
        gate_step=0.025,
        drain_list=[0.05, 1.00],
        Irange='1 nA limited auto ranging',
        Vrange='2 V limited auto ranging'
    )

    # Plot Id-Vg curves for different drain voltages
    plt.figure(figsize=(8, 6))
    for Vd in data['Drain_Voltage'].unique():
        Vd_data = data[data['Drain_Voltage'] == Vd]
        plt.semilogy(Vd_data['Gate_Voltage'].to_numpy(), np.abs(Vd_data['Drain_Current'].to_numpy()), label=f'Vd = {Vd} V')
    plt.xlabel('Gate Voltage (V)')
    plt.ylabel('Drain Current (A)')
    plt.title('Id-Vg Curves for Different Drain Voltages')
    plt.legend()
    plt.grid(True)
    plt.show(block=False)
    plt.pause(10)
    plt.close()

    if mode == 'save':
        test_name = 'IdVg_multi_Vd'
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if descriptor is not None:
            timestamp += f"_{descriptor}"
        save_dir = os.path.join("saved_data", "trial_run_Jan09_2026")
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f"{test_name}_{timestamp}.csv")
        data.to_csv(save_path, index=False)
        print(f"Data saved to: {save_path}")

def main_trial():
    measure()
    time.sleep(2)
    move_relative(8000, 0)  # Move chuck by 8000 microns in X direction
    time.sleep(2)
    measure()
    move_relative(0, 8000)
    time.sleep(2)
    measure()
    move_relative(-8000, 0)
    time.sleep(2)
    measure()
    move_relative(0, -8000)
    print("Measurement sequence completed.")
    prober.close()
    rm.close()

def main():
    total_x_displace = 0
    total_y_displace = 0

    dev_x_pitch = 200
    dev_y_pitch = -200
    dev_per_L = 13
    DieR_idx_list = [0, 1]
    DieC_idx_list = [0, 1]
    die_x_pitch = 8000
    die_y_pitch = 8000

    L_list = [60, 80, 100, 150, 200, 250, 300, 400, 500, 700, 1000]

    for DieR_idx in DieR_idx_list:
        for DieC_idx in DieC_idx_list:
            print(f"Moving to Die Row={DieR_idx}, Column={DieC_idx}...")
            move_relative(-total_x_displace + die_x_pitch * DieC_idx, -total_y_displace + die_y_pitch * DieR_idx)
            total_x_displace = die_x_pitch * DieC_idx
            total_y_displace = die_y_pitch * DieR_idx
            for L in L_list:
                for dev_idx in range(dev_per_L):
                    print(f"Measuring device with L={L} nm at position X={total_x_displace} um, Y={total_y_displace} um")
                    time.sleep(2)
                    measure(descriptor=f"DieR{DieR_idx}_DieC{DieC_idx}_L{L}nm_Dev{dev_idx}")
                    if dev_idx < dev_per_L - 1:
                        move_relative(dev_x_pitch, 0)
                        total_x_displace += dev_x_pitch
                move_relative(-total_x_displace, dev_y_pitch)
                total_x_displace = 0
                total_y_displace += dev_y_pitch  


if __name__ == "__main__":
    main_trial()

    