import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import time
from math import ceil, floor
from data_processing_utils.IdVg_param_extract import *
from b1500A_utils.FET_three_terminal import *
from S200_utils.chuck_control import *
from e4980A_utils.qcodes_cv import *

def measure_initial_scan_v2(myb1500=None, smu_gate=None, smu_drain=None, smu_source=None, configs={}, data_all=None, descriptor=None, save_dir=None, mode=None, W=None, L=None):
    print("\n################################################")
    print("Starting initial Id-Vg scan to evaluate device...")
    skip_device_flag = False
    gate_start = configs.get('default_start', -0.5)
    gate_stop = configs.get('default_stop', 1.0)
    gate_step = configs.get('scan_step', 0.05)
    start_limit = configs.get('start_limit', -2.0)
    Vdscan = configs.get('Vdsat', 1.5)
    Irange = configs.get('Irange', '1 nA limited auto ranging')
    Vrange = configs.get('Vrange', '2 V limited auto ranging')
    new_gate_start = gate_start

    if mode == 'debug' and data_all is not None:
        data = data_all[data_all['Drain_Voltage'] == Vdscan]
    else:
        if myb1500 is None or smu_gate is None or smu_drain is None or smu_source is None:
            raise Exception("B1500 and SMUs must be initialized before calling measure_initial_scan in non-debug mode.")
        
        # Initial Id-Vg scan to check if device is working / measuring VT
        data = IdVg_single_Vd(
            b1500=myb1500,
            smu_gate=smu_gate,
            smu_drain=smu_drain,
            smu_source=smu_source,
            gate_start=gate_start,
            gate_stop=gate_stop,
            gate_step=gate_step,
            drain_voltage=Vdscan,
            Irange=Irange,
            Vrange=Vrange
        )

        # Plot Id-Vg curve
        plt.figure(figsize=(8, 6))
        plt.semilogy(data['Gate_Voltage'].to_numpy(), np.abs(data['Drain_Current'].to_numpy()), label=f'Drain Current')
        plt.semilogy(data['Gate_Voltage'].to_numpy(), np.abs(data['Gate_Current'].to_numpy()), label=f'Gate Current')
        plt.semilogy(data['Gate_Voltage'].to_numpy(), np.abs(data['Source_Current'].to_numpy()), label=f'Source Current')
        plt.xlabel('Gate Voltage (V)')
        # plt.ylabel('Drain Current (A)')
        plt.ylabel('Current (A)')
        plt.title(f'Initial Id-Vg Scan at Vd = {Vdscan} V')
        plt.legend()
        plt.grid(True)
        plt.show(block=False)
        plt.pause(1)

        if mode == 'save':
            test_name = 'IdVg_initial_scan'
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            if descriptor is not None:
                timestamp += f"_{descriptor}"
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, f"{test_name}_{timestamp}.csv")
            data.to_csv(save_path, index=False)
            plt.savefig(save_path.replace('.csv', '.png'))
            print(f"Data saved to: {save_path}")

        plt.close()

    Vg_data = data['Gate_Voltage'].to_numpy()
    Id_data = np.abs(data['Drain_Current'].to_numpy())
    Ig_data = np.abs(data['Gate_Current'].to_numpy())

    Vg_data_half = get_sweeps(Vg_data)['f']
    Id_data_half = get_sweeps(Id_data)['f']
    Vt_sat = Vt_at_constant_Id(Vg_data_half, Id_data_half, Id_target=100e-9 * W / L)
    print(f"Vt @ Id = 100 nA * W / L: {Vt_sat} V")

    if np.isnan(Vt_sat) or Vt_sat is None:
        print("Failed to extract Vt, device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, Vt_sat
    
    if Vt_sat < -3.5 or Vt_sat > 2.5:
        print("Extracted Vt is out of expected range (-3.5 V to 2.5 V), device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, Vt_sat
    else:
        print("Extracted Vt within acceptable range.")

    if max(Ig_data) > 1e-9:
        print("Gate leakage current exceeds 1 nA, device may be faulty.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, Vt_sat
    else:
        print("Gate leakage current within acceptable limits.")

    if max(Id_data) < 1e-7:
        print("Maximum drain current is below 100 nA, device is not good enough.")
        skip_device_flag = True
        return skip_device_flag, new_gate_start, Vt_sat
    else:
        print("Maximum drain current within acceptable limits.")

    if min(Id_data) < 1e-12 or max(Id_data) > 1e-7 :
        if max(Id_data) / min(Id_data) < 100:
            print("Drain current range is less than two decades, device may be faulty.")
            skip_device_flag = True
            return skip_device_flag, new_gate_start, Vt_sat
        else:
            print("Drain current range within acceptable limits.")

    if min(Id_data) <= 2.5e-12:
        Voff = Vt_at_constant_Id(Vg_data_half, Id_data_half, Id_target=2.5e-12)
        print(f"Voff = {Voff} V defined at Id = 2.5 pA")
        new_gate_start = floor((Voff - 0.5)/gate_step) * gate_step

    if min(Id_data) > 2.5e-12:
        new_gate_start = start_limit

    return skip_device_flag, new_gate_start, Vt_sat

def measure_main_IdVg(myb1500=None, smu_gate=None, smu_drain=None, smu_source=None, gate_start=None, configs={}, descriptor=None, save_dir=None, mode=None, cycle_colors=['blue', 'red', 'green', 'black', 'orange']):
    print("\n################################################")
    print("Starting main Id-Vg measurement sequence...")

    gate_stop = configs.get('default_stop', 1.0)
    gate_step = configs.get('main_step', 0.05)
    Vdlin = configs.get('Vdlin', 0.05)
    Vdsat = configs.get('Vdsat', 1.5)
    num_cycles = configs.get('IdVg_cycles', 2)
    Irange = configs.get('Irange', '1 nA limited auto ranging')
    Vrange = configs.get('Vrange', '2 V limited auto ranging')

    if mode == 'debug':
        print("Debug mode: Skipping main Id-Vg measurement sequence.")
        return

    if myb1500 is None or smu_gate is None or smu_drain is None or smu_source is None:
        raise Exception("B1500 and SMUs must be initialized before calling measure_main_IdVg in non-debug mode.")

    # Main Id-Vg measurement at multiple drain voltages
    data = IdVg_multi_Vd_multi_cycle(
        b1500=myb1500,
        smu_gate=smu_gate,
        smu_drain=smu_drain,
        smu_source=smu_source,
        gate_start=gate_start,
        gate_stop=gate_stop,
        gate_step=gate_step,
        drain_list=[Vdlin, Vdsat],
        num_cycles=num_cycles,
        Irange=Irange,
        Vrange=Vrange
    )

    # Plot Id-Vg curves for different drain voltages
    plt.figure(figsize=(8, 6))
    for cycle in data['Cycle'].unique():
        cycle_data = data[data['Cycle'] == cycle]
        for Vd in cycle_data['Drain_Voltage'].unique():
            Vd_data = cycle_data[cycle_data['Drain_Voltage'] == Vd]
            plt.semilogy(Vd_data['Gate_Voltage'].to_numpy(), np.abs(Vd_data['Drain_Current'].to_numpy()), label=f'Drain Current' if Vd == Vdlin else f'_Drain Current', color=cycle_colors[(cycle-1) % len(cycle_colors)], linestyle='-' if Vd == Vdlin else '--')
            plt.semilogy(Vd_data['Gate_Voltage'].to_numpy(), np.abs(Vd_data['Gate_Current'].to_numpy()), label=f'Gate Current' if Vd == Vdlin else f'_Gate Current', color=cycle_colors[(cycle-1) % len(cycle_colors)], linestyle='-' if Vd == Vdlin else '--')
            plt.semilogy(Vd_data['Gate_Voltage'].to_numpy(), np.abs(Vd_data['Source_Current'].to_numpy()), label=f'Source Current' if Vd == Vdlin else f'_Source Current', color=cycle_colors[(cycle-1) % len(cycle_colors)], linestyle='-' if Vd == Vdlin else '--')
    plt.xlabel('Gate Voltage (V)')
    plt.ylabel('Drain Current (A)')
    plt.title('Id-Vg Curves for Different Drain Voltages')
    # plt.legend()
    plt.grid(True)
    plt.show(block=False)
    plt.pause(1)

    if mode == 'save':
        test_name = 'IdVg_main'
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if descriptor is not None:
            timestamp += f"_{descriptor}"
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f"{test_name}_{timestamp}.csv")
        data.to_csv(save_path, index=False)
        plt.savefig(save_path.replace('.csv', '.png'))
        print(f"Data saved to : {save_path}")

    plt.close()

    print("Main IdVg measurement sequence completed.")
    print("################################################\n")

def measure_all_v2(myb1500=None, smu_gate=None, smu_drain=None, smu_source=None, save_dir=None, mode=None, _meas={}, descriptor=None, W=None, L=None, cycle_colors=['blue', 'red', 'green', 'black', 'orange']):
    save_dir = save_dir
    gate_stop = _meas.get('gate_stop', None)
    mode = mode
    skip_device_flag, gate_start, Vt_sat = measure_initial_scan_v2(myb1500=myb1500, smu_gate=smu_gate, smu_drain=smu_drain, smu_source=smu_source, configs=_meas, descriptor=descriptor, save_dir=save_dir, mode=mode, W=W, L=L)
    if skip_device_flag:
        print("SKIPPING DEVICE BASED ON INITIAL SCAN EVALUATION.....\n")
    else:
        print("DEVICE PASSED INITIAL SCAN EVALUATION.")
        print(f"Proceeding with main measurement sequence with gate voltage range {gate_start} V to {gate_stop} V and Vt_sat = {Vt_sat} V\n")
        measure_main_IdVg(myb1500=myb1500, smu_gate=smu_gate, smu_drain=smu_drain, smu_source=smu_source, gate_start=gate_start, configs=_meas, descriptor=descriptor, save_dir=save_dir, mode=mode, cycle_colors=cycle_colors)

def measure_cvf(lcr_meter=None, save_dir=None, _meas=None, _sample=None, _dev_grp=None, mode=None, descriptor=None, cv_func = 'CSRS'):
    cvf_settings = settings.copy()
    cvf_settings['sample_name'] = _sample.get('sample_name', 'main_wf2')
    cvf_settings['device_group'] = _dev_grp.get('dev_group_name', 'AC_R')
    cvf_settings['start_volt'] = _meas.get('default_start', -1.0)
    cvf_settings['stop_volt'] = _meas.get('default_stop', 3.0)
    cvf_settings['step_volt'] = _meas.get('scan_step', 0.05)
    cvf_settings['start_freq'] = _meas.get('start_freq', 5e3)
    cvf_settings['stop_freq'] = _meas.get('stop_freq', 1e6)
    cvf_settings['num_freq_decade'] = _meas.get('num_freq_decade', 4)
    cvf_settings['measurement_function'] = cv_func

    cvf_measurement = CVMeasurement(cvf_settings, lcr_meter=lcr_meter)
    df = cvf_measurement.perform_cvf_sweep()

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    save_csv_path = os.path.join(save_dir, f"CV_{timestamp}_{descriptor}.csv")
    save_settings_path = os.path.join(save_dir, f"CV_{timestamp}_{descriptor}.yaml")
    save_plot_path = os.path.join(save_dir, f"CV_{timestamp}_{descriptor}.png")

    if mode == 'save':
        df.to_csv(save_csv_path, index=False)
        print(f"Data saved to {save_csv_path}")

        cvf_settings.update({'timestamp': timestamp})
        with open(save_settings_path, 'w') as f:
            yaml.dump(cvf_settings, f)
        print(f"Settings saved to {save_settings_path}")

    # Plotting
    fig = plt.figure()
    volt_col = 'voltage'
    freq_col = 'frequency'
    freq_unique = df[freq_col].unique()
    dir_unique = df['direction'].unique() if 'direction' in df.columns else ['fwd']
    for direction in dir_unique:
        for freq in freq_unique:
            mask = (df[volt_col].notna()) & (df[freq_col] == freq) & ((df['direction'] == direction) if 'direction' in df.columns else True)
            marker = 'o' if direction == 'fwd' else 's'
            color = plt.cm.viridis((np.log10(freq) - np.log10(cvf_settings['start_freq'])) / (np.log10(cvf_settings['stop_freq']) - np.log10(cvf_settings['start_freq'])))
            plt.plot(df[mask][volt_col], df[mask]['capacitance'], marker=marker, color=color, label=f'{direction} - {freq/1e3:.1f} kHz')
    # plt.legend()
    plt.xlabel('Voltage (V)')
    plt.ylabel('Capacitance (F)')
    plt.title(f'C-V-F Sweep: {cvf_settings["device_group"]}')
    plt.grid(True)
    plt.tight_layout()
    plt.show(block=False)
    plt.pause(5)

    if mode == 'save':
        plt.savefig(save_plot_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to {save_plot_path}")

    plt.close(fig)

def measure_all_cvf(lcr_meter=None, save_dir=None, _meas=None, _sample=None, _dev_grp=None, mode=None, descriptor=None):
    measure_cvf(lcr_meter=lcr_meter, save_dir=save_dir, _meas=_meas, _sample=_sample, _dev_grp=_dev_grp, mode=mode, descriptor=descriptor, cv_func = 'CPG')
    measure_cvf(lcr_meter=lcr_meter, save_dir=save_dir, _meas=_meas, _sample=_sample, _dev_grp=_dev_grp, mode=mode, descriptor=descriptor, cv_func = 'CSRS')

def measure_dev_grp(_misc={}, _meas={}, _sample={}, _dev_grp={}, myb1500=None, smu_gate=None, smu_drain=None, smu_source=None, prober=None):
    mode = _misc.get('mode', 'debug')
    data_parent_dir = _misc.get('data_parent_dir', os.getcwd())
    repeat_measurement = _misc.get('repeat_measurement', False)
    remarks = _misc.get('remarks', 'init_0')

    sample_name = _sample.get('sample_name', 'main_wf2')
    die_id = _sample.get('die_id', '-3_0')
    
    dev_group_name = _dev_grp.get('dev_group_name', 'AC_R')
    W_um = _dev_grp.get('W_um', 10)
    L_um = _dev_grp.get('L_um', 4)
    start_dev_y_idx = _dev_grp.get('start_dev_y_idx', 0)
    dev_y_idx_list = _dev_grp.get('dev_y_idx_list', [0])
    dev_y_pitch = _dev_grp.get('dev_y_pitch', 290.0)

    current_x_displace_from_origin = 0
    current_y_displace_from_origin = 0

    save_dir = os.path.join(data_parent_dir, sample_name, die_id, dev_group_name, remarks)
    os.makedirs(save_dir, exist_ok=True)

    print("=================================================")
    print(f"Starting measurement sequence for device group: {dev_group_name} on sample: {sample_name}, die: {die_id}")
    print("=================================================")

    print(f"Device group parameters: W = {W_um} um, L = {L_um} um, start_dev_y_idx = {start_dev_y_idx}, dev_y_idx_list = {dev_y_idx_list}, dev_y_pitch = {dev_y_pitch} um")

    for dev_y_idx in dev_y_idx_list:
        print()
        print("=================================================")
        descriptor = f"{remarks}_{die_id}_{dev_group_name}_{dev_y_idx}"
        measured_previously = False

        
        for root, dirs, files in os.walk(save_dir):
            if 'IGNORE' in root:
                continue
            for file in files:
                if file.endswith(".csv"):
                    if f"{descriptor}.csv" in file:
                        measured_previously = True
                        break

        if measured_previously and not repeat_measurement:
            print(f"Device with descriptor {descriptor} has been measured previously. Skipping measurement as repeat_measurement is set to False.")
            continue

        print(f"Measuring device with descriptor: {descriptor}")

        reqd_x_displace_from_origin = 0
        reqd_y_displace_from_origin = (dev_y_idx - start_dev_y_idx) * dev_y_pitch

        move_separation_height(prober=prober)
                    
        move_relative(prober=prober, x_microns=reqd_x_displace_from_origin - current_x_displace_from_origin, y_microns=reqd_y_displace_from_origin - current_y_displace_from_origin)

        current_x_displace_from_origin = reqd_x_displace_from_origin
        current_y_displace_from_origin = reqd_y_displace_from_origin
        print(f"Current position: x = {current_x_displace_from_origin}, y = {current_y_displace_from_origin}")

        W = W_um * 1e-6
        L = L_um * 1e-6

        print("Starting measurement...")

        move_contact_height(prober=prober)
        
        measure_all_v2(myb1500=myb1500, smu_gate=smu_gate, smu_drain=smu_drain, smu_source=smu_source, save_dir=save_dir, mode=mode, _meas=_meas, descriptor=descriptor, W=W, L=L, cycle_colors=['blue', 'red', 'green', 'black', 'orange'])

        print("Finished measurement.")

        move_separation_height(prober=prober)

        print("=================================================")

def measure_dev_grp_cvf(_misc={}, _meas={}, _sample={}, _dev_grp={}, lcr_meter=None, prober=None):
    mode = _misc.get('mode', 'debug')
    data_parent_dir = _misc.get('data_parent_dir', os.getcwd())
    repeat_measurement = _misc.get('repeat_measurement', False)
    remarks = _misc.get('remarks', 'cvf_1')

    sample_name = _sample.get('sample_name', 'main_wf2')
    die_id = _sample.get('die_id', '-3_0')
    
    dev_group_name = _dev_grp.get('dev_group_name', 'AC_R')
    W_um = _dev_grp.get('W_um', 10)
    L_um = _dev_grp.get('L_um', 4)
    start_dev_y_idx = _dev_grp.get('start_dev_y_idx', 0)
    dev_y_idx_list = _dev_grp.get('dev_y_idx_list', [0])
    dev_y_pitch = _dev_grp.get('dev_y_pitch', 290.0)

    current_x_displace_from_origin = 0
    current_y_displace_from_origin = 0

    save_dir = os.path.join(data_parent_dir, sample_name, die_id, dev_group_name, remarks)
    os.makedirs(save_dir, exist_ok=True)

    print("=================================================")
    print(f"Starting measurement sequence for device group: {dev_group_name} on sample: {sample_name}, die: {die_id}")
    print("=================================================")

    print(f"Device group parameters: W = {W_um} um, L = {L_um} um, start_dev_y_idx = {start_dev_y_idx}, dev_y_idx_list = {dev_y_idx_list}, dev_y_pitch = {dev_y_pitch} um")

    for dev_y_idx in dev_y_idx_list:
        print()
        print("=================================================")
        descriptor = f"{remarks}_{die_id}_{dev_group_name}_{dev_y_idx}"
        measured_previously = False

        
        for root, dirs, files in os.walk(save_dir):
            if 'IGNORE' in root:
                continue
            for file in files:
                if file.endswith(".csv"):
                    if f"{descriptor}.csv" in file:
                        measured_previously = True
                        break

        if measured_previously and not repeat_measurement:
            print(f"Device with descriptor {descriptor} has been measured previously. Skipping measurement as repeat_measurement is set to False.")
            continue

        print(f"Measuring device with descriptor: {descriptor}")

        reqd_x_displace_from_origin = 0
        reqd_y_displace_from_origin = (dev_y_idx - start_dev_y_idx) * dev_y_pitch

        move_separation_height(prober=prober)
                    
        move_relative(prober=prober, x_microns=reqd_x_displace_from_origin - current_x_displace_from_origin, y_microns=reqd_y_displace_from_origin - current_y_displace_from_origin)

        current_x_displace_from_origin = reqd_x_displace_from_origin
        current_y_displace_from_origin = reqd_y_displace_from_origin
        print(f"Current position: x = {current_x_displace_from_origin}, y = {current_y_displace_from_origin}")

        W = W_um * 1e-6
        L = L_um * 1e-6

        print("Starting measurement...")

        move_contact_height(prober=prober)
        
        measure_all_cvf(lcr_meter=lcr_meter, save_dir=save_dir, _meas=_meas, _sample=_sample, _dev_grp=_dev_grp, mode=mode, descriptor=descriptor)

        print("Finished measurement.")

        move_separation_height(prober=prober)

        print("=================================================")

       



