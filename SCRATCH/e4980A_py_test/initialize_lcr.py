from pymeasure.instruments.resources import list_resources
list_resources()

from pymeasure.instruments.agilent import AgilentE4980

e4980 = AgilentE4980('GPIB0::17::INSTR', timeout=600000)

print(f"Initialized {e4980.name} with ID: {e4980.id} ...")
e4980.mode = 'CPRP'
print(f"LCR measurement mode: {e4980.mode}")

# # Perform a frequency sweep and print the results
# data_e4980 = e4980.freq_sweep([5e2, 1e3, 1e4, 1e5, 1e6, 2e6], return_freq=True)
# print(data_e4980)

# # Print all public properties and methods of the e4980 object
# print("\n--- Available Class Functions & Properties ---")
# for item in dir(e4980):
#     if not item.startswith("_"):
#         print(item)