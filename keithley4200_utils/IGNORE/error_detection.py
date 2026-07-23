import pyvisa
import time

def get_exact_parameters():
    try:
        rm = pyvisa.ResourceManager()
        my4200 = rm.open_resource("GPIB0::18::INSTR", timeout=10000)
        my4200.write("UL")
        
        # Try different commands to get parameter info
        help_commands = [
            "GH PMU_examples_ulib PMU_SegArb_Example",  # Get help
            "GD PMU_examples_ulib PMU_SegArb_Example",  # Get description  
            "GP PMU_examples_ulib PMU_SegArb_Example",  # Get parameters
            "GS PMU_examples_ulib PMU_SegArb_Example",  # Get signature
            "HELP PMU_examples_ulib PMU_SegArb_Example"  # Alternative help
        ]
        
        for cmd in help_commands:
            try:
                result = my4200.query(cmd)
                print(f"Command '{cmd}':")
                print(f"Result: {result}")
                print("-" * 50)
            except Exception as e:
                print(f"Command '{cmd}' failed: {e}")
                
        my4200.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_exact_parameters()