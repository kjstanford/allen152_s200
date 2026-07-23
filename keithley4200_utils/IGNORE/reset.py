import pyvisa

def connect_4200(resource_string="GPIB::18::INSTR"):  # Adjust as needed!
    rm = pyvisa.ResourceManager()
    instr = rm.open_resource(resource_string)
    return instr

def disconnect_4200(instr):
    instr.close()

# --- Now your cell ---
my4200 = connect_4200()

# Reset everything to default state
my4200.write("*RST")  # Reset instrument
my4200.write("DE")    # Go to channel definition page
my4200.write("SS")    # Go to source setup page  
my4200.write("MD")    # Go to measurement page

disconnect_4200(my4200)