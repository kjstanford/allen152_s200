import numpy as np
import pandas as pd
from b1500A_utils.initialize_smus import *
from b1500A_utils.FET_three_terminal import *

smu_gate = b1500.smu3
smu_drain = b1500.smu2
smu_source = b1500.smu4

meas_data = FET_sampling(b1500=b1500, smu_gate=smu_gate, smu_drain=smu_drain, smu_source=smu_source, gate_voltage=0.0, drain_voltage=0.0, source_voltage=0.0, hold_time=0.0, base_voltage=0.0, sampling_interval=1.0, nop=11, Irange='1 nA limited auto ranging', Vrange='2 V limited auto ranging')

print(meas_data.head(10))
