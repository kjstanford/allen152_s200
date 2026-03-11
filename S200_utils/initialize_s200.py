from urllib import response
import pyvisa

# Configuration
GPIB_ADDRESS = 22  # Must match the address set in Velox preferences
RESOURCE_STR = f'GPIB0::{GPIB_ADDRESS}::INSTR'

rm = pyvisa.ResourceManager()

try:
    # Open connection to the probe station
    prober = rm.open_resource(RESOURCE_STR)
    
    prober.timeout = 20000  # set timeout to 20 seconds
    
    print(f"Connected to: {prober.query('*IDN?')}")
except pyvisa.VisaIOError as e:
    print(f"Communication Error: {e}")