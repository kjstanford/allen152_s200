from keithley4200_utils.k4200_helpers import connect_4200, disconnect_4200
from keithley4200_utils.gc_helpers import (
    wbl_sweep,
    wwl_sweep,
    gc_retention_test,
)

smu = connect_4200("GPIB0::18::INSTR")

if smu is None:
    raise RuntimeError("Could not connect to the 4200A")

try:
    # Replace these example voltages with safe values for your device.
    common = {
        "vdata0": -0.5,
        "vdata1": 2.0,
        "vboost": 2.5,
        "vhold": -1.0,
        "vdd": 2.0,
        "vss": 0.0,
        "compliances": 10e-3,
        "current_ranges": "1e-6",
        "integration_time": 1,
        "show_plot": True,
    }

    data = wbl_sweep(
        smu,
        vdata0=common["vdata0"],
        vdata1=common["vdata1"],
        vdata_step=0.1,
        vboost=common["vboost"],
        vdd=common["vdd"],
        vss=common["vss"],
        compliances=common["compliances"],
        current_ranges=common["current_ranges"],
        integration_time=common["integration_time"],
        show_plot=common["show_plot"],
    )

    print(data)
    data.to_csv("wbl_test.csv", index=False)

    data = wwl_sweep(
        smu,
        state=1,
        vdata0=common["vdata0"],
        vdata1=common["vdata1"],
        vhold=common["vhold"],
        vboost=common["vboost"],
        vwwl_step=0.05,
        vdd=common["vdd"],
        vss=common["vss"],
        compliances=common["compliances"],
        current_ranges=common["current_ranges"],
        integration_time=common["integration_time"],
        show_plot=common["show_plot"],
    )

    print(data)
    data.to_csv("wwl_test.csv", index=False)

    data = gc_retention_test(
        smu,
        state=1,
        vdata0=common["vdata0"],
        vdata1=common["vdata1"],
        vhold=common["vhold"],
        vboost=common["vboost"],
        vdd=common["vdd"],
        vss=common["vss"],
        tretention=500,
        sample_interval=1.0,
        compliances=common["compliances"],
        current_ranges=common["current_ranges"],
        integration_time=common["integration_time"],
        show_plot=common["show_plot"],
    )

    print(data)
    data.to_csv("retention_test.csv", index=False)

finally:
    disconnect_4200(smu)