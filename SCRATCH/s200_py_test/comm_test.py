from urllib import response
import pyvisa
import time

# Configuration
GPIB_ADDRESS = 22  # Must match the address set in Velox preferences
RESOURCE_STR = f'GPIB0::{GPIB_ADDRESS}::INSTR'

rm = pyvisa.ResourceManager()

try:
    # Open connection to the probe station
    prober = rm.open_resource(RESOURCE_STR)
    
    prober.timeout = 20000  # set timeout to 20 seconds
    
    print(f"Connected to: {prober.query('*IDN?')}")

    def move_relative(x_microns, y_microns):
        """
        Relative move of the chuck by specified microns in X and Y directions.
        """
        response = prober.query('ReadChuckPosition')
        print(f"Start Position: {response}")
        
        print(f"Moving chuck to separation height...")
        prober.write('MoveChuckSeparation 100.')
        time.sleep(5)


        print(f"Commanding move: X={x_microns}, Y={y_microns}...")        
        prober.write(f'MoveChuck {-1*x_microns} {-1*y_microns} R Y 100.')
        time.sleep(10)

        print(f"Moving chuck to contact height...")
        prober.write('MoveChuckContact 100.')
        time.sleep(5)

        response = prober.query('ReadChuckPosition')
        print(f"Current Position: {response}")


    time.sleep(5)
    move_relative(-8000, 0)

except pyvisa.VisaIOError as e:
    print(f"Communication Error: {e}")
finally:
    # Clean up
    if 'prober' in locals():
        prober.close()
    rm.close()