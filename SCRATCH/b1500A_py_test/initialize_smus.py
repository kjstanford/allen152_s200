from pymeasure.instruments.agilent import AgilentB1500
import pymeasure
print(f"Pymeasure location: {pymeasure.__file__}")

# 1. Connect to the instrument
b1500 = AgilentB1500("GPIB0::16::INSTR", read_termination='\r\n', write_termination='\r\n', timeout=600000)

# Patch the query_modules method to recognize the B1530A WGFMU

def patched_query_modules():
    """
    Replacement for AgilentB1500.query_modules() that adds support for the B1530A WGFMU.

    The stock pymeasure driver does not recognise the B1530A model string, causing
    initialize_all_smus() to fail on chassis that contain one.  This function sends
    the same 'UNT? 0' query but uses an extended module_names map that includes the
    B1530A.  The B1530A entry is returned as 'WGFMU'; because initialize_all_smus()
    only creates SMU objects for HPSMU/MPSMU/HRSMU types, the WGFMU slot is silently
    skipped while all other SMUs are initialised normally.

    Returns
    -------
    dict
        Mapping of slot index (1-based int) to module type string
        (e.g. {2: 'HRSMU', 3: 'HRSMU', 4: 'HRSMU'}).
    """
    # We define the map locally including the missing B1530A
    # This is based on the source code of pymeasure AgilentB1500
    module_names = {
        'B1510A': 'HPSMU',
        'B1511A': 'MPSMU',
        'B1511B': 'MPSMU',
        'B1517A': 'HRSMU',
        'B1520A': 'MFCMU',
        'B1525A': 'HVSPGU',
        'B1530A': 'WGFMU',  # <--- Added this line
    }
    
    # Send the UNT? 0 command to query modules
    # The driver usually splits the response string "B1517A,0;B1530A,0..."
    response = b1500.ask("UNT? 0")
    
    modules = {}
    if response:
        # The response format is usually: model,status;model,status...
        # We need to parse this string manually since we are bypassing the original method
        params = response.split(';')
        for i, param in enumerate(params):
            if ',' in param:
                model, status = param.split(',')
                if model in module_names:
                    # Only add if it's a known SMU type we want to control
                    # The initialize_all_smus loop looks for HPSMU/MPSMU/HRSMU
                    modules[i + 1] = module_names[model]
    return modules

# Replace the method on your instance
b1500.query_modules = patched_query_modules

# 4. Now initialize. The B1530A will be identified but skipped during SMU object creation 
# (assuming the driver logic filters for 'SMU' strings, or we simply don't return it in the dict above if we don't want to control it).
b1500.initialize_all_smus()

# # Check what was found
# print("Raw Modules detected:", b1500.query_modules())
# for i in range(1, 11):
#     if hasattr(b1500, f"smu{i}"):
#         print(f"smu{i} initialized: {getattr(b1500, f'smu{i}')}")