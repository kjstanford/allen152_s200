import pandas as pd
import numpy as np

def IdVg_single_Vd(b1500=None, smu_gate=None, smu_drain=None, smu_source=None, gate_start=0, gate_stop=1, gate_step=0.05, drain_voltage=0.05, Irange='1 nA limited auto ranging', Vrange='2 V limited auto ranging'):
    """
    Perform a single Id-Vg transfer measurement at a fixed drain voltage.

    Parameters:
    - b1500: AgilentB1500 instance
    - smu_gate: SMU instance for gate
    - smu_drain: SMU instance for drain
    - smu_source: SMU instance for source
    - gate_start: Starting gate voltage
    - gate_stop: Ending gate voltage
    - gate_step: Step size for gate voltage
    - drain_voltage: Fixed drain voltage
    - Irange: Current measurement range for SMUs
    - Vrange: Voltage measurement range for SMUs

    Returns:
    - data: Pandas DataFrame containing the measurement results
    """

    compliance = 0.1
    hold = 0
    delay = 0
    step_delay = 0

    if b1500 is None or smu_gate is None or smu_drain is None or smu_source is None:
        raise ValueError("b1500 and SMU instances must be provided")

    num_points = int((gate_stop - gate_start) / gate_step) + 1

    b1500.data_format(21, mode=1)
    b1500.meas_mode('STAIRCASE_SWEEP', smu_gate, smu_drain, smu_source)
    for smu in [smu_gate, smu_drain, smu_source]:
        smu.enable()
        smu.adc_type = 'HRADC'
        smu.meas_range_current = Irange
        smu.meas_op_mode = 'COMPLIANCE_SIDE'

    b1500.adc_setup('HRADC', 'AUTO', 6)
    b1500.sweep_timing(hold=hold, delay=delay, step_delay=step_delay)
    b1500.sweep_auto_abort(False, post='STOP')

    smu_gate.staircase_sweep_source('VOLTAGE', 'LINEAR_DOUBLE', Vrange, gate_start, gate_stop, num_points, comp=compliance)
    smu_drain.force('VOLTAGE', Vrange, drain_voltage, comp=compliance)
    smu_source.force('VOLTAGE', Vrange, 0, comp=compliance)

    b1500.check_errors()
    b1500.clear_buffer()
    b1500.clear_timer()
    b1500.send_trigger()
    b1500.check_idle()

    if not b1500.check_errors():
        print("Measurement successful :D")
    else:
        print("Measurement completed with errors :(")

    raw_data_str = b1500.read()
    data_list = []

    for item in raw_data_str.strip().split(','):
        if len(item) < 5: 
            continue
        item_dict = {}
        item_dict['Value'] = float(item[-13:])
        item_dict['Channel'] = item[-15]
        item_dict['Type'] = 'Current' if item[-14] == 'I' else 'Voltage'
        data_list.append(item_dict)
    df = pd.DataFrame(data_list)

    unique_params = df[['Channel', 'Type']].drop_duplicates()
    items_per_step = len(unique_params)
    print(f"Detected {items_per_step} items per measurement step.")

    def terminal(idx):
        idx = ord(idx) - 66
        if f"SMU{idx}" == smu_gate.name:
            return 'Gate'
        elif f"SMU{idx}" == smu_drain.name:
            return 'Drain'
        elif f"SMU{idx}" == smu_source.name:
            return 'Source'
        else:
            raise ValueError("Invalid SMU instance")

    df['Group_ID'] = df.index // items_per_step
    df['New_Column'] = df['Channel'] + '_' + df['Type']
    df_pivoted = df.pivot(index='Group_ID', columns='New_Column', values='Value')
    df_pivoted.columns.name = None
    df_pivoted = df_pivoted.reset_index(drop=True)
    data = df_pivoted

    data.columns = [f"{terminal(col[0])}{col[1:]}" for col in data.columns]

    return data

def IdVg_multi_Vd(b1500, smu_gate, smu_drain, smu_source, gate_start, gate_stop, gate_step, drain_list, Irange='1 nA limited auto ranging', Vrange='2 V limited auto ranging'):
    """
    Perform an Id-Vg transfer measurement over multiple drain voltages.

    Parameters:
    - b1500: AgilentB1500 instance
    - smu_gate: SMU instance for gate
    - smu_drain: SMU instance for drain
    - smu_source: SMU instance for source
    - gate_start: Starting gate voltage
    - gate_stop: Ending gate voltage
    - gate_step: Step size for gate voltage
    - drain_list: List of drain voltages
    - Irange: Current measurement range for SMUs
    - Vrange: Voltage measurement range for SMUs

    Returns:
    - data: Pandas DataFrame containing the measurement results
    """

    all_data = pd.DataFrame()

    drain_voltages = np.array(drain_list)

    for Vd in drain_voltages:
        print(f"Measuring at Drain Voltage: {Vd} V")
        data = IdVg_single_Vd(
            b1500,
            smu_gate,
            smu_drain,
            smu_source,
            gate_start,
            gate_stop,
            gate_step,
            Vd,
            Irange,
            Vrange
        )
        data['Drain_Voltage'] = Vd
        all_data = pd.concat([all_data, data], ignore_index=True)

    return all_data

def IdVg_multi_Vd_multi_cycle(b1500, smu_gate, smu_drain, smu_source, gate_start, gate_stop, gate_step, drain_list, num_cycles=1, Irange='1 nA limited auto ranging', Vrange='2 V limited auto ranging'):
    """
    Perform multiple cycles of Id-Vg transfer measurements over multiple drain voltages.

    Parameters:
    - b1500: AgilentB1500 instance
    - smu_gate: SMU instance for gate
    - smu_drain: SMU instance for drain
    - smu_source: SMU instance for source
    - gate_start: Starting gate voltage
    - gate_stop: Ending gate voltage
    - gate_step: Step size for gate voltage
    - drain_list: List of drain voltages
    - num_cycles: Number of measurement cycles
    - Irange: Current measurement range for SMUs
    - Vrange: Voltage measurement range for SMUs

    Returns:
    - data: Pandas DataFrame containing the measurement results
    """

    all_data = pd.DataFrame()

    for cycle in range(num_cycles):
        print(f"Starting measurement cycle {cycle + 1} of {num_cycles}")
        cycle_data = IdVg_multi_Vd(
            b1500,
            smu_gate,
            smu_drain,
            smu_source,
            gate_start,
            gate_stop,
            gate_step,
            drain_list,
            Irange,
            Vrange
        )
        cycle_data['Cycle'] = cycle + 1
        all_data = pd.concat([all_data, cycle_data], ignore_index=True)

    return all_data

def IdVd_single_Vg(b1500, smu_gate, smu_drain, smu_source, drain_start, drain_stop, drain_step, gate_voltage, Irange='1 nA limited auto ranging', Vrange='2 V limited auto ranging'):
    """
    Perform a single Id-Vd output measurement at a fixed gate voltage.

    Parameters:
    - b1500: AgilentB1500 instance
    - smu_gate: SMU instance for gate
    - smu_drain: SMU instance for drain
    - smu_source: SMU instance for source
    - drain_start: Starting drain voltage
    - drain_stop: Ending drain voltage
    - drain_step: Step size for drain voltage
    - gate_voltage: Fixed gate voltage
    - Irange: Current measurement range for SMUs
    - Vrange: Voltage measurement range for SMUs

    Returns:
    - data: Pandas DataFrame containing the measurement results
    """

    compliance = 0.1
    hold = 0
    delay = 0
    step_delay = 0

    if b1500 is None or smu_gate is None or smu_drain is None or smu_source is None:
        raise ValueError("b1500 and SMU instances must be provided")

    num_points = int((drain_stop - drain_start) / drain_step) + 1

    b1500.data_format(21, mode=1)
    b1500.meas_mode('STAIRCASE_SWEEP', smu_drain, smu_gate, smu_source)
    for smu in [smu_gate, smu_drain, smu_source]:
        smu.enable()
        smu.adc_type = 'HRADC'
        smu.meas_range_current = Irange
        smu.meas_op_mode = 'COMPLIANCE_SIDE'

    b1500.adc_setup('HRADC', 'AUTO', 6)
    b1500.sweep_timing(hold=hold, delay=delay, step_delay=step_delay)
    b1500.sweep_auto_abort(False, post='STOP')

    smu_drain.staircase_sweep_source('VOLTAGE', 'LINEAR_DOUBLE', Vrange, drain_start, drain_stop, num_points, comp=compliance)
    smu_gate.force('VOLTAGE', Vrange, gate_voltage, comp=compliance)
    smu_source.force('VOLTAGE', Vrange, 0, comp=compliance)

    b1500.check_errors()
    b1500.clear_buffer()
    b1500.clear_timer()
    b1500.send_trigger()
    b1500.check_idle()

    if not b1500.check_errors():
        print("Measurement successful :D")
    else:
        print("Measurement completed with errors :(")

    raw_data_str = b1500.read()
    data_list = []

    for item in raw_data_str.strip().split(','):
        if len(item) < 5: 
            continue
        item_dict = {}
        item_dict['Value'] = float(item[-13:])
        item_dict['Channel'] = item[-15]
        item_dict['Type'] = 'Current' if item[-14] == 'I' else 'Voltage'
        data_list.append(item_dict)
    df = pd.DataFrame(data_list)

    unique_params = df[['Channel', 'Type']].drop_duplicates()
    items_per_step = len(unique_params)
    print(f"Detected {items_per_step} items per measurement step.")

    def terminal(idx):
        idx = ord(idx) - 66
        if f"SMU{idx}" == smu_gate.name:
            return 'Gate'
        elif f"SMU{idx}" == smu_drain.name:
            return 'Drain'
        elif f"SMU{idx}" == smu_source.name:
            return 'Source'
        else:
            raise ValueError("Invalid SMU instance")

    df['Group_ID'] = df.index // items_per_step
    df['New_Column'] = df['Channel'] + '_' + df['Type']
    df_pivoted = df.pivot(index='Group_ID', columns='New_Column', values='Value')
    df_pivoted.columns.name = None
    df_pivoted = df_pivoted.reset_index(drop=True)
    data = df_pivoted

    data.columns = [f"{terminal(col[0])}{col[1:]}" for col in data.columns]

    return data

def IdVd_multi_Vg(b1500, smu_gate, smu_drain, smu_source, drain_start, drain_stop, drain_step, gate_list, Irange='1 nA limited auto ranging', Vrange='2 V limited auto ranging'):
    """
    Perform an Id-Vd output measurement over multiple gate voltages.

    Parameters:
    - b1500: AgilentB1500 instance
    - smu_gate: SMU instance for gate
    - smu_drain: SMU instance for drain
    - smu_source: SMU instance for source
    - drain_start: Starting drain voltage
    - drain_stop: Ending drain voltage
    - drain_step: Step size for drain voltage
    - gate_list: List of gate voltages
    - Irange: Current measurement range for SMUs
    - Vrange: Voltage measurement range for SMUs

    Returns:
    - data: Pandas DataFrame containing the measurement results
    """

    all_data = pd.DataFrame()

    gate_voltages = np.array(gate_list)

    for Vg in gate_voltages:
        print(f"Measuring at Gate Voltage: {Vg} V")
        data = IdVd_single_Vg(
            b1500,
            smu_gate,
            smu_drain,
            smu_source,
            drain_start,
            drain_stop,
            drain_step,
            Vg,
            Irange,
            Vrange
        )
        data['Gate_Voltage'] = Vg
        all_data = pd.concat([all_data, data], ignore_index=True)

    return all_data

def IdVd_multi_Vg_multi_cycle(b1500, smu_gate, smu_drain, smu_source, drain_start, drain_stop, drain_step, gate_list, num_cycles=1, Irange='1 nA limited auto ranging', Vrange='2 V limited auto ranging'):
    """
    Perform multiple cycles of Id-Vd output measurements over multiple gate voltages.

    Parameters:
    - b1500: AgilentB1500 instance
    - smu_gate: SMU instance for gate
    - smu_drain: SMU instance for drain
    - smu_source: SMU instance for source
    - drain_start: Starting drain voltage
    - drain_stop: Ending drain voltage
    - drain_step: Step size for drain voltage
    - gate_list: List of gate voltages
    - num_cycles: Number of measurement cycles
    - Irange: Current measurement range for SMUs
    - Vrange: Voltage measurement range for SMUs

    Returns:
    - data: Pandas DataFrame containing the measurement results
    """

    all_data = pd.DataFrame()

    for cycle in range(num_cycles):
        print(f"Starting measurement cycle {cycle + 1} of {num_cycles}")
        cycle_data = IdVd_multi_Vg(
            b1500,
            smu_gate,
            smu_drain,
            smu_source,
            drain_start,
            drain_stop,
            drain_step,
            gate_list,
            Irange,
            Vrange
        )
        cycle_data['Cycle'] = cycle + 1
        all_data = pd.concat([all_data, cycle_data], ignore_index=True)

    return all_data

def FET_sampling(b1500=None, smu_gate=None, smu_drain=None, smu_source=None, gate_voltage=0.0, drain_voltage=0.0, source_voltage=0.0, hold_time=0.0, base_voltage=0.0, sampling_interval=1.0, nop=11, Irange='1 nA limited auto ranging', Vrange='2 V limited auto ranging'):
    """
    Sampling of Id, Ig, and Is at specified gate, drain, and source voltages.

    Parameters:
    - b1500: AgilentB1500 instance
    - smu_gate: SMU instance for gate
    - smu_drain: SMU instance for drain
    - smu_source: SMU instance for source
    - gate_voltage: Voltage to apply to the gate
    - drain_voltage: Voltage to apply to the drain
    - source_voltage: Voltage to apply to the source
    - hold_time: Hold time in seconds
    - base_voltage: Base voltage
    - sampling_interval: Interval between samples in seconds
    - nop: Number of points to sample
    - Irange: Current measurement range for SMUs
    - Vrange: Voltage measurement range for SMUs

    Returns:
    - data: Pandas DataFrame containing the sampled values
    """

    compliance = 0.1

    if b1500 is None or smu_gate is None or smu_drain is None or smu_source is None:
        raise ValueError("b1500 and SMU instances must be provided")
    
    b1500.data_format(21, mode=1)
    b1500.meas_mode('SAMPLING', smu_gate, smu_drain, smu_source)

    for smu in [smu_gate, smu_drain, smu_source]:
        smu.enable()
        # smu.adc_type = 'HRADC'
        smu.adc_type = 'HSADC'
        smu.meas_range_current = Irange
        smu.meas_op_mode = 'COMPLIANCE_SIDE'

    b1500.sampling_mode = 'LINEAR'
    # b1500.adc_setup('HRADC', 'AUTO', 6)
    b1500.adc_setup('HSADC', 'AUTO', 1)

    b1500.sampling_timing(hold_time, sampling_interval, nop)
    b1500.sampling_auto_abort(False, post='BIAS')
    b1500.time_stamp = True

    smu_gate.sampling_source('VOLTAGE', Vrange, base_voltage, gate_voltage, compliance)
    smu_drain.sampling_source('VOLTAGE', Vrange, base_voltage, drain_voltage, compliance)
    smu_source.sampling_source('VOLTAGE', Vrange, base_voltage, source_voltage, compliance)

    b1500.check_errors()
    b1500.clear_buffer()
    b1500.clear_timer()
    b1500.send_trigger()
    b1500.check_idle()

    if not b1500.check_errors():
        print("Measurement successful :D")
    else:
        print("Measurement completed with errors :(")

    raw_data_str = b1500.read()

    data_list = []
    type_dict = {'I': 'Current', 'V': 'Voltage', 'T': 'Time', 'X': 'Index'}
    for item in raw_data_str.strip().split(','):
        # print(f"Processing item: '{item}'")
        if len(item) < 5: 
            continue
        item_dict = {}
        item_dict['Value'] = float(item[-13:])
        item_dict['Channel'] = item[-15]
        item_dict['Type'] = type_dict.get(item[-14], '')
        data_list.append(item_dict)
    
    df = pd.DataFrame(data_list)

    unique_params = df[['Channel', 'Type']].drop_duplicates()
    items_per_step = len(unique_params)
    print(f"Detected {items_per_step} items per measurement step.")

    def terminal(idx):
        if idx == 'Z':
            return 'Common'
        idx = ord(idx) - 66
        if f"SMU{idx}" == smu_gate.name:
            return 'Gate'
        elif f"SMU{idx}" == smu_drain.name:
            return 'Drain'
        elif f"SMU{idx}" == smu_source.name:
            return 'Source'
        else:
            return ''
        
    df['Group_ID'] = df.index // items_per_step
    df['New_Column'] = df['Channel'] + '_' + df['Type']
    df_pivoted = df.pivot(index='Group_ID', columns='New_Column', values='Value')
    df_pivoted.columns.name = None
    df_pivoted = df_pivoted.reset_index(drop=True)
    data = df_pivoted

    data.columns = [f"{terminal(col[0])}{col[1:]}" for col in data.columns]

    return data

def FET_sampling_live(b1500=None, smu_gate=None, smu_drain=None, smu_source=None, gate_voltage=0.0, drain_voltage=0.0, source_voltage=0.0, hold_time=0.0, base_voltage=0.0, sampling_interval=1.0, nop=11, Irange='1 nA limited auto ranging', Vrange='2 V limited auto ranging'):
    """
    Sampling of Id, Ig, and Is at specified gate, drain, and source voltages.

    Parameters:
    - b1500: AgilentB1500 instance
    - smu_gate: SMU instance for gate
    - smu_drain: SMU instance for drain
    - smu_source: SMU instance for source
    - gate_voltage: Voltage to apply to the gate
    - drain_voltage: Voltage to apply to the drain
    - source_voltage: Voltage to apply to the source
    - hold_time: Hold time in seconds
    - base_voltage: Base voltage
    - sampling_interval: Interval between samples in seconds
    - nop: Number of points to sample
    - Irange: Current measurement range for SMUs
    - Vrange: Voltage measurement range for SMUs

    Returns:
    - data: Pandas DataFrame containing the sampled values
    """

    compliance = 0.1

    if b1500 is None or smu_gate is None or smu_drain is None or smu_source is None:
        raise ValueError("b1500 and SMU instances must be provided")
    
    b1500.data_format(21, mode=1)
    b1500.meas_mode('SAMPLING', smu_gate, smu_drain, smu_source)

    for smu in [smu_gate, smu_drain, smu_source]:
        smu.enable()
        # smu.adc_type = 'HRADC'
        smu.adc_type = 'HSADC'
        smu.meas_range_current = Irange
        smu.meas_op_mode = 'COMPLIANCE_SIDE'

    b1500.sampling_mode = 'LINEAR'
    # b1500.adc_setup('HRADC', 'AUTO', 6)
    b1500.adc_setup('HSADC', 'AUTO', 1)

    b1500.sampling_timing(hold_time, sampling_interval, nop)
    b1500.sampling_auto_abort(False, post='BIAS')
    b1500.time_stamp = True

    smu_gate.sampling_source('VOLTAGE', Vrange, base_voltage, gate_voltage, compliance)
    smu_drain.sampling_source('VOLTAGE', Vrange, base_voltage, drain_voltage, compliance)
    smu_source.sampling_source('VOLTAGE', Vrange, base_voltage, source_voltage, compliance)

    b1500.check_errors()
    b1500.clear_buffer()
    b1500.clear_timer()
    b1500.send_trigger()

    df_dict = {}
    channel_dict = {smu_gate.name: 'Gate', smu_drain.name: 'Drain', smu_source.name: 'Source', 'MISC': 'Common'}
    for ii in range(nop):
        read_data = b1500.read_channels(1 + 2 * 3)
        for item in read_data:
            df_dict_key = f"{channel_dict.get(item[1], item[1])} {item[2]}"
            df_dict.setdefault(df_dict_key, []).append(item[3])
    
    data = pd.DataFrame(df_dict)

    return data

    

    


    
