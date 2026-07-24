"""
Helper methods for communicating and running the Keithley 4200 with GPIB
"""
import pyvisa
import numpy as np
import time
import pandas as pd
import matplotlib.pyplot as plt
import math

#%% Helper methods

def connect_4200(resource_string="GPIB0::18::INSTR", timeout=20000):
    rm = pyvisa.ResourceManager()
    try:
        my4200 = rm.open_resource(resource_string)
        my4200.timeout = timeout
        print(f"Connected to: {my4200.query('*IDN?')}")
        return my4200
    except pyvisa.VisaIOError as e:
        print(f"Communication Error: {e}")
        return None

def disconnect_4200(my4200=None):
    if my4200 is None:
        print("Keithley resource not provided. Cannot disconnect.")
        return 1
    try:
        my4200.close()
        print("Disconnected from Keithley 4200.")
    except pyvisa.VisaIOError as e:
        print(f"Communication Error: {e}")
    return 0

import numpy as np

def get_data(my4200, chan, invalid_sentinels=None, return_nan_on_error=True):
    """
    Robust DO parser:
    - Handles optional leading status character (e.g., 'N+1.23E-6')
    - Marks known invalid sentinel readings as NaN
    """
    if invalid_sentinels is None:
        # Add/adjust if you know the exact sentinel(s) your setup returns
        invalid_sentinels = {"-999.99E-03", "-9.9999E+37"}

    print(my4200.query("IDN?"))  # consider matching your known-good sample
    print(f"Reading {chan}...")
    data = my4200.query(f"DO '{chan}'")

    out = []
    for tok in data.split(","):
        s = tok.strip()
        if not s:
            continue

        # If token begins with a non-numeric status character, drop it (sample behavior)
        if s[0] not in "+-0123456789.":
            s_num = s[1:].strip()
        else:
            s_num = s

        # Handle known invalid sentinels
        if s_num in invalid_sentinels:
            out.append(np.nan)
            continue

        try:
            out.append(float(s_num))
        except ValueError:
            # Unknown junk: either NaN or raise
            if return_nan_on_error:
                print(f"Could not parse reading '{s}' -> NaN")
                out.append(np.nan)
            else:
                raise ValueError(f"Could not parse reading '{s}' from DO '{chan}'")

    return out

def wait_for_stb(my4200, delay=1, timeout_s=60):
    time.sleep(delay)
    t0 = time.time()
    while True:
        status = my4200.read_stb()
        print(f"Status byte: {status}")
        if status == 0 or status == 1:
            print("Data ready")
            return
        if time.time() - t0 > timeout_s:
            raise TimeoutError("Timed out waiting for status byte")
        time.sleep(1)

def check_for_rpms(my4200):
    settings = my4200.query("*OPT?")
    return settings.find("RPM") > -1

def switch_rpm_mode(my4200, card, chan, mode):
    """Mode: 0 = Pulse, 1 = CV 2-wire, 2 = SMU, 3 = CV 4-wire"""
    my4200.write("SS")
    cmd = f"RP PMU{card}-{chan}, {mode}"
    my4200.write(cmd)

def map_rpm_to_smu(smu):
    """Maps SMUs to RPMs based on the system"""
    if smu % 2 == 0:
        return math.ceil(smu/2), 2
    else:
        return math.ceil(smu/2), 1

def zero_all_outputs(my4200, gatechan, drainchan, sourcechan, gatecomp, draincomp, sourcecomp):
    """SAFETY: Set all outputs to 0V"""
    try:
        my4200.write(f"VC{gatechan}, 0, {gatecomp}")
        my4200.write(f"VC{drainchan}, 0, {draincomp}")  
        my4200.write(f"VC{sourcechan}, 0, {sourcecomp}")
        print(" All outputs safely set to 0V")
    except Exception as e:
        print(f" WARNING: Failed to zero outputs: {e}")

def parse_semicolon_data_to_df(**data_dict):
    """Convert semicolon-separated data strings to DataFrame"""
    parsed_data = {}
    for col_name, data_string in data_dict.items():
        parsed_data[col_name] = np.array([float(x) for x in data_string.split(';') if x.strip()])
    df = pd.DataFrame(parsed_data)
    return df

def list_to_semicolon_str_V(num_list):
    return '; '.join([f"{x:.3f}" for x in num_list])

def list_to_semicolon_str_t(num_list):
    return '; '.join([f"{x:f}" for x in num_list])

def list_to_semicolon_str_int(num_list):
    return '; '.join([f"{x:d}" for x in num_list])

#%% FIXED PMU Function
def pmu_segarb_example_fixed(my4200, VRangeCh1=10, IRangeCh1=10e-6, VRangeCh2=10, IRangeCh2=100e-6, 
                           NumWaveforms=1, DUTResCh1=1e9, DUTResCh2=1e9, MaxSheetPoints=20,
                           SegTime=None, StartVCh1=None, StopVCh1=None, StartVCh2=None, StopVCh2=None,  # FIXED mutable defaults
                           SSRCtrlCh1=None, SSRCtrlCh2=None, SegTrigOut=None,
                           SMU_V=0, SMU_Irange=0.01, SMU_Icomp=0.01, SMU_ID="NONE", PMU_ID="PMU1", 
                           Output_size=10):
    
    # Handle mutable defaults properly
    if SegTime is None: SegTime = []
    if StartVCh1 is None: StartVCh1 = []
    if StopVCh1 is None: StopVCh1 = []
    if StartVCh2 is None: StartVCh2 = []
    if StopVCh2 is None: StopVCh2 = []
    if SSRCtrlCh1 is None: SSRCtrlCh1 = []
    if SSRCtrlCh2 is None: SSRCtrlCh2 = []
    if SegTrigOut is None: SegTrigOut = []
    
    NumSegments = len(SegTime)
    MaxSheetPoints = max(MaxSheetPoints, Output_size, 20)
    
    # Clear buffer and enter user library mode
    my4200.write("BC")
    my4200.write("UL")
    
    # SINGLE, CORRECT command execution with NumSegments in position 9
    cmd = f"EX PMU_examples_ulib PMU_SegArb_Example({VRangeCh1}, {IRangeCh1}, {VRangeCh2}, {IRangeCh2}, {NumWaveforms}, {DUTResCh1}, {DUTResCh2}, {MaxSheetPoints}, {NumSegments}, {list_to_semicolon_str_t(SegTime)}, {len(SegTime)}, {list_to_semicolon_str_V(StartVCh1)}, {len(StartVCh1)}, {list_to_semicolon_str_V(StopVCh1)}, {len(StopVCh1)}, {list_to_semicolon_str_V(StartVCh2)}, {len(StartVCh2)}, {list_to_semicolon_str_V(StopVCh2)}, {len(StopVCh2)}, {list_to_semicolon_str_int(SSRCtrlCh1)}, {len(SSRCtrlCh1)}, {list_to_semicolon_str_int(SSRCtrlCh2)}, {len(SSRCtrlCh2)}, {list_to_semicolon_str_int(SegTrigOut)}, {len(SegTrigOut)}, {SMU_V}, {SMU_Irange}, {SMU_Icomp}, {SMU_ID}, {PMU_ID}, , {MaxSheetPoints}, , {MaxSheetPoints}, , {MaxSheetPoints}, , {MaxSheetPoints}, , {MaxSheetPoints}, , {MaxSheetPoints}, , {MaxSheetPoints})"
    
    print(f"Calling PMU function: {cmd}")
    my4200.write(cmd)
    my4200.write("ME1")
    wait_for_stb(my4200)

    # Get results
    return_data = my4200.query("DO")
    print(f"Return Value: {return_data}")

    VMeasCh1_data = my4200.query(f"GN VMeasCh1 {MaxSheetPoints}")
    IMeasCh1_data = my4200.query(f"GN IMeasCh1 {MaxSheetPoints}")
    VMeasCh2_data = my4200.query(f"GN VMeasCh2 {MaxSheetPoints}")
    IMeasCh2_data = my4200.query(f"GN IMeasCh2 {MaxSheetPoints}")
    TimeOutput_data = my4200.query(f"GN TimeOutput {MaxSheetPoints}")
    StatusCh1_data = my4200.query(f"GN StatusCh1 {MaxSheetPoints}")
    StatusCh2_data = my4200.query(f"GN StatusCh2 {MaxSheetPoints}")
    
    print(f"VMeasCh1 Data: {VMeasCh1_data}")
    print(f"IMeasCh1 Data: {IMeasCh1_data}")
    print(f"VMeasCh2 Data: {VMeasCh2_data}")
    print(f"IMeasCh2 Data: {IMeasCh2_data}")
    
    df = parse_semicolon_data_to_df(VMeasCh1=VMeasCh1_data, IMeasCh1=IMeasCh1_data, 
                                   VMeasCh2=VMeasCh2_data, IMeasCh2=IMeasCh2_data, 
                                   TimeOutput=TimeOutput_data, StatusCh1=StatusCh1_data, 
                                   StatusCh2=StatusCh2_data)
    return df

#%% FIXED PMU Sweep Function
def idvg_sweep_pmu(my4200, vgs_start, vgs_stop, vgs_step, vds_const,
                   gatechan, sourcechan, drainchan,    
                   gatecomp, sourcecomp, draincomp,       
                   pulse_width=200e-6, dual_sweep=0, output_size=100):

    print("Setting up IDVG PMU test...")
    
    try:
        # Clear all readings from buffer
        my4200.write("BC")
        my4200.write("UL")
        
        # Keep RPMS in pulse mode
        if check_for_rpms(my4200):
            gaterpm = map_rpm_to_smu(gatechan)
            drainrpm = map_rpm_to_smu(drainchan)
            sourcerpm = map_rpm_to_smu(sourcechan)
            switch_rpm_mode(my4200, gaterpm[0], gaterpm[1], 0)
            switch_rpm_mode(my4200, drainrpm[0], drainrpm[1], 0)
            switch_rpm_mode(my4200, sourcerpm[0], sourcerpm[1], 0)
            print("RPMs in pulse mode")

        # Create voltage sweep points
        if dual_sweep == 0:
            vgs = np.arange(vgs_start, vgs_stop + vgs_step, vgs_step)
        else:
            vgs = np.concatenate((np.arange(vgs_start, vgs_stop + vgs_step, vgs_step),
                                 np.arange(vgs_stop, vgs_start-vgs_step, -vgs_step)))

        num_points = len(vgs)
        print(f"Debug: Number of VGS points: {num_points}")
        print(f"Debug: VGS values: {vgs}")
        
        # Create arrays
        SegTime = [pulse_width] * num_points 
        StartVCh1 = [0.0] * num_points
        StopVCh1 = vgs.tolist() 
        StartVCh2 = [vds_const] * num_points
        StopVCh2 = [vds_const] * num_points
        SSRCtrlCh1 = [1] * num_points
        SSRCtrlCh2 = [1] * num_points
        SegTrigOut = [0] * num_points

        # FIXED: Call correct function name
        df = pmu_segarb_example_fixed(my4200,
                               VRangeCh1=2,        #changed this from 10  
                               IRangeCh1=10e-6,       
                               VRangeCh2=2,          
                               IRangeCh2=100e-6,      
                               NumWaveforms=1,
                               DUTResCh1=50000,         ###Lower this when device is input to 1e9
                               DUTResCh2=1000,         
                               MaxSheetPoints=max(num_points * 4, 20),
                               SegTime=SegTime,       
                               StartVCh1=StartVCh1,   
                               StopVCh1=StopVCh1,     
                               StartVCh2=StartVCh2,   
                               StopVCh2=StopVCh2,     
                               SSRCtrlCh1=SSRCtrlCh1, 
                               SSRCtrlCh2=SSRCtrlCh2,
                               SegTrigOut=SegTrigOut,
                               SMU_V=0, SMU_Irange=0.01, SMU_Icomp=0.01,
                               SMU_ID="NONE", PMU_ID="PMU1",
                               Output_size=num_points)

        # Rename columns
        df_renamed = df.rename(columns={'VMeasCh1': 'VG','IMeasCh1': 'IG', 
                                       'VMeasCh2': 'VD','IMeasCh2': 'ID',
                                       'TimeOutput': 'Time'})
        
        # Add source data (assuming it's grounded)
        df_renamed['VS'] = 0.0
        df_renamed['IS'] = 0.0
        
        return df_renamed
        
    except Exception as e:
        print(f" PMU measurement failed: {e}")
        # Try to safely return to PMU mode
        try:
            if check_for_rpms(my4200):
                gaterpm = map_rpm_to_smu(gatechan)
                drainrpm = map_rpm_to_smu(drainchan)
                sourcerpm = map_rpm_to_smu(sourcechan)
                switch_rpm_mode(my4200, gaterpm[0], gaterpm[1], 0)
                switch_rpm_mode(my4200, drainrpm[0], drainrpm[1], 0)
                switch_rpm_mode(my4200, sourcerpm[0], sourcerpm[1], 0)
        except:
            pass
        raise


def idvg_sweep_smu(my4200, vgs_start, vgs_stop, vgs_step, vds_const, gatechan, sourcechan, drainchan, 
                   gatecomp, sourcecomp, draincomp, gaterange, sourcerange, drainrange, 
                   dual_sweep=0, integ_time=3, hold_time=0, delay_time=0.001, standby=1, resolution=5):
    
    print("Setting up IDVG test...")
    
    try:
        # Clear all readings from buffer
        my4200.write("BC")

        # Select channel definition page
        my4200.write("DE")
        my4200.write("CH"+str(gatechan)+",'VG','IG', 1, 1")
        my4200.write("CH"+str(drainchan)+",'VD','ID', 1, 3")
        my4200.write("CH"+str(sourcechan)+",'VS','IS', 1, 3")

        # Select source setup page
        my4200.write("SS")
        my4200.write(f"VC{gatechan}, 0, {gatecomp}")
        my4200.write(f"VC{drainchan}, 0, {draincomp}")  
        my4200.write(f"VC{sourcechan}, 0, {sourcecomp}")
        # Check if there are RPMs on system, and if so, switch them
        if check_for_rpms(my4200):
        
            gaterpm = map_rpm_to_smu(gatechan)
            drainrpm = map_rpm_to_smu(drainchan)
            sourcerpm = map_rpm_to_smu(sourcechan)
            switch_rpm_mode(my4200, gaterpm[0], gaterpm[1], 2)
            switch_rpm_mode(my4200, drainrpm[0], drainrpm[1], 2)
            switch_rpm_mode(my4200, sourcerpm[0], sourcerpm[1], 2)
            print("RPM switched to SMU")
            
        # Set up sweep parameters
        if dual_sweep == 0:
            vgs = np.arange(vgs_start, vgs_stop + vgs_step, vgs_step)
        else:
            vgs = np.concatenate((np.arange(vgs_start, vgs_stop + vgs_step, vgs_step),
                                 np.arange(vgs_stop, vgs_start-vgs_step, -vgs_step)))
        vgs_str = ",".join([format(v, ".2f") for v in vgs])
        my4200.write("VL"+str(gatechan)+", 1, "+str(gatecomp)+", "+ vgs_str)
        my4200.write("VC"+str(drainchan)+", "+str(vds_const)+", "+str(draincomp))
        my4200.write("VC"+str(sourcechan)+", 0, "+str(sourcecomp))
        
        # Set up timing parameters
        my4200.write("HT "+str(hold_time))
        my4200.write("DT "+str(delay_time))
        my4200.write("IT"+str(integ_time))
        my4200.write("ST "+str(gatechan)+", "+str(standby))
        my4200.write("ST "+str(drainchan)+", "+str(standby))
        my4200.write("ST "+str(sourcechan)+", "+str(standby))   
        
        # Set up ranging/timing parameters
        my4200.write("RS "+str(resolution))
        my4200.write("RG " + str(gatechan)+", "+str(gaterange))
        my4200.write("RG " + str(drainchan)+", "+str(drainrange))
        my4200.write("RG " + str(sourcechan)+", "+str(sourcerange))

        # Selects measurement setup page - this plots the graph in KXCI, not necessary for operation
        my4200.write("SM")
        my4200.write("DM1")
        my4200.write("XN 'VG', 1, "+str(vgs_start)+", "+str(vgs_stop))
        my4200.write("YA 'IS', 3, 0, 0.00004")
        my4200.write("YA 'ID', 3, 0, 0.00004")
        my4200.write("YB 'IG', 3, 0, 0.00004")

        # Enable service request for data ready on buffer 1
        my4200.write('DR1')
        # Selects measurement control page
        my4200.write("MD")
        # Runs a single trigger test and stores readings in cleared buffer 1
        print("Executing IDVG test...")
        my4200.write("ME1")
        wait_for_stb(my4200)

        data = pd.DataFrame({'VG': get_data(my4200, 'VG'),
                            'IG': get_data(my4200, 'IG'),
                            'VD': get_data(my4200, 'VD'),
                            'ID': get_data(my4200, 'ID'),
                            'VS': get_data(my4200, 'VS'),
                            'IS': get_data(my4200, 'IS')})
        
        # FIXED: Set outputs to 0 V BEFORE switching modes
        print("Setting outputs to safe levels...")
        zero_all_outputs(my4200, gatechan, drainchan, sourcechan, gatecomp, draincomp, sourcecomp)
        
        # Check if there are RPMs on system, and if so, switch them back to PMUs
        if check_for_rpms(my4200):
            gaterpm = map_rpm_to_smu(gatechan)
            drainrpm = map_rpm_to_smu(drainchan)
            sourcerpm = map_rpm_to_smu(sourcechan)
            switch_rpm_mode(my4200, gaterpm[0], gaterpm[1], 0)
            switch_rpm_mode(my4200, drainrpm[0], drainrpm[1], 0)
            switch_rpm_mode(my4200, sourcerpm[0], sourcerpm[1], 0)
            print("RPM switched to PMU")
        
        # Optional: Show plot briefly (non-blocking)
        plt.figure(figsize=(10, 6))
        plt.plot(data['VG'].to_numpy(), np.abs(data['ID'].to_numpy()), label='ID', color='blue', linewidth=2)
        plt.plot(data['VG'].to_numpy(), np.abs(data['IG'].to_numpy()), label='IG', color='red', linewidth=2)
        plt.plot(data['VG'].to_numpy(), np.abs(data['IS'].to_numpy()), label='IS', color='green', linewidth=2)
        plt.yscale('log')
        plt.xlabel('Gate Voltage (V)')
        plt.ylabel('Current (A)')
        plt.title('ID-VG Sweep')
        plt.legend()
        plt.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.show(block=False)
        plt.pause(3)  # Show for 3 seconds
        plt.close()

        return data
        
    except Exception as e:
        print(f" SMU measurement failed: {e}")
        # Emergency safety: try to zero outputs
        try:
            zero_all_outputs(my4200, gatechan, drainchan, sourcechan, gatecomp, draincomp, sourcecomp)
        except:
            print(" CRITICAL: Could not zero outputs after error!")
        
        # Try to return RPMs to safe mode
        try:
            if check_for_rpms(my4200):
                gaterpm = map_rpm_to_smu(gatechan)
                drainrpm = map_rpm_to_smu(drainchan)
                sourcerpm = map_rpm_to_smu(sourcechan)
                switch_rpm_mode(my4200, gaterpm[0], gaterpm[1], 0)
                switch_rpm_mode(my4200, drainrpm[0], drainrpm[1], 0)
                switch_rpm_mode(my4200, sourcerpm[0], sourcerpm[1], 0)
        except:
            pass
        raise

#%% Plotting function (unchanged but safer)
def plot_dc_vs_pulse_comparison(dc_data, pulse_data, device_id, save_plots=True):
    """Generate comparison plots for DC vs Pulse measurements."""
    
    # Ensure required columns exist and clean NaNs
    for col in ['VG','ID']:
        if col not in dc_data or col not in pulse_data:
            raise ValueError(f"Column '{col}' missing from input data.")
    
    dc_data = dc_data.dropna(subset=['VG','ID'])
    pulse_data = pulse_data.dropna(subset=['VG','ID'])
    
    if len(dc_data) != len(pulse_data):
        print(f"  Warning: DC data has {len(dc_data)} points, Pulse data has {len(pulse_data)} points")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Plot 1: Linear
    ax1.plot(dc_data['VG'], dc_data['ID'], 'r-', linewidth=2, label='DC SMU')
    ax1.plot(pulse_data['VG'], pulse_data['ID'], 'b-', linewidth=2, label='Pulse PMU')
    ax1.set_xlabel('Gate Voltage (V)')
    ax1.set_ylabel('Drain Current (A)')
    ax1.set_title(f'Device {device_id}: ID-VG Linear Scale')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # Plot 2: Log (with protection against log(0))
    dc_current = np.abs(dc_data['ID']) + 1e-15
    pulse_current = np.abs(pulse_data['ID']) + 1e-15
    
    ax2.semilogy(dc_data['VG'], dc_current, 'r-', linewidth=2, label='DC SMU')
    ax2.semilogy(pulse_data['VG'], pulse_current, 'b-', linewidth=2, label='Pulse PMU')
    ax2.set_xlabel('Gate Voltage (V)')
    ax2.set_ylabel('|Drain Current| (A)')
    ax2.set_title(f'Device {device_id}: ID-VG Log Scale')
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    plt.tight_layout()

    if save_plots:
        filename = f'device_{str(device_id).replace(" ","_").replace("/","_")}_dc_vs_pulse_comparison.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f" Plot saved as: {filename}")

    plt.show(block=False)
    plt.pause(2)
    plt.close()
    return fig

#%% Safety check function
def safe_measurement_check(data, max_gate_current=1e-3, max_drain_current=0.1, measurement_type="measurement"):
    """Check if measurement looks reasonable"""
    if len(data) == 0:
        print(f"  Warning: No data returned from {measurement_type}")
        return True
        
    max_ig = np.abs(data['IG']).max() if 'IG' in data else 0
    max_id = np.abs(data['ID']).max() if 'ID' in data else 0
    
    print(f" {measurement_type} Safety Check:")
    print(f"   Max gate current: {max_ig:.2e} A (limit: {max_gate_current:.2e} A)")
    print(f"   Max drain current: {max_id:.2e} A (limit: {max_drain_current:.2e} A)")
    
    safety_passed = True
    
    if max_ig > max_gate_current:
        print(f" SAFETY ALERT: High gate current in {measurement_type}: {max_ig:.2e} A")
        safety_passed = False
        
    if max_id > max_drain_current:
        print(f" SAFETY ALERT: High drain current in {measurement_type}: {max_id:.2e} A") 
        safety_passed = False
        
    if safety_passed:
        print(f" {measurement_type} safety check passed")
    
    return safety_passed

#%% MAIN TEST PROGRAM
if __name__ == "__main__":
    print("🔬 Starting DC vs Pulse Comparison Test - CORRECTED VERSION")
    
    # Connect to instrument
    my4200 = connect_4200()
    if my4200 is None:
        print(" Connection failed")
        exit()
    
    # Safe test parameters
    test_params = {
        'vgs_start': -1.0,
        'vgs_stop': 1.0,
        'vgs_step': 0.5,
        'vds_const': 0.1,
        'gatechan': 1,
        'sourcechan': 2, 
        'drainchan': 3,
        'gatecomp': 10e-6,
        'draincomp': 100e-6,
        'sourcecomp': 10e-6,
        'gaterange': "10e-6",
        'sourcerange': "10e-6",
        'drainrange': "100e-6"
    }
    
    try:
        # Test 1: DC measurement
        print("\n" + "="*50)
        print("TESTING DC MEASUREMENT (SMU)")
        print("="*50)
        dc_data = idvg_sweep_smu(my4200, 
                               test_params['vgs_start'], test_params['vgs_stop'], 
                               test_params['vgs_step'], test_params['vds_const'],
                               test_params['gatechan'], test_params['sourcechan'], 
                               test_params['drainchan'], test_params['gatecomp'],
                               test_params['sourcecomp'], test_params['draincomp'],
                               test_params['gaterange'], test_params['sourcerange'], 
                               test_params['drainrange'], dual_sweep=0, integ_time=3)
        
        print(f" DC test complete: {len(dc_data)} points")
        print(f"DC current range: {dc_data['ID'].min():.2e} to {dc_data['ID'].max():.2e} A")
        
        # Safety check after DC measurement
        if not safe_measurement_check(dc_data, measurement_type="DC measurement"):
            print(" DC measurement shows concerning currents - aborting for safety")
            disconnect_4200(my4200)
            exit()
        
        # Test 2: Pulse measurement
        print("\n" + "="*50) 
        print("TESTING PULSE MEASUREMENT (PMU)")
        print("="*50)
        
        pulse_data = idvg_sweep_pmu(my4200,
                          test_params['vgs_start'], test_params['vgs_stop'],
                          test_params['vgs_step'], test_params['vds_const'], 
                          test_params['gatechan'], test_params['sourcechan'],
                          test_params['drainchan'], test_params['gatecomp'],
                          test_params['sourcecomp'], test_params['draincomp'],
                          pulse_width=20e-6, #increase by one factor of 0
                          dual_sweep=0, 
                          output_size=10)
        
        print(f"Pulse test complete: {len(pulse_data)} points")
        print(f"Pulse current range: {pulse_data['ID'].min():.2e} to {pulse_data['ID'].max():.2e} A")
        
        # Safety check after pulse measurement
        if not safe_measurement_check(pulse_data, measurement_type="Pulse measurement"):
            print("  Pulse measurement shows concerning currents")
            print("  Continuing to generate plot, but investigate current levels")
        
        # Test 3: Generate comparison plot
        print("\n" + "="*50)
        print("GENERATING COMPARISON PLOT")  
        print("="*50)
        fig = plot_dc_vs_pulse_comparison(dc_data, pulse_data, "DCvsPulseTest", save_plots=True)
        print(" Comparison plot generated and saved!")
        
        print(" ALL TESTS COMPLETED SUCCESSFULLY!")
        
    except Exception as e:
        print(f" ERROR during testing: {e}")
        import traceback
        traceback.print_exc()
        
        # Emergency safety: try to zero all outputs
        try:
            print(" Emergency safety: attempting to zero all outputs...")
            zero_all_outputs(my4200, test_params['gatechan'], test_params['drainchan'], 
                            test_params['sourcechan'], test_params['gatecomp'], 
                            test_params['draincomp'], test_params['sourcecomp'])
        except Exception as safety_error:
            print(f" CRITICAL: Emergency safety failed: {safety_error}")
            print("  MANUALLY CHECK INSTRUMENT OUTPUTS!")
        
    finally:
        print("\n Disconnecting safely...")
        disconnect_4200(my4200)
        print(" Disconnected safely")
        

#%% Additional safety functions (optional extras)
def emergency_stop_all(my4200):
    """Emergency function to stop all operations and zero outputs"""
    try:
        print(" EMERGENCY STOP - Zeroing all outputs...")
        for chan in [1, 2, 3, 4]:
            my4200.write(f"VC{chan}, 0, 0.01")
        my4200.write("BC")  # Clear buffers
        print(" Emergency stop completed")
    except Exception as e:
        print(f" Emergency stop failed: {e}")

def quick_test_connection():
    """Quick function to test if Keithley is responsive"""
    try:
        my4200 = connect_4200()
        if my4200:
            idn = my4200.query("*IDN?")
            print(f" Keithley responsive: {idn}")
            my4200.close()
            return True
        else:
            print(" Connection failed")
            return False
    except Exception as e:
        print(f" Connection test failed: {e}")
        return False

# End of corrected code