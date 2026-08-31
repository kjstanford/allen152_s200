/* USRLIB MODULE INFORMATION

    MODULE NAME: gc_retention
    MODULE RETURN TYPE: int
    NUMBER OF PARMS: 31
    ARGUMENTS:
        vhold,                double, Input,  0.0,   -40.0,  40.0
        vboost,               double, Input,  2.0,   -40.0,  40.0
        vdata0,               double, Input,  0.0,   -40.0,  40.0
        vdata1,               double, Input,  1.0,   -40.0,  40.0
        vss,                  double, Input,  0.0,   -40.0,  40.0
        vdd,                  double, Input,  1.0,   -40.0,  40.0
        tdelay,               double, Input,  1e-6,  0.0,    40.0
        trf,                  double, Input,  100e-9,20e-9,  40.0
        twrite,               double, Input,  1e-6,  20e-9,  40.0
        tread,                double, Input,  1e-6,  20e-9,  40.0
        measure_start_fraction,double,Input,  0.2,   0.0,    1.0
        measure_stop_fraction,double, Input,  0.8,   0.0,    1.0
        state,                int,    Input,  1,     0,      1
        retention_times,      D_ARRAY_T, Input, , ,
        retention_times_size, int,    Input,  10,    1,      256
        sample_rate,          double, Input,  1e8,   1.0,    2e8
        voltage_range,        double, Input,  10.0,  10.0,   40.0
        current_range,        double, Input,  1e-3,  100e-9, 0.8
        dut_resistance,       double, Input,  1e6,   1.0,    1e6
        PMU_ID1,              char *, Input,  "PMU1", ,
        PMU_ID2,              char *, Input,  "PMU2", ,
        WWL_V,                D_ARRAY_T, Output, , ,
        WWL_V_size,           int, Input,  30000, 100, 30000
        WBL_V,                D_ARRAY_T, Output, , ,
        WBL_V_size,           int, Input,  30000, 100, 30000
        RWL_V,                D_ARRAY_T, Output, , ,
        RWL_V_size,           int, Input,  30000, 100, 30000
        RBL_I,                D_ARRAY_T, Output, , ,
        RBL_I_size,           int, Input,  30000, 100, 30000
        Time,                 D_ARRAY_T, Output, , ,
        Time_size,            int, Input,  30000, 100, 30000
    INCLUDES:
#include "keithley.h"
#include <math.h>
    END USRLIB MODULE INFORMATION
*/

/* USRLIB MODULE HELP DESCRIPTION
<!--MarkdownExtra-->
<link rel="stylesheet" type="text/css"
href="http://clariusweb/HelpPane/stylesheet.css">

GC retention measurement
========================

Description
-----------

Writes one gain-cell state and reads it at a list of cumulative retention
times using two 4225-PMU cards:

* WWL: PMU1 channel 1
* WBL: PMU1 channel 2
* RWL: PMU2 channel 1
* RBL: PMU2 channel 2

For `state = 1`, WBL pulses from `vdata0` to `vdata1` and returns to
`vdata0`. For `state = 0`, WBL pulses from `vdata1` to `vdata0` and
returns to `vdata1`. Thus, after the write, WBL is held at the voltage
opposite to the written state.

The write WWL pulse has a high-level duration of `twrite`. The WBL data
level lasts `twrite + 2*trf`, so WBL returns to the opposite voltage
exactly `2*trf` after WWL returns to `vhold`.

Each element of `retention_times` is a cumulative time in seconds,
measured from the end of that WBL return. At each requested time, RWL
pulses from `vss` to `vdd`, remains high for `tread`, and returns to
`vss`. The times must be nonnegative and ordered so read pulses do not
overlap. `retention_times_size` is the number of requested reads.

One spot-mean value is returned for each read. The averaging window lies
within the flat RWL-high interval and is selected by
`measure_start_fraction` and `measure_stop_fraction`. For example, values
of 0.2 and 0.8 average from 20% through 80% of `tread`. The fractions must
satisfy `0 <= start < stop <= 1`. Long unmeasured retention intervals do
not fill the PMU data buffer.

Outputs
-------

`WWL_V`, `WBL_V`, `RWL_V`
: Spot-mean terminal voltages for every RWL-high read window.

`RBL_I`
: Spot-mean RBL current for every RWL-high read window.

`Time`
: Absolute synchronized PMU timestamps. Subtract the write/initial-delay
  offset if retention-relative timestamps are required.

Return values
-------------

`0`
: Measurement completed successfully.

Negative value
: Local parameter, retention-list, waveform, or array validation error.

Other nonzero value
: Error returned by a Keithley LPT/PMU function.

    END USRLIB MODULE HELP DESCRIPTION
*/

/* USRLIB MODULE PARAMETER LIST */

#include "keithley.h"
#include <math.h>

#define GC_MAX_RETENTION_POINTS 256
#define GC_MAX_BREAKPOINTS (8 + 4 * GC_MAX_RETENTION_POINTS)
#define GC_MAX_SEGMENTS (GC_MAX_BREAKPOINTS - 1)
#define GC_MEAS_SPOT_MEAN_DISCRETE 1UL

static double gc_pulse_value(
    double t,
    double low_value,
    double high_value,
    double t0,
    double rise,
    double high_time,
    double fall);

static double gc_read_value(
    double t,
    double low_value,
    double high_value,
    double retention_origin,
    double *retention_times,
    int retention_count,
    double rise,
    double high_time,
    double fall);

static int gc_is_read_high_segment(
    double segment_start,
    double segment_stop,
    double retention_origin,
    double *retention_times,
    int retention_count,
    double rise,
    double high_time);

static void gc_add_time(double *times, int *count, double value);
static void gc_sort_times(double *times, int count);


/* USRLIB MODULE MAIN FUNCTION */
int gc_retention( double vhold, double vboost, double vdata0, double vdata1, double vss, double vdd, double tdelay, double trf, double twrite, double tread, double measure_start_fraction, double measure_stop_fraction, int state, double *retention_times, int retention_times_size, double sample_rate, double voltage_range, double current_range, double dut_resistance, char *PMU_ID1, char *PMU_ID2, double *WWL_V, int WWL_V_size, double *WBL_V, int WBL_V_size, double *RWL_V, int RWL_V_size, double *RBL_I, int RBL_I_size, double *Time, int Time_size )
{
/* USRLIB MODULE CODE */

    double breakpoints[GC_MAX_BREAKPOINTS];
    double segment_time[GC_MAX_SEGMENTS];

    double wwl_start[GC_MAX_SEGMENTS];
    double wwl_stop[GC_MAX_SEGMENTS];
    double wbl_start[GC_MAX_SEGMENTS];
    double wbl_stop[GC_MAX_SEGMENTS];
    double rwl_start[GC_MAX_SEGMENTS];
    double rwl_stop[GC_MAX_SEGMENTS];
    double rbl_start[GC_MAX_SEGMENTS];
    double rbl_stop[GC_MAX_SEGMENTS];

    long trigger_out[GC_MAX_SEGMENTS];
    long wwl_ssr[GC_MAX_SEGMENTS];
    long wbl_ssr[GC_MAX_SEGMENTS];
    long rwl_ssr[GC_MAX_SEGMENTS];
    long rbl_ssr[GC_MAX_SEGMENTS];
    unsigned long measure_type[GC_MAX_SEGMENTS];
    double measure_start[GC_MAX_SEGMENTS];
    double measure_stop[GC_MAX_SEGMENTS];

    long sequence_list[1] = {1};
    double sequence_loops[1] = {1.0};

    int pmu1;
    int pmu2;
    int status;
    int point_count = 0;
    int segment_count;
    int i;
    double elapsed_time;
    double expected_points;
    double gap;
    double measure_window;

    double write_start;
    double wwl_rise_end;
    double wwl_high_end;
    double wwl_end;
    double wbl_high_end;
    double retention_origin;
    double total_time;
    double wbl_base;
    double wbl_data;

    if (!(trf >= 20e-9) || !(twrite >= 20e-9) ||
        !(tread >= 20e-9) || !(tdelay >= 0.0) ||
        (tdelay > 0.0 && tdelay < 20e-9))
    {
        printf("gc_retention: invalid timing parameter.");
        return -1;
    }

    if (state != 0 && state != 1)
    {
        printf("gc_retention: state must be 0 or 1.");
        return -2;
    }

    if (retention_times == NULL || retention_times_size < 1 ||
        retention_times_size > GC_MAX_RETENTION_POINTS)
    {
        printf(
            "gc_retention: retention_times must contain 1 to %d values.",
            GC_MAX_RETENTION_POINTS);
        return -3;
    }

    if (!(sample_rate > 0.0) || sample_rate > 200e6)
    {
        printf("gc_retention: sample_rate must be > 0 and <= 200e6.");
        return -4;
    }

    if (!(measure_start_fraction >= 0.0) ||
        !(measure_stop_fraction <= 1.0) ||
        !(measure_start_fraction < measure_stop_fraction))
    {
        printf(
            "gc_retention: measurement fractions must satisfy "
            "0 <= start < stop <= 1.");
        return -4;
    }

    measure_window =
        (measure_stop_fraction - measure_start_fraction) * tread;

    if (measure_window < 10e-9 || measure_window * sample_rate < 1.0)
    {
        printf(
            "gc_retention: spot-mean window must be at least 10 ns "
            "and contain at least one sample.");
        return -4;
    }

    /*
     * Validate cumulative read-start times. A zero gap is allowed, but
     * any nonzero Segment ARB hold segment must be at least 20 ns.
     */
    for (i = 0; i < retention_times_size; ++i)
    {
        if (!(retention_times[i] >= 0.0) ||
            retention_times[i] - retention_times[i] != 0.0)
        {
            printf(
                "gc_retention: retention_times[%d] is invalid.", i);
            return -5;
        }

        if (i == 0)
        {
            gap = retention_times[0];
        }
        else
        {
            gap = retention_times[i] - retention_times[i - 1] -
                  (2.0 * trf + tread);
        }

        if (gap < -1e-15 || (gap > 1e-15 && gap < 20e-9))
        {
            printf(
                "gc_retention: read %d overlaps the previous event or "
                "creates a hold shorter than 20 ns.",
                i + 1);
            return -5;
        }
    }

    write_start     = tdelay;
    wwl_rise_end    = write_start + trf;
    wwl_high_end    = wwl_rise_end + twrite;
    wwl_end         = wwl_high_end + trf;
    wbl_high_end    = wwl_rise_end + twrite + 2.0 * trf;
    retention_origin = wbl_high_end + trf;

    wbl_base = (state == 1) ? vdata0 : vdata1;
    wbl_data = (state == 1) ? vdata1 : vdata0;

    total_time = retention_origin +
                 retention_times[retention_times_size - 1] +
                 2.0 * trf + tread;

    gc_add_time(breakpoints, &point_count, 0.0);
    gc_add_time(breakpoints, &point_count, write_start);
    gc_add_time(breakpoints, &point_count, wwl_rise_end);
    gc_add_time(breakpoints, &point_count, wwl_high_end);
    gc_add_time(breakpoints, &point_count, wwl_end);
    gc_add_time(breakpoints, &point_count, wbl_high_end);
    gc_add_time(breakpoints, &point_count, retention_origin);

    for (i = 0; i < retention_times_size; ++i)
    {
        double read_start = retention_origin + retention_times[i];
        double read_rise_end = read_start + trf;
        double read_high_end = read_rise_end + tread;
        double read_end = read_high_end + trf;

        gc_add_time(breakpoints, &point_count, read_start);
        gc_add_time(breakpoints, &point_count, read_rise_end);
        gc_add_time(breakpoints, &point_count, read_high_end);
        gc_add_time(breakpoints, &point_count, read_end);
    }

    gc_add_time(breakpoints, &point_count, total_time);
    gc_sort_times(breakpoints, point_count);
    segment_count = point_count - 1;

    if (segment_count < 3 || segment_count > GC_MAX_SEGMENTS ||
        segment_count > 2048)
    {
        printf("gc_retention: invalid Segment ARB segment count.");
        return -6;
    }

    /* Spot mean returns exactly one averaged value for each read. */
    expected_points = (double)retention_times_size;

    if (expected_points > (double)WWL_V_size ||
        expected_points > (double)WBL_V_size ||
        expected_points > (double)RWL_V_size ||
        expected_points > (double)RBL_I_size ||
        expected_points > (double)Time_size)
    {
        printf(
            "gc_retention: output arrays are too small; "
            "need approximately %.0f points.",
            expected_points);
        return -7;
    }

    for (i = 0; i < segment_count; ++i)
    {
        double t0 = breakpoints[i];
        double t1 = breakpoints[i + 1];

        segment_time[i] = t1 - t0;

        if (segment_time[i] < 20e-9)
        {
            printf(
                "gc_retention: segment %d is shorter than 20 ns.",
                i + 1);
            return -8;
        }

        wwl_start[i] = gc_pulse_value(
            t0, vhold, vboost, write_start, trf, twrite, trf);
        wwl_stop[i] = gc_pulse_value(
            t1, vhold, vboost, write_start, trf, twrite, trf);

        wbl_start[i] = gc_pulse_value(
            t0, wbl_base, wbl_data, write_start,
            trf, twrite + 2.0 * trf, trf);
        wbl_stop[i] = gc_pulse_value(
            t1, wbl_base, wbl_data, write_start,
            trf, twrite + 2.0 * trf, trf);

        rwl_start[i] = gc_read_value(
            t0, vss, vdd, retention_origin,
            retention_times, retention_times_size,
            trf, tread, trf);
        rwl_stop[i] = gc_read_value(
            t1, vss, vdd, retention_origin,
            retention_times, retention_times_size,
            trf, tread, trf);

        rbl_start[i] = vss;
        rbl_stop[i] = vss;

        trigger_out[i] = (i == 0) ? 1 : 0;
        wwl_ssr[i] = 1;
        wbl_ssr[i] = 1;
        rwl_ssr[i] = 1;
        rbl_ssr[i] = 1;

        if (gc_is_read_high_segment(
                t0, t1, retention_origin,
                retention_times, retention_times_size,
                trf, tread))
        {
            measure_type[i] = GC_MEAS_SPOT_MEAN_DISCRETE;
            measure_start[i] =
                measure_start_fraction * segment_time[i];
            measure_stop[i] =
                measure_stop_fraction * segment_time[i];
        }
        else
        {
            measure_type[i] = 0;
            measure_start[i] = 0.0;
            measure_stop[i] = 0.0;
        }
    }

    getinstid(PMU_ID1, &pmu1);
    getinstid(PMU_ID2, &pmu2);

    if (pmu1 == -1 || pmu2 == -1)
    {
        printf(
            "gc_retention: cannot find %s and/or %s.",
            PMU_ID1, PMU_ID2);
        return -9;
    }

    status = rpm_config(pmu1, 1, KI_RPM_PATHWAY, KI_RPM_PULSE);
    if (status) return status;
    status = rpm_config(pmu1, 2, KI_RPM_PATHWAY, KI_RPM_PULSE);
    if (status) return status;
    status = rpm_config(pmu2, 1, KI_RPM_PATHWAY, KI_RPM_PULSE);
    if (status) return status;
    status = rpm_config(pmu2, 2, KI_RPM_PATHWAY, KI_RPM_PULSE);
    if (status) return status;

    status = pg2_init(pmu1, PULSE_MODE_SARB);
    if (status) return status;
    status = pg2_init(pmu2, PULSE_MODE_SARB);
    if (status) return status;

    status = setmode(pmu1, KI_LIM_MODE, KI_VALUE);
    if (status) return status;
    status = setmode(pmu2, KI_LIM_MODE, KI_VALUE);
    if (status) return status;

    status = pulse_load(pmu1, 1, dut_resistance);
    if (status) return status;
    status = pulse_load(pmu1, 2, dut_resistance);
    if (status) return status;
    status = pulse_load(pmu2, 1, dut_resistance);
    if (status) return status;
    status = pulse_load(pmu2, 2, dut_resistance);
    if (status) return status;

    status = pulse_ranges(
        pmu1, 1, voltage_range,
        PULSE_MEAS_FIXED, voltage_range,
        PULSE_MEAS_FIXED, current_range);
    if (status) return status;
    status = pulse_ranges(
        pmu1, 2, voltage_range,
        PULSE_MEAS_FIXED, voltage_range,
        PULSE_MEAS_FIXED, current_range);
    if (status) return status;
    status = pulse_ranges(
        pmu2, 1, voltage_range,
        PULSE_MEAS_FIXED, voltage_range,
        PULSE_MEAS_FIXED, current_range);
    if (status) return status;
    status = pulse_ranges(
        pmu2, 2, voltage_range,
        PULSE_MEAS_FIXED, voltage_range,
        PULSE_MEAS_FIXED, current_range);
    if (status) return status;

    status = pulse_sample_rate(pmu1, (long)sample_rate);
    if (status) return status;
    status = pulse_sample_rate(pmu2, (long)sample_rate);
    if (status) return status;

    status = pulse_burst_count(pmu1, 1, 1);
    if (status) return status;
    status = pulse_burst_count(pmu1, 2, 1);
    if (status) return status;
    status = pulse_burst_count(pmu2, 1, 1);
    if (status) return status;
    status = pulse_burst_count(pmu2, 2, 1);
    if (status) return status;

    status = pulse_measrt(pmu1, 1, "WWL_V", "", "Time", NULL);
    if (status) return status;
    status = pulse_measrt(pmu1, 2, "WBL_V", "", "", NULL);
    if (status) return status;
    status = pulse_measrt(pmu2, 1, "RWL_V", "", "", NULL);
    if (status) return status;
    status = pulse_measrt(pmu2, 2, "", "RBL_I", "", NULL);
    if (status) return status;

    status = seg_arb_sequence(
        pmu1, 1, 1, segment_count,
        wwl_start, wwl_stop, segment_time,
        trigger_out, wwl_ssr, measure_type,
        measure_start, measure_stop);
    if (status) return status;
    status = seg_arb_sequence(
        pmu1, 2, 1, segment_count,
        wbl_start, wbl_stop, segment_time,
        trigger_out, wbl_ssr, measure_type,
        measure_start, measure_stop);
    if (status) return status;
    status = seg_arb_sequence(
        pmu2, 1, 1, segment_count,
        rwl_start, rwl_stop, segment_time,
        trigger_out, rwl_ssr, measure_type,
        measure_start, measure_stop);
    if (status) return status;
    status = seg_arb_sequence(
        pmu2, 2, 1, segment_count,
        rbl_start, rbl_stop, segment_time,
        trigger_out, rbl_ssr, measure_type,
        measure_start, measure_stop);
    if (status) return status;

    status = seg_arb_waveform(
        pmu1, 1, 1, sequence_list, sequence_loops);
    if (status) return status;
    status = seg_arb_waveform(
        pmu1, 2, 1, sequence_list, sequence_loops);
    if (status) return status;
    status = seg_arb_waveform(
        pmu2, 1, 1, sequence_list, sequence_loops);
    if (status) return status;
    status = seg_arb_waveform(
        pmu2, 2, 1, sequence_list, sequence_loops);
    if (status) return status;

    status = pulse_output(pmu1, 1, 1);
    if (status) return status;
    status = pulse_output(pmu1, 2, 1);
    if (status) return status;
    status = pulse_output(pmu2, 1, 1);
    if (status) return status;
    status = pulse_output(pmu2, 2, 1);
    if (status) return status;

    status = pulse_exec(PULSE_MODE_SIMPLE);
    if (status) return status;

    while (pulse_exec_status(&elapsed_time) == 1)
        Sleep(10);

    return 0;

/* USRLIB MODULE END */
}       /* End gc_retention.c */


static double gc_pulse_value(
    double t,
    double low_value,
    double high_value,
    double t0,
    double rise,
    double high_time,
    double fall)
{
    double t1 = t0 + rise;
    double t2 = t1 + high_time;
    double t3 = t2 + fall;

    if (t <= t0)
        return low_value;
    if (t < t1)
        return low_value +
               (high_value - low_value) * (t - t0) / rise;
    if (t <= t2)
        return high_value;
    if (t < t3)
        return high_value +
               (low_value - high_value) * (t - t2) / fall;
    return low_value;
}


/* Return RWL for the read pulse that contains t, or vss between reads. */
static double gc_read_value(
    double t,
    double low_value,
    double high_value,
    double retention_origin,
    double *retention_times,
    int retention_count,
    double rise,
    double high_time,
    double fall)
{
    int i;

    for (i = 0; i < retention_count; ++i)
    {
        double read_start = retention_origin + retention_times[i];
        double read_end = read_start + rise + high_time + fall;

        if (t <= read_end)
        {
            return gc_pulse_value(
                t, low_value, high_value, read_start,
                rise, high_time, fall);
        }
    }

    return low_value;
}


/* Identify the high-level segment of any RWL read pulse. */
static int gc_is_read_high_segment(
    double segment_start,
    double segment_stop,
    double retention_origin,
    double *retention_times,
    int retention_count,
    double rise,
    double high_time)
{
    int i;
    const double tolerance = 1e-15;

    for (i = 0; i < retention_count; ++i)
    {
        double high_start = retention_origin + retention_times[i] + rise;
        double high_stop = high_start + high_time;

        if (fabs(segment_start - high_start) < tolerance &&
            fabs(segment_stop - high_stop) < tolerance)
        {
            return 1;
        }
    }

    return 0;
}


static void gc_add_time(double *times, int *count, double value)
{
    int i;
    const double tolerance = 1e-15;

    for (i = 0; i < *count; ++i)
    {
        if (fabs(times[i] - value) < tolerance)
            return;
    }

    times[*count] = value;
    ++(*count);
}


static void gc_sort_times(double *times, int count)
{
    int i;
    int j;
    double temporary;

    for (i = 0; i < count - 1; ++i)
    {
        for (j = i + 1; j < count; ++j)
        {
            if (times[j] < times[i])
            {
                temporary = times[i];
                times[i] = times[j];
                times[j] = temporary;
            }
        }
    }
}
