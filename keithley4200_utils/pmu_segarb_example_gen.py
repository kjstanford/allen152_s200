import numpy as np
import pandas as pd

pmu_segarb_columns = ["SegTime (s)", "StartVCh1 (V)", "StopVCh1 (V)", "StartVCh2 (V)", "StopVCh2 (V)", "SSRCtrlCh1 (0/1)", "SSRCtrlCh2 (0/1)", "SegTrigOut (0/1)"]

seg_meas_type_default_val = 2
seg_meas_start_default_val = 0
seg_meas_stop_default_val = 1
ssr_ctrl_ch_default_val = 1

def hold_row_gen(vhold_ch1, vhold_ch2, thold, trig_enable=1):
    return [thold, round(vhold_ch1, 3), round(vhold_ch1, 3), round(vhold_ch2, 3), round(vhold_ch2, 3), ssr_ctrl_ch_default_val, ssr_ctrl_ch_default_val, trig_enable]

def trans_row_gen(current_v_ch1, next_v_ch1, current_v_ch2, next_v_ch2, trf, trig_enable=0):
    return [trf, round(current_v_ch1, 3), round(next_v_ch1, 3), round(current_v_ch2, 3), round(next_v_ch2, 3), ssr_ctrl_ch_default_val, ssr_ctrl_ch_default_val, trig_enable]

def initial_row_gen(thold, trig_enable=1):
    return [thold, 0, 0, 0, 0, ssr_ctrl_ch_default_val, ssr_ctrl_ch_default_val, trig_enable]

def zero_to_init_row_gen(init_v_ch1, init_v_ch2, trf, trig_enable=0):
    return [trf, 0, init_v_ch1, 0, init_v_ch2, ssr_ctrl_ch_default_val, ssr_ctrl_ch_default_val, trig_enable]

def back_to_zero_row_gen(current_v_ch1, current_v_ch2, trf, trig_enable=0):
    return [trf, current_v_ch1, 0, current_v_ch2, 0, ssr_ctrl_ch_default_val, ssr_ctrl_ch_default_val, trig_enable]

def finish_row_gen(thold, trig_enable=0):
    return [thold, 0, 0, 0, 0, ssr_ctrl_ch_default_val, ssr_ctrl_ch_default_val, trig_enable]

def stair_case_ramp_gen(start_v=0, stop_v=2, step_v=0.1, bias_v=0.1, trf=1e-6, thold=1e-5, sweep_mode="double"):
    segarb_rows = []
    ttot = 0
    current_v = start_v
    while not np.isclose(stop_v, current_v):
        hold_row = hold_row_gen(vhold_ch1=current_v, vhold_ch2=bias_v, thold=thold, trig_enable=1)
        ttot += thold
        segarb_rows.append(hold_row)
        next_v = current_v + step_v
        if next_v > stop_v:
            next_v = stop_v
        rf_row = trans_row_gen(current_v_ch1=current_v, next_v_ch1=next_v, current_v_ch2=bias_v, next_v_ch2=bias_v, trf=trf, trig_enable=0)
        ttot += trf
        segarb_rows.append(rf_row)
        current_v = next_v
    segarb_rows.append(hold_row_gen(vhold_ch1=current_v, vhold_ch2=bias_v, thold=thold, trig_enable=0))
    ttot += thold
    if sweep_mode == "double":
        current_v = stop_v
        while not np.isclose(start_v, current_v):
            hold_row = hold_row_gen(vhold_ch1=current_v, vhold_ch2=bias_v, thold=thold, trig_enable=0)
            ttot += thold
            segarb_rows.append(hold_row)
            next_v = current_v - step_v
            if next_v < start_v:
                next_v = start_v
            rf_row = trans_row_gen(current_v_ch1=current_v, next_v_ch1=next_v, current_v_ch2=bias_v, next_v_ch2=bias_v, trf=trf, trig_enable=0)
            ttot += trf
            segarb_rows.append(rf_row)
            current_v = next_v
        segarb_rows.append(hold_row_gen(vhold_ch1=current_v, vhold_ch2=bias_v, thold=thold, trig_enable=0))
        ttot += thold
    print(f"Total sweep time = {ttot} s")
    return segarb_rows

def pulse_gen(pulse_v_ch1=2, stdby_v_ch1=0, pulse_v_ch2=0, stdby_v_ch2=0, tpulse=1e-3, trf=1e-5, duty_cycle=0.5):
    tperiod = (tpulse+trf)/duty_cycle
    segarb_rows = []
    segarb_rows.append(trans_row_gen(current_v_ch1=stdby_v_ch1, next_v_ch1=pulse_v_ch1, current_v_ch2=stdby_v_ch2, next_v_ch2=pulse_v_ch2, trf=trf, trig_enable=1))
    segarb_rows.append(hold_row_gen(vhold_ch1=pulse_v_ch1, vhold_ch2=pulse_v_ch2, thold=tpulse, trig_enable=0))
    segarb_rows.append(trans_row_gen(current_v_ch1=pulse_v_ch1, next_v_ch1=stdby_v_ch1, current_v_ch2=pulse_v_ch2, next_v_ch2=stdby_v_ch2, trf=trf, trig_enable=0))
    tstdby = round(tperiod - trf - tpulse, 7)
    if tstdby > 0:
        segarb_rows.append(hold_row_gen(vhold_ch1=stdby_v_ch1, vhold_ch2=stdby_v_ch2, thold=tstdby, trig_enable=0))
    return segarb_rows

def my_fast_staircase_ramp_gen_idvg(start_vg=0, stop_vg=2, step_vg=0.1, bias_vd=0.1, trf=1e-6, thold=1e-5):
    segarb_rows = []
    segarb_rows.append(initial_row_gen(thold=thold, trig_enable=1))
    segarb_rows.append(zero_to_init_row_gen(init_v_ch1=start_vg, init_v_ch2=bias_vd, trf=trf, trig_enable=0))
    segarb_rows += stair_case_ramp_gen(start_v=start_vg, stop_v=stop_vg, step_v=step_vg, bias_v=bias_vd, trf=trf, thold=thold, sweep_mode="double")
    segarb_rows.append(back_to_zero_row_gen(current_v_ch1=start_vg, current_v_ch2=bias_vd, trf=trf, trig_enable=0))
    segarb_rows.append(finish_row_gen(thold=thold, trig_enable=0))
    return segarb_rows

def my_pulse_gen_stress(pulse_vg=2, stdby_vg=0, pulse_vd=0.1, stdby_vd=0.1, tdelay=1e-3, tpulse=1e-3, trf=1e-5, duty_cycle=0.5):
    segarb_rows = []
    segarb_rows.append(initial_row_gen(thold=tdelay, trig_enable=1))
    segarb_rows.append(zero_to_init_row_gen(init_v_ch1=stdby_vg, init_v_ch2=stdby_vd, trf=trf, trig_enable=0))
    segarb_rows += pulse_gen(pulse_v_ch1=pulse_vg, stdby_v_ch1=stdby_vg, pulse_v_ch2=pulse_vd, stdby_v_ch2=stdby_vd, tpulse=tpulse, trf=trf, duty_cycle=duty_cycle)
    segarb_rows.append(back_to_zero_row_gen(current_v_ch1=stdby_vg, current_v_ch2=stdby_vd, trf=trf, trig_enable=0))
    segarb_rows.append(finish_row_gen(thold=tdelay, trig_enable=0))
    return segarb_rows

def segarb_rows_to_df(segarb_rows):
    columns = [
        "SegTime (s)",
        "StartVCh1 (V)",
        "StopVCh1 (V)",
        "StartVCh2 (V)",
        "StopVCh2 (V)",
        "SSRCtrlCh1 (0/1)",
        "SSRCtrlCh2 (0/1)",
        "SegTrigOut (0/1)"
    ]
    df = pd.DataFrame(segarb_rows, columns=columns)
    return df

def print_rows(rows):
    # Print the header first
    print(*pmu_segarb_columns, sep='\t')
    # Print each row with tabs as separators
    for row in rows:
        print(*row, sep='\t')

if __name__ == "__main__":
    # Example usage: Generate a stair-case ramp and print the rows
    segarb_rows = stair_case_ramp_gen(start_v=0, stop_v=2, step_v=0.1, bias_v=0.1, trf=1e-6, thold=1e-5, sweep_mode="double")
    print_rows(segarb_rows)

    # Example usage: Generate a pulse and print the rows
    pulse_rows = pulse_gen(pulse_v_ch1=2, stdby_v_ch1=0, pulse_v_ch2=0, stdby_v_ch2=0, tpulse=1e-3, trf=1e-5, duty_cycle=0.5)
    print_rows(pulse_rows)

    # Example usage: Generate a fast stair-case ramp for Id-Vg measurement and print the rows
    fast_ramp_rows = my_fast_staircase_ramp_gen_idvg(start_vg=0, stop_vg=2, step_vg=0.1, bias_vd=0.1, trf=1e-6, thold=1e-5)
    print_rows(fast_ramp_rows)

    # Example usage: Convert segarb rows to a DataFrame
    df = segarb_rows_to_df(segarb_rows=fast_ramp_rows)

    # Print the DataFrame
    print(df)

    # Example usage: Generate a pulse for stress testing and print the rows
    pulse_stress_rows = my_pulse_gen_stress(pulse_vg=2, stdby_vg=0, pulse_vd=0.1, stdby_vd=0.1, tdelay=1e-3, tpulse=1e-3, trf=1e-5, duty_cycle=0.5)
    print_rows(pulse_stress_rows)