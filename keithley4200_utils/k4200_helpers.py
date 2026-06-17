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
        # Open connection to the Keithley 4200
        my4200 = rm.open_resource(resource_string)
        
        my4200.timeout = timeout  # set timeout to 20 seconds
        
        print(f"Connected to: {my4200.query('IDN?')}")
    except pyvisa.VisaIOError as e:
        print(f"Communication Error: {e}")
        return None

    return my4200

def disconnect_4200(my4200=None):
    if my4200 is None:
        print("Keithley resource not provided. Cannot disconnect.")
        return 1
    """
    Close the connection to the Keithley 4200.
    """
    try:
        my4200.close()
        print("Disconnected from Keithley 4200.")
    except pyvisa.VisaIOError as e:
        print(f"Communication Error: {e}")
    return 0

def get_data(my4200, chan):
    print(my4200.query('IDN?'))

    # Get data
    datastring=[]
    print("Reading "+chan+"...")
    data = my4200.query("DO '"+chan+"'")
    # print("DO '"+chan+"'")

    string_list = data.split(",")
    realdata = [float(item[1:]) for item in string_list]
    print(realdata)
    return realdata

# Wait for status byte to be 0, which indicates data is ready in buffer after a measurement
def wait_for_stb(my4200, delay=1):
    time.sleep(delay)
    while True:
        status = my4200.read_stb()
        print(f"Status byte: {status}")
        if status == 0 or status == 1:  # Check if all bits are zero
            print("Data ready")
            break
        else:
            time.sleep(1)

def check_for_rpms(my4200):
    settings = my4200.query("*OPT?")
    if settings.find("RPM") > -1:
        return True
    else:
        return False

def switch_rpm_mode(my4200, card, chan, mode):
    """
    Mode: 0 = Pulse, 1 = CV 2-wire, 2 = SMU, 3 = CV 4-wire
    """
    # SS (Set Status) clears the status byte and prepares the bus
    my4200.write("SS")
    
    # Command format: RP PMUn-m, mode
    # Example: RP PMU1-1, 2 (Switches Channel 1 of Card 1 to SMU mode)
    cmd = f"RP PMU{card}-{chan}, {mode}"
    
    my4200.write(cmd)

    return None

def map_rpm_to_smu(smu):
    """
    Maps SMUs to RPMs based on the system
    Tells which RPMs to switch to SMU mode when running IdVg sweeps
    Current mapping: SMU1:PMU1-1, SMU2:PMU1-2, SMU3:PMU2-1, SMU4:PMU2-2
    """
    if smu % 2 == 0:
        return math.ceil(smu/2), 2
    else:
        return math.ceil(smu/2), 1

def parse_semicolon_data_to_df(**data_dict):
    """
    Convert semicolon-separated data strings to numpy arrays and pandas DataFrame.
    
    Generic function that accepts any number of semicolon-separated data columns.
    
    Parameters:
    -----------
    **data_dict : dict
        Keyword arguments where key is column name and value is the semicolon-separated string.
        Example: parse_semicolon_data_to_df(Vforce="1.2;3.4;5.6", Imeasd="0.1;0.2;0.3")
    
    Returns:
    --------
    df : pd.DataFrame
        DataFrame with columns corresponding to the provided keyword arguments
    
    Examples:
    ---------
    # Three columns
    df = parse_semicolon_data_to_df(Vforce=vforce_str, Imeasd=imeasd_str, Timed=timed_str)
    
    # Two columns
    df = parse_semicolon_data_to_df(Voltage=volt_str, Current=curr_str)
    
    # Any number of columns
    df = parse_semicolon_data_to_df(Data1=str1, Data2=str2, Data3=str3, Data4=str4)
    """
    parsed_data = {}
    
    # Parse each data string and convert to numpy array
    for col_name, data_string in data_dict.items():
        parsed_data[col_name] = np.array([float(x) for x in data_string.split(';') if x.strip()])
    
    # Create DataFrame
    df = pd.DataFrame(parsed_data)
    
    return df


# %% Define an Id-Vgs test
def idvg_sweep_smu(my4200,vgs_start, vgs_stop, vgs_step, vds_const,
               gatechan, sourcechan, drainchan,
               gatecomp, sourcecomp, draincomp, 
               gaterange, sourcerange, drainrange,
               dual_sweep = 0, integ_time = 3,
               hold_time = 0, delay_time = 0.001, standby = 1, resolution = 5):
    
    print("Setting up IDVG test...")
    # Clear all readings from buffer
    my4200.write("BC")

    # Select channel definition page
    my4200.write("DE")
    my4200.write("CH"+str(gatechan)+",'VG','IG', 1, 1")
    my4200.write("CH"+str(drainchan)+",'VD','ID', 1, 3")
    my4200.write("CH"+str(sourcechan)+",'VS','IS', 1, 3")

    # Select source setup page
    my4200.write("SS")
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
        vgs = np.concatenate((np.arange(vgs_start, vgs_stop + vgs_step, vgs_step),np.arange(vgs_stop, vgs_start-vgs_step, -vgs_step)))
    vgs_str = ",".join([format(v, ".2f") for v in vgs])
    my4200.write("VL"+str(gatechan)+", 1, "+str(gatecomp)+", "+ vgs_str)
    my4200.write("VC"+str(drainchan)+", "+str(vds_const)+", "+str(draincomp))
    my4200.write("VC"+str(sourcechan)+", 0, "+str(sourcecomp))
    #Set up timing parameters
    my4200.write("HT "+str(hold_time))
    my4200.write("DT "+str(delay_time))
    my4200.write("IT"+str(integ_time))
    my4200.write("ST "+str(gatechan)+", "+str(standby))
    my4200.write("ST "+str(drainchan)+", "+str(standby))
    my4200.write("ST "+str(sourcechan)+", "+str(standby))   
    # Set up ranging/timing parameters
    my4200.write("RS "+str(resolution))
    rangelist = ["1e-12","10e-12","100e-12","1e-9","10e-9","100e-9",
                 "1e-6","10e-6","100e-6","1e-3","10e-3","100e-3","1"]
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
    
    # TODO: Set outputs to 0 V
    # Check if there are RPMs on system, and if so, switch them back to PMUs
    if check_for_rpms(my4200):
        gaterpm = map_rpm_to_smu(gatechan)
        drainrpm = map_rpm_to_smu(drainchan)
        sourcerpm = map_rpm_to_smu(sourcechan)
        switch_rpm_mode(my4200, gaterpm[0], gaterpm[1], 0)
        switch_rpm_mode(my4200, drainrpm[0], drainrpm[1], 0)
        switch_rpm_mode(my4200, sourcerpm[0], sourcerpm[1], 0)
        print("RPM switched to PMU")
    return data


# %% Define an Id-Vds test
def idvd_sweep_smu(my4200, vgs_start, vgs_stop, vgs_step, vds_start, vds_stop, vds_step,
               gatechan, sourcechan, drainchan,
               gatecomp, sourcecomp, draincomp, 
               gaterange, sourcerange, drainrange,
               dual_sweep = 0, integ_time = 3,
               hold_time = 0, delay_time = 0.001, standby = 1, resolution = 5):
    
    print("Setting up IDVD test...")
    # Clear all readings from buffer
    my4200.write("BC")

    # Select channel definition page
    my4200.write("DE")
    my4200.write("CH"+str(gatechan)+",'VG','IG', 1, 2")
    my4200.write("CH"+str(drainchan)+",'VD','ID', 1, 1")
    my4200.write("CH"+str(sourcechan)+",'VS','IS', 1, 3")

    # Select source setup page
    my4200.write("SS")
    # Check if there are RPMs on system, and if so, switch them
    if check_for_rpms(my4200):
        gaterpm = map_rpm_to_smu(gatechan)
        drainrpm = map_rpm_to_smu(drainchan)
        sourcerpm = map_rpm_to_smu(sourcechan)
        switch_rpm_mode(my4200, gaterpm[0], gaterpm[1], 2)
        switch_rpm_mode(my4200, drainrpm[0], drainrpm[1], 2)
        switch_rpm_mode(my4200, sourcerpm[0], sourcerpm[1], 2)
        print("RPM switched to SMU")
    if dual_sweep == 0:
        vds = np.arange(vds_start, vds_stop + vds_step, vds_step)
    else:
        vds = np.concatenate((np.arange(vds_start, vds_stop + vds_step, vds_step),np.arange(vds_stop, vds_start-vds_step, -vds_step)))
    vds_str = ",".join([format(v, ".2f") for v in vds])
    my4200.write("VL"+str(drainchan)+", 1, "+str(draincomp)+", "+ vds_str)
    # my4200.write("VP "+str(vgs_start)+", "+str(vgs_stop+vgs_step)+", "+str(vgs_step)+", "+str(gatecomp))
    # VP command: VP [start] [step] [numsteps] [comp]
    numsteps = (vgs_stop-vgs_start)/vgs_step
    my4200.write("VP "+str(vgs_start)+", "+str(vgs_step)+", "+str(int(numsteps+1))+", "+str(gatecomp))
    my4200.write("VC"+str(sourcechan)+", 0, "+str(sourcecomp))

    my4200.write("HT "+str(hold_time))
    my4200.write("DT "+str(delay_time))
    my4200.write("IT"+str(integ_time))  

    my4200.write("RS "+str(resolution))
    rangelist = ["1e-12","10e-12","100e-12","1e-9","10e-9","100e-9",
                 "1e-6","10e-6","100e-6","1e-3","10e-3","100e-3","1"]
    my4200.write("RG " + str(gatechan)+", "+str(gaterange))
    my4200.write("RG " + str(drainchan)+", "+str(drainrange))
    my4200.write("RG " + str(sourcechan)+", "+str(sourcerange))

    # Selects measurement setup page
    my4200.write("SM")
    my4200.write("DM1")
    my4200.write("XN 'VD', 1, "+str(vgs_start)+", "+str(vgs_stop))
    my4200.write("YA 'ID', 1, 0, 0.04")
    my4200.write("YB 'IG', 1, 0, 0.04")

    # Enable service request for data ready on buffer 1
    my4200.write('DR1')
    # Selects measurement control page
    my4200.write("MD")
    # Runs a single trigger test and stores readings in cleared buffer 1
    print("Executing IDVD test...")
    my4200.write("ME1")
    wait_for_stb(my4200)

    data = pd.DataFrame({'VG': get_data(my4200, 'VG'),
                        'IG': get_data(my4200,'IG'),
                        'VD': get_data(my4200,'VD'),
                        'ID': get_data(my4200,'ID'),
                        'VS': get_data(my4200,'VS'),
                        'IS': get_data(my4200,'IS')})
    
    # Check if there are RPMs on system, and if so, switch them back to PMUs
    if check_for_rpms(my4200):
        gaterpm = map_rpm_to_smu(gatechan)
        drainrpm = map_rpm_to_smu(drainchan)
        sourcerpm = map_rpm_to_smu(sourcechan)
        switch_rpm_mode(my4200, gaterpm[0], gaterpm[1], 0)
        switch_rpm_mode(my4200, drainrpm[0], drainrpm[1], 0)
        switch_rpm_mode(my4200, sourcerpm[0], sourcerpm[1], 0)
        print("RPM switched to PMU")
    
    # TODO: Set outputs to 0 V
    return data

# # %% Beep the Keithley using the BeepLib UTM
# def keithley_beep(my4200, freq, duration):
#     my4200.write("UL")
#     my4200.write("EX BeepLib beep(2000, 500)")
#     time.sleep(2)
#     my4200.write("DE")

# def keithley_sing(my4200, song):
#     # 1=BeepUp, 2=BeepDown, 3=BeepCharge
#     my4200.write("UL")
#     match song:
#         case 1: my4200.write("EX BeepLib BeepUp()")
#         case 2: my4200.write("EX BeepLib BeepDown()")
#         case 3: my4200.write("EX BeepLib BeepCharge()")
#     time.sleep(5)
#     my4200.write("DE")
#     # print(my4200.query("GD BeepLib BeepCharge"))

def list_to_semicolon_str_V(num_list):
    return '; '.join([f"{x:.3f}" for x in num_list])

def list_to_semicolon_str_t(num_list):
    return '; '.join([f"{x:f}" for x in num_list])

def list_to_semicolon_str_int(num_list):
    return '; '.join([f"{x:d}" for x in num_list])

def pmu_segarb_example(my4200, VRangeCh1=10, IRangeCh1=0.01, VRangeCh2=10, IRangeCh2=0.01, NumWaveforms=1, DUTResCh1=1e6, DUTResCh2=1e6, MaxSheetPoints=5000, SegTime=[], StartVCh1=[], StopVCh1=[], StartVCh2=[], StopVCh2=[], SSRCtrlCh1=[], SSRCtrlCh2=[], SegTrigOut=[], SMU_V=0, SMU_Irange=0.01, SMU_Icomp=0.01, SMU_ID="NONE", PMU_ID="PMU1", Output_size=10000):
    # Clear all readings from buffer
    my4200.write("BC")

    my4200.write("UL")
    my4200.write(f"EX PMU_examples_ulib PMU_SegArb_Example({VRangeCh1}, {IRangeCh1}, {VRangeCh2}, {IRangeCh2}, {NumWaveforms}, {DUTResCh1}, {DUTResCh2}, {MaxSheetPoints}, {len(SegTime)}, {list_to_semicolon_str_t(SegTime)}, {len(SegTime)}, {list_to_semicolon_str_V(StartVCh1)}, {len(StartVCh1)}, {list_to_semicolon_str_V(StopVCh1)}, {len(StopVCh1)}, {list_to_semicolon_str_V(StartVCh2)}, {len(StartVCh2)}, {list_to_semicolon_str_V(StopVCh2)}, {len(StopVCh2)}, {list_to_semicolon_str_int(SSRCtrlCh1)}, {len(SSRCtrlCh1)}, {list_to_semicolon_str_int(SSRCtrlCh2)}, {len(SSRCtrlCh2)}, {list_to_semicolon_str_int(SegTrigOut)}, {len(SegTrigOut)}, {SMU_V}, {SMU_Irange}, {SMU_Icomp},{SMU_ID},{PMU_ID}, , {Output_size}, , {Output_size}, , {Output_size}, , {Output_size}, , {Output_size}, , {Output_size}, , {Output_size})")
    print(f"EX PMU_examples_ulib PMU_SegArb_Example({VRangeCh1}, {IRangeCh1}, {VRangeCh2}, {IRangeCh2}, {NumWaveforms}, {DUTResCh1}, {DUTResCh2}, {MaxSheetPoints}, {len(SegTime)}, {list_to_semicolon_str_t(SegTime)}, {len(SegTime)}, {list_to_semicolon_str_V(StartVCh1)}, {len(StartVCh1)}, {list_to_semicolon_str_V(StopVCh1)}, {len(StopVCh1)}, {list_to_semicolon_str_V(StartVCh2)}, {len(StartVCh2)}, {list_to_semicolon_str_V(StopVCh2)}, {len(StopVCh2)}, {list_to_semicolon_str_int(SSRCtrlCh1)}, {len(SSRCtrlCh1)}, {list_to_semicolon_str_int(SSRCtrlCh2)}, {len(SSRCtrlCh2)}, {list_to_semicolon_str_int(SegTrigOut)}, {len(SegTrigOut)}, {SMU_V}, {SMU_Irange}, {SMU_Icomp},{SMU_ID},{PMU_ID}, , {Output_size}, , {Output_size}, , {Output_size}, , {Output_size}, , {Output_size}, , {Output_size}, , {Output_size})")
    # Runs a single trigger test and stores readings in cleared buffer 1
    print("Executing PMU_SegArb_ExampleFull module from PMU_examples_ulib library...")
    my4200.write("ME1")
    wait_for_stb(my4200)

    # After wait_for_stb returns:
    return_data = my4200.query("DO") # Requests the stored data from Buffer 1
    print(f"Return Value: {return_data}")

    VMeasCh1_data = my4200.query(f"GN VMeasCh1 {Output_size}")
    IMeasCh1_data = my4200.query(f"GN IMeasCh1 {Output_size}")
    VMeasCh2_data = my4200.query(f"GN VMeasCh2 {Output_size}")
    IMeasCh2_data = my4200.query(f"GN IMeasCh2 {Output_size}")
    TimeOutput_data = my4200.query(f"GN TimeOutput {Output_size}")
    StatusCh1_data = my4200.query(f"GN StatusCh1 {Output_size}")
    StatusCh2_data = my4200.query(f"GN StatusCh2 {Output_size}")
    print(f"VMeasCh1 Data: {VMeasCh1_data}")
    print(f"IMeasCh1 Data: {IMeasCh1_data}")
    print(f"VMeasCh2 Data: {VMeasCh2_data}")
    print(f"IMeasCh2 Data: {IMeasCh2_data}")
    print(f"TimeOutput Data: {TimeOutput_data}")
    print(f"StatusCh1 Data: {StatusCh1_data}")
    print(f"StatusCh2 Data: {StatusCh2_data}")
    df = parse_semicolon_data_to_df(VMeasCh1=VMeasCh1_data, IMeasCh1=IMeasCh1_data, VMeasCh2=VMeasCh2_data, IMeasCh2=IMeasCh2_data, TimeOutput=TimeOutput_data, StatusCh1=StatusCh1_data, StatusCh2=StatusCh2_data)
    return df

def keithley_beep_BeepLib(my4200, freq=2000, duration=500):
    # Clear all readings from buffer
    my4200.write("BC")
    my4200.write("UL")
    my4200.write(f"EX BeepLib beep({freq}, {duration})")
    wait_for_stb(my4200)
    data = my4200.query("DO") # Requests the stored data from Buffer 1
    print(f"Beep Data: {data}")

def keithley_nvm_dcSweep(my4200, SMU_low="SMU1", SMU_high="SMU2", compCH=1, measCH=2, irange=0.0, ilimit=0.0, stepTime=0.0, widthTime=0.001, vamp=1, vamp_pts=300, vforce_pts=300, imeasd_pts=300, timed_pts=300):
    # Clear all readings from buffer
    my4200.write("BC")

    my4200.write("UL")
    return_data = my4200.write(f"EX nvm dcSweep({SMU_low},{SMU_high}, {compCH}, {measCH}, {irange}, {ilimit}, {stepTime}, {widthTime}, {vamp}, {vamp_pts}, , {vforce_pts}, , {imeasd_pts}, , {timed_pts})")
    print(f"EX nvm dcSweep({SMU_low},{SMU_high}, {compCH}, {measCH}, {irange}, {ilimit}, {stepTime}, {widthTime}, {vamp}, {vamp_pts}, , {vforce_pts}, , {imeasd_pts}, , {timed_pts})")
    wait_for_stb(my4200)
    # After wait_for_stb returns:
    print(f"Return Value: {return_data}")
    vforce_data = my4200.query(f"GN vforce {vforce_pts}")
    imeasd_data = my4200.query(f"GN imeasd {imeasd_pts}")
    timed_data = my4200.query(f"GN timed {timed_pts}")
    print(f"Vforce Data: {vforce_data}")
    print(f"Imeasd Data: {imeasd_data}")
    print(f"Timed Data: {timed_data}")
    df = parse_semicolon_data_to_df(Vforce=vforce_data, Imeasd=imeasd_data, Timed=timed_data)
    return df


    