import pyvisa

rm = pyvisa.ResourceManager()              # should pick up Keysight VISA
print(rm.list_resources())

inst = rm.open_resource("GPIB0::18::INSTR")  # same as Interactive IO
inst.timeout = 30000
inst.write_termination = '\n'
inst.read_termination = '\n'

print(inst.query("IDN?"))
inst.close()
