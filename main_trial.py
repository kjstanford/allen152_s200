# from b1500A_utils.initialize_smus import *
# from b1500A_utils.FET_three_terminal import IdVg_single_Vd, IdVg_multi_Vd
from keithley4200_utils.k4200_helpers import *
from keithley4200_utils.pmu_segarb_example_gen import *
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
# from S200_utils.initialize_s200 import *
# from S200_utils.chuck_control import *
import time
import os

if __name__ == "__main__":
    my4200 = connect_4200()
    rpm_check = check_for_rpms(my4200)
    print(rpm_check)

    # idvg_data = idvg_sweep_smu(my4200=my4200, vgs_start=0, vgs_stop=1, vgs_step=0.1, vds_const=0.1,
    #            gatechan=1, sourcechan=2, drainchan=3,
    #            gatecomp=0.01, sourcecomp=0.01, draincomp=0.01,
    #            gaterange=100e-9, sourcerange=100e-9, drainrange=100e-9,
    #            dual_sweep = 1, integ_time = 3,
    #            hold_time = 0, delay_time = 0.001, standby = 1, resolution = 5)
    
    # # print(idvg_data)
    # vgs_data = idvg_data['VG'].to_numpy()
    # id_data = idvg_data['ID'].to_numpy()
    # plt.figure(figsize=(8, 6))
    # plt.semilogy(vgs_data, np.abs(id_data), marker='o', linestyle='-', linewidth=2, markersize=8, color='r')
    # plt.xlabel('Gate Voltage (V)')
    # plt.ylabel('Drain Current (A)')
    # plt.title('Id-Vg Curve')
    # plt.grid(True)
    # plt.show(block=False)
    # plt.pause(3)
    # plt.close()

    # # fast_ramp_rows = my_fast_staircase_ramp_gen_idvg(start_vg=0, stop_vg=2, step_vg=0.1, bias_vd=0.1, trf=1e-6, thold=1e-5)
    # # print_rows(fast_ramp_rows)
    # # df = segarb_rows_to_df(segarb_rows=fast_ramp_rows)
    # pulse_stress_rows = my_pulse_gen_stress(pulse_vg=2, stdby_vg=0, pulse_vd=0.1, stdby_vd=0.1, tdelay=1e-3, tpulse=1e-3, trf=1e-5, duty_cycle=0.5)
    # print_rows(pulse_stress_rows)
    # df = segarb_rows_to_df(segarb_rows=pulse_stress_rows)
    # SegTime = df['SegTime (s)'].to_list()
    # StartVCh1 = df['StartVCh1 (V)'].to_list()
    # StopVCh1 = df['StopVCh1 (V)'].to_list()
    # StartVCh2 = df['StartVCh2 (V)'].to_list()
    # StopVCh2 = df['StopVCh2 (V)'].to_list()
    # SSRCtrlCh1 = df['SSRCtrlCh1 (0/1)'].to_list()
    # SSRCtrlCh2 = df['SSRCtrlCh2 (0/1)'].to_list()
    # SegTrigOut = df['SegTrigOut (0/1)'].to_list()
    # df.to_excel("pulse_stress_segarb.xlsx", index=False)

    # pmu_segarb_example_data = pmu_segarb_example(my4200=my4200, VRangeCh1=10, IRangeCh1=1e-6, VRangeCh2=10, IRangeCh2=1e-6, NumWaveforms=1, DUTResCh1=1e6, DUTResCh2=1e6, MaxSheetPoints=5000, SegTime=SegTime, StartVCh1=StartVCh1, StopVCh1=StopVCh1, StartVCh2=StartVCh2, StopVCh2=StopVCh2, SSRCtrlCh1=SSRCtrlCh1, SSRCtrlCh2=SSRCtrlCh2, SegTrigOut=SegTrigOut, SMU_V=0, SMU_Irange=0.01, SMU_Icomp=0.01, SMU_ID="NONE", PMU_ID="PMU1", Output_size=10000)
    # print(pmu_segarb_example_data)
    # TimeOutput_data = pmu_segarb_example_data['TimeOutput'].to_numpy()
    # VMeasCh1_data = pmu_segarb_example_data['VMeasCh1'].to_numpy()
    # IMeasCh1_data = pmu_segarb_example_data['IMeasCh1'].to_numpy()
    # VMeasCh2_data = pmu_segarb_example_data['VMeasCh2'].to_numpy()
    # IMeasCh2_data = pmu_segarb_example_data['IMeasCh2'].to_numpy()
    # plt.figure(figsize=(8, 6))
    # plt.subplot(2, 1, 1)
    # plt.plot(TimeOutput_data, VMeasCh1_data, marker='o', linestyle='-', linewidth=2, markersize=8, color='b')
    # plt.xlabel('Time (s)')
    # plt.ylabel('Measured Voltage Ch1 (V)')
    # plt.title('Measured Voltage on Channel 1 vs Time')
    # plt.grid(True)
    # plt.subplot(2, 1, 2)
    # plt.plot(TimeOutput_data, VMeasCh2_data, marker='o', linestyle='-', linewidth=2, markersize=8, color='r')
    # plt.xlabel('Time (s)')
    # plt.ylabel('Measured Voltage Ch2 (V)')
    # plt.title('Measured Voltage on Channel 2 vs Time')
    # plt.grid(True)
    # plt.tight_layout()
    # plt.show(block=False)
    # plt.pause(5)
    # plt.close()

    # keithley_beep_BeepLib(my4200=my4200, freq=2000, duration=5000)

    nvm_dcSweep_data = keithley_nvm_dcSweep(my4200=my4200)
    print(nvm_dcSweep_data)
    vforce_data = nvm_dcSweep_data['Vforce'].to_numpy()
    imeasd_data = nvm_dcSweep_data['Imeasd'].to_numpy()
    timed_data = nvm_dcSweep_data['Timed'].to_numpy()
    plt.figure(figsize=(8, 6))
    plt.semilogy(vforce_data, np.abs(imeasd_data), marker='o', linestyle='-', linewidth=2, markersize=8, color='b')
    plt.xlabel('Force Voltage (V)')
    plt.ylabel('Current (A)')
    plt.title('Id-Vg Curve')
    plt.grid(True)
    plt.show(block=False)
    plt.pause(3)
    plt.close()


# mode = 'nosave'  

# def measure(descriptor = None):
#     data = IdVg_multi_Vd(
#         b1500,
#         smu_gate=b1500.smu4,
#         smu_drain=b1500.smu2,
#         smu_source=b1500.smu3,
#         gate_start=-2,
#         gate_stop=2,
#         gate_step=0.025,
#         drain_list=[0.05, 1.00],
#         Irange='1 nA limited auto ranging',
#         Vrange='2 V limited auto ranging'
#     )

#     # Plot Id-Vg curves for different drain voltages
#     plt.figure(figsize=(8, 6))
#     for Vd in data['Drain_Voltage'].unique():
#         Vd_data = data[data['Drain_Voltage'] == Vd]
#         plt.semilogy(Vd_data['Gate_Voltage'].to_numpy(), np.abs(Vd_data['Drain_Current'].to_numpy()), label=f'Vd = {Vd} V')
#     plt.xlabel('Gate Voltage (V)')
#     plt.ylabel('Drain Current (A)')
#     plt.title('Id-Vg Curves for Different Drain Voltages')
#     plt.legend()
#     plt.grid(True)
#     plt.show(block=False)
#     plt.pause(10)
#     plt.close()

#     if mode == 'save':
#         test_name = 'IdVg_multi_Vd'
#         timestamp = time.strftime("%Y%m%d_%H%M%S")
#         if descriptor is not None:
#             timestamp += f"_{descriptor}"
#         save_dir = os.path.join("saved_data", "trial_run_Jan09_2026")
#         os.makedirs(save_dir, exist_ok=True)
#         save_path = os.path.join(save_dir, f"{test_name}_{timestamp}.csv")
#         data.to_csv(save_path, index=False)
#         print(f"Data saved to: {save_path}")

# def main_trial():
#     move_contact_height(prober)
#     time.sleep(2)
#     measure()
#     time.sleep(2)
#     move_separation_height(prober)
#     time.sleep(2)

#     move_relative(prober, 8000, 0)  # Move chuck by 8000 microns in X direction
#     time.sleep(2)

#     move_contact_height(prober)
#     time.sleep(2)
#     measure()
#     time.sleep(2)
#     move_separation_height(prober)
#     print("Measurement sequence completed.")
#     prober.close()
#     rm.close()

# def main():
#     total_x_displace = 0
#     total_y_displace = 0

#     dev_x_pitch = 200
#     dev_y_pitch = -200
#     dev_per_L = 13
#     DieR_idx_list = [0, 1]
#     DieC_idx_list = [0, 1]
#     die_x_pitch = 8000
#     die_y_pitch = 8000

#     L_list = [60, 80, 100, 150, 200, 250, 300, 400, 500, 700, 1000]

#     for DieR_idx in DieR_idx_list:
#         for DieC_idx in DieC_idx_list:
#             print(f"Moving to Die Row={DieR_idx}, Column={DieC_idx}...")
#             move_relative(-total_x_displace + die_x_pitch * DieC_idx, -total_y_displace + die_y_pitch * DieR_idx)
#             total_x_displace = die_x_pitch * DieC_idx
#             total_y_displace = die_y_pitch * DieR_idx
#             for L in L_list:
#                 for dev_idx in range(dev_per_L):
#                     print(f"Measuring device with L={L} nm at position X={total_x_displace} um, Y={total_y_displace} um")
#                     time.sleep(2)
#                     measure(descriptor=f"DieR{DieR_idx}_DieC{DieC_idx}_L{L}nm_Dev{dev_idx}")
#                     if dev_idx < dev_per_L - 1:
#                         move_relative(dev_x_pitch, 0)
#                         total_x_displace += dev_x_pitch
#                 move_relative(-total_x_displace, dev_y_pitch)
#                 total_x_displace = 0
#                 total_y_displace += dev_y_pitch  


# if __name__ == "__main__":
#     main_trial()

    