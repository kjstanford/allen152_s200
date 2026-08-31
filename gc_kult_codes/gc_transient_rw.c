/* USRLIB MODULE INFORMATION

    MODULE NAME: gc_transient_rw
    MODULE RETURN TYPE: int
    NUMBER OF PARMS: 28
    ARGUMENTS:
        vhold,          double, Input,  0.0,   -40.0,  40.0
        vboost,         double, Input,  2.0,   -40.0,  40.0
        vdata0,         double, Input,  0.0,   -40.0,  40.0
        vdata1,         double, Input,  1.0,   -40.0,  40.0
        vss,            double, Input,  0.0,   -40.0,  40.0
        vdd,            double, Input,  1.0,   -40.0,  40.0
        tdelay,         double, Input,  1e-6,  0.0,    40.0
        trf,            double, Input,  100e-9,20e-9,  40.0
        twrite,         double, Input,  1e-6,  20e-9,  40.0
        thold,          double, Input,  1e-6,  0.0,    40.0
        tread,          double, Input,  1e-6,  20e-9,  40.0
        n,              int,    Input,  10,    1,      10000
        sample_rate,    double, Input,  1e8,   1.0,    2e8
        voltage_range,  double, Input,  10.0,  10.0,   40.0
        current_range,  double, Input,  1e-3,  100e-9, 0.8
        dut_resistance, double, Input,  1e6,   1.0,    1e6
        PMU_ID1,        char *, Input,  "PMU1", ,
        PMU_ID2,        char *, Input,  "PMU2", ,
        WWL_V,          D_ARRAY_T, Output, , ,
        WWL_V_size,     int, Input,  30000, 100, 30000
        WBL_V,          D_ARRAY_T, Output, , ,
        WBL_V_size,     int, Input,  30000, 100, 30000
        RWL_V,          D_ARRAY_T, Output, , ,
        RWL_V_size,     int, Input,  30000, 100, 30000
        RBL_I,          D_ARRAY_T, Output, , ,
        RBL_I_size,     int, Input,  30000, 100, 30000
        Time,           D_ARRAY_T, Output, , ,
        Time_size,      int, Input,  30000, 100, 30000
    INCLUDES:
#include "keithley.h"
#include <math.h>
    END USRLIB MODULE INFORMATION
*/

/* USRLIB MODULE HELP DESCRIPTION
<!--MarkdownExtra-->
<link rel="stylesheet" type="text/css"
href="http://clariusweb/HelpPane/stylesheet.css">

GC alternating write/read transient
===================================

Description
-----------

Executes an alternating gain-cell transient measurement using two
4225-PMU cards:

* WWL: PMU1 channel 1
* WBL: PMU1 channel 2
* RWL: PMU2 channel 1
* RBL: PMU2 channel 2

After one initial `tdelay`, the following cycle is repeated `n` times:

1. Write data 1: WBL transitions to `vdata1` while WWL pulses from
   `vhold` to `vboost`.
2. Hold for `thold`, then pulse RWL from `vss` to `vdd` to read data 1.
3. Hold for `thold`.
4. Write data 0: WBL transitions to `vdata0` while WWL pulses from
   `vhold` to `vboost`.
5. Hold for `thold`, then pulse RWL from `vss` to `vdd` to read data 0.
6. Hold for `thold` before the next cycle.

WWL and WBL transitions have rise/fall time `trf`. Each WWL high level
lasts `twrite`; each RWL high level lasts `tread`. RBL remains at `vss`.
Its current is sampled throughout the complete waveform.

Use `tdelay = 0` to omit the initial delay. A nonzero `tdelay` must be at
least 60 ns because the delay is represented by the three-segment minimum
required for a Segment ARB sequence.

Outputs
-------

`WWL_V`, `WBL_V`, `RWL_V`
: Measured terminal voltages.

`RBL_I`
: Measured RBL current.

`Time`
: Shared synchronized measurement timestamps in seconds.

Return values
-------------

`0`
: Measurement completed successfully.

Negative value
: Local parameter or waveform validation error.

Other nonzero value
: Error returned by a Keithley LPT/PMU function.

    END USRLIB MODULE HELP DESCRIPTION
*/

/* USRLIB MODULE PARAMETER LIST */

#include "keithley.h"
#include <math.h>

#define GC_MAX_BREAKPOINTS 20
#define GC_MAX_SEGMENTS (GC_MAX_BREAKPOINTS - 1)

static double gc_pulse_value(
    double t,
    double low_value,
    double high_value,
    double t0,
    double rise,
    double high_time,
    double fall);

static double gc_two_pulse_value(
    double t,
    double low_value,
    double high_value,
    double first_t0,
    double second_t0,
    double rise,
    double high_time,
    double fall);

static double gc_data_value(
    double t,
    double vdata0,
    double vdata1,
    double write1_start,
    double write0_start,
    double transition_time);

static void gc_add_time(double *times, int *count, double value);
static void gc_sort_times(double *times, int count);


/* USRLIB MODULE MAIN FUNCTION */
int gc_transient_rw( double vhold, double vboost, double vdata0, double vdata1, double vss, double vdd, double tdelay, double trf, double twrite, double thold, double tread, int n, double sample_rate, double voltage_range, double current_range, double dut_resistance, char *PMU_ID1, char *PMU_ID2, double *WWL_V, int WWL_V_size, double *WBL_V, int WBL_V_size, double *RWL_V, int RWL_V_size, double *RBL_I, int RBL_I_size, double *Time, int Time_size )
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

    /* Optional three-segment prefix used to apply tdelay only once. */
    double prefix_time[3];
    double prefix_wwl_start[3];
    double prefix_wwl_stop[3];
    double prefix_wbl_start[3];
    double prefix_wbl_stop[3];
    double prefix_rwl_start[3];
    double prefix_rwl_stop[3];
    double prefix_rbl_start[3];
    double prefix_rbl_stop[3];
    long prefix_trigger[3];
    long prefix_ssr[3];
    unsigned long prefix_measure_type[3];
    double prefix_measure_start[3];
    double prefix_measure_stop[3];

    long sequence_list[2];
    double sequence_loops[2];

    int pmu1;
    int pmu2;
    int status;
    int point_count = 0;
    int segment_count;
    int waveform_sequence_count;
    int cycle_sequence_number;
    int i;
    double elapsed_time;
    double expected_points;
    double total_time;

    double write1_start;
    double write1_rise_end;
    double write1_high_end;
    double write1_end;

    double read1_start;
    double read1_rise_end;
    double read1_high_end;
    double read1_end;

    double write0_start;
    double write0_rise_end;
    double write0_high_end;
    double write0_end;

    double read0_start;
    double read0_rise_end;
    double read0_high_end;
    double read0_end;
    double cycle_time;

    /* Segment ARB durations must be zero (omitted) or at least 20 ns. */
    if (trf < 20e-9 || twrite < 20e-9 || tread < 20e-9 ||
        tdelay < 0.0 || thold < 0.0 ||
        (tdelay > 0.0 && tdelay < 60e-9) ||
        (thold > 0.0 && thold < 20e-9))
    {
        printf("gc_transient_rw: invalid timing parameter.");
        return -1;
    }

    if (n < 1)
    {
        printf("gc_transient_rw: n must be at least 1.");
        return -2;
    }

    if (sample_rate <= 0.0 || sample_rate > 200e6)
    {
        printf("gc_transient_rw: sample_rate must be > 0 and <= 200e6.");
        return -3;
    }

    /*
     * Construct one complete write-1/read-1/write-0/read-0 cycle.
     * The sequence begins and ends at WBL=vdata0, so it can loop
     * seamlessly. The initial delay is kept in a separate sequence.
     */
    write1_start    = 0.0;
    write1_rise_end = write1_start + trf;
    write1_high_end = write1_rise_end + twrite;
    write1_end      = write1_high_end + trf;

    read1_start     = write1_end + thold;
    read1_rise_end  = read1_start + trf;
    read1_high_end  = read1_rise_end + tread;
    read1_end       = read1_high_end + trf;

    write0_start    = read1_end + thold;
    write0_rise_end = write0_start + trf;
    write0_high_end = write0_rise_end + twrite;
    write0_end      = write0_high_end + trf;

    read0_start     = write0_end + thold;
    read0_rise_end  = read0_start + trf;
    read0_high_end  = read0_rise_end + tread;
    read0_end       = read0_high_end + trf;
    cycle_time      = read0_end + thold;

    gc_add_time(breakpoints, &point_count, 0.0);
    gc_add_time(breakpoints, &point_count, write1_rise_end);
    gc_add_time(breakpoints, &point_count, write1_high_end);
    gc_add_time(breakpoints, &point_count, write1_end);
    gc_add_time(breakpoints, &point_count, read1_start);
    gc_add_time(breakpoints, &point_count, read1_rise_end);
    gc_add_time(breakpoints, &point_count, read1_high_end);
    gc_add_time(breakpoints, &point_count, read1_end);
    gc_add_time(breakpoints, &point_count, write0_start);
    gc_add_time(breakpoints, &point_count, write0_rise_end);
    gc_add_time(breakpoints, &point_count, write0_high_end);
    gc_add_time(breakpoints, &point_count, write0_end);
    gc_add_time(breakpoints, &point_count, read0_start);
    gc_add_time(breakpoints, &point_count, read0_rise_end);
    gc_add_time(breakpoints, &point_count, read0_high_end);
    gc_add_time(breakpoints, &point_count, read0_end);
    gc_add_time(breakpoints, &point_count, cycle_time);

    gc_sort_times(breakpoints, point_count);
    segment_count = point_count - 1;

    if (segment_count < 8 || segment_count > GC_MAX_SEGMENTS)
    {
        printf("gc_transient_rw: invalid Segment ARB segment count.");
        return -4;
    }

    total_time = tdelay + (double)n * cycle_time;
    expected_points = ceil(total_time * sample_rate) + 2.0;

    if (expected_points > (double)WWL_V_size ||
        expected_points > (double)WBL_V_size ||
        expected_points > (double)RWL_V_size ||
        expected_points > (double)RBL_I_size ||
        expected_points > (double)Time_size)
    {
        printf(
            "gc_transient_rw: output arrays are too small; "
            "need approximately %.0f points.",
            expected_points);
        return -5;
    }

    /* Evaluate all four channel values at every common boundary. */
    for (i = 0; i < segment_count; ++i)
    {
        double t0 = breakpoints[i];
        double t1 = breakpoints[i + 1];

        segment_time[i] = t1 - t0;

        if (segment_time[i] < 20e-9)
        {
            printf(
                "gc_transient_rw: segment %d is shorter than 20 ns.",
                i + 1);
            return -6;
        }

        wwl_start[i] = gc_two_pulse_value(
            t0, vhold, vboost, write1_start, write0_start,
            trf, twrite, trf);
        wwl_stop[i] = gc_two_pulse_value(
            t1, vhold, vboost, write1_start, write0_start,
            trf, twrite, trf);

        wbl_start[i] = gc_data_value(
            t0, vdata0, vdata1, write1_start, write0_start, trf);
        wbl_stop[i] = gc_data_value(
            t1, vdata0, vdata1, write1_start, write0_start, trf);

        rwl_start[i] = gc_two_pulse_value(
            t0, vss, vdd, read1_start, read0_start,
            trf, tread, trf);
        rwl_stop[i] = gc_two_pulse_value(
            t1, vss, vdd, read1_start, read0_start,
            trf, tread, trf);

        rbl_start[i] = vss;
        rbl_stop[i] = vss;

        trigger_out[i] = (i == 0) ? 1 : 0;
        wwl_ssr[i] = 1;
        wbl_ssr[i] = 1;
        rwl_ssr[i] = 1;
        rbl_ssr[i] = 1;
        measure_type[i] = PULSE_MEAS_WFM_PER;
        measure_start[i] = 0.0;
        measure_stop[i] = segment_time[i];
    }

    /*
     * Values for the optional, measured initial-delay sequence. The LPT
     * API requires every sequence to contain at least three segments.
     */
    prefix_time[0] = 20e-9;
    prefix_time[1] = 20e-9;
    prefix_time[2] = (tdelay > 0.0) ? tdelay - 40e-9 : 20e-9;

    for (i = 0; i < 3; ++i)
    {
        prefix_wwl_start[i] = vhold;
        prefix_wwl_stop[i] = vhold;
        prefix_wbl_start[i] = vdata0;
        prefix_wbl_stop[i] = vdata0;
        prefix_rwl_start[i] = vss;
        prefix_rwl_stop[i] = vss;
        prefix_rbl_start[i] = vss;
        prefix_rbl_stop[i] = vss;
        prefix_trigger[i] = (i == 0) ? 1 : 0;
        prefix_ssr[i] = 1;
        prefix_measure_type[i] = PULSE_MEAS_WFM_PER;
        prefix_measure_start[i] = 0.0;
        prefix_measure_stop[i] = prefix_time[i];
    }

    getinstid(PMU_ID1, &pmu1);
    getinstid(PMU_ID2, &pmu2);

    if (pmu1 == -1 || pmu2 == -1)
    {
        printf(
            "gc_transient_rw: cannot find %s and/or %s.",
            PMU_ID1, PMU_ID2);
        return -7;
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

    /*
     * Sequence 1 is the initial delay when tdelay is nonzero. In that
     * case sequence 2 is the repeating cycle. With no delay, sequence 1
     * is the repeating cycle.
     */
    if (tdelay > 0.0)
    {
        status = seg_arb_sequence(
            pmu1, 1, 1, 3,
            prefix_wwl_start, prefix_wwl_stop, prefix_time,
            prefix_trigger, prefix_ssr, prefix_measure_type,
            prefix_measure_start, prefix_measure_stop);
        if (status) return status;
        status = seg_arb_sequence(
            pmu1, 2, 1, 3,
            prefix_wbl_start, prefix_wbl_stop, prefix_time,
            prefix_trigger, prefix_ssr, prefix_measure_type,
            prefix_measure_start, prefix_measure_stop);
        if (status) return status;
        status = seg_arb_sequence(
            pmu2, 1, 1, 3,
            prefix_rwl_start, prefix_rwl_stop, prefix_time,
            prefix_trigger, prefix_ssr, prefix_measure_type,
            prefix_measure_start, prefix_measure_stop);
        if (status) return status;
        status = seg_arb_sequence(
            pmu2, 2, 1, 3,
            prefix_rbl_start, prefix_rbl_stop, prefix_time,
            prefix_trigger, prefix_ssr, prefix_measure_type,
            prefix_measure_start, prefix_measure_stop);
        if (status) return status;

        cycle_sequence_number = 2;
        waveform_sequence_count = 2;
        sequence_list[0] = 1;
        sequence_loops[0] = 1.0;
        sequence_list[1] = 2;
        sequence_loops[1] = (double)n;
    }
    else
    {
        cycle_sequence_number = 1;
        waveform_sequence_count = 1;
        sequence_list[0] = 1;
        sequence_loops[0] = (double)n;
    }

    status = seg_arb_sequence(
        pmu1, 1, cycle_sequence_number, segment_count,
        wwl_start, wwl_stop, segment_time,
        trigger_out, wwl_ssr, measure_type,
        measure_start, measure_stop);
    if (status) return status;
    status = seg_arb_sequence(
        pmu1, 2, cycle_sequence_number, segment_count,
        wbl_start, wbl_stop, segment_time,
        trigger_out, wbl_ssr, measure_type,
        measure_start, measure_stop);
    if (status) return status;
    status = seg_arb_sequence(
        pmu2, 1, cycle_sequence_number, segment_count,
        rwl_start, rwl_stop, segment_time,
        trigger_out, rwl_ssr, measure_type,
        measure_start, measure_stop);
    if (status) return status;
    status = seg_arb_sequence(
        pmu2, 2, cycle_sequence_number, segment_count,
        rbl_start, rbl_stop, segment_time,
        trigger_out, rbl_ssr, measure_type,
        measure_start, measure_stop);
    if (status) return status;

    status = seg_arb_waveform(
        pmu1, 1, waveform_sequence_count,
        sequence_list, sequence_loops);
    if (status) return status;
    status = seg_arb_waveform(
        pmu1, 2, waveform_sequence_count,
        sequence_list, sequence_loops);
    if (status) return status;
    status = seg_arb_waveform(
        pmu2, 1, waveform_sequence_count,
        sequence_list, sequence_loops);
    if (status) return status;
    status = seg_arb_waveform(
        pmu2, 2, waveform_sequence_count,
        sequence_list, sequence_loops);
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
}       /* End gc_transient_rw.c */


/* Return a piecewise-linear pulse value. */
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


/* Return the value of either of two nonoverlapping identical pulses. */
static double gc_two_pulse_value(
    double t,
    double low_value,
    double high_value,
    double first_t0,
    double second_t0,
    double rise,
    double high_time,
    double fall)
{
    double first_end = first_t0 + rise + high_time + fall;

    if (t <= first_end)
    {
        return gc_pulse_value(
            t, low_value, high_value, first_t0,
            rise, high_time, fall);
    }

    return gc_pulse_value(
        t, low_value, high_value, second_t0,
        rise, high_time, fall);
}


/* WBL changes to data 1 for the first write and data 0 for the second. */
static double gc_data_value(
    double t,
    double vdata0,
    double vdata1,
    double write1_start,
    double write0_start,
    double transition_time)
{
    double write1_end = write1_start + transition_time;
    double write0_end = write0_start + transition_time;

    if (t <= write1_start)
        return vdata0;

    if (t < write1_end)
    {
        return vdata0 +
               (vdata1 - vdata0) *
               (t - write1_start) / transition_time;
    }

    if (t <= write0_start)
        return vdata1;

    if (t < write0_end)
    {
        return vdata1 +
               (vdata0 - vdata1) *
               (t - write0_start) / transition_time;
    }

    return vdata0;
}


/* Add a breakpoint if it is not already present. */
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


/* Sort waveform breakpoints into ascending order. */
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
