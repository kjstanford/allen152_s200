/* USRLIB MODULE INFORMATION

    MODULE NAME: gc_initialize
    MODULE RETURN TYPE: int
    NUMBER OF PARMS: 27
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

GC transient measurement
========================

Description
-----------

Executes a four-terminal gain-cell transient measurement using two
4225-PMU cards:

* WWL: PMU1 channel 1
* WBL: PMU1 channel 2
* RWL: PMU2 channel 1
* RBL: PMU2 channel 2

WWL is initialized to `vhold`, WBL to `vdata0`, and RWL/RBL to `vss`.

After `tdelay`, WWL pulses from `vhold` to `vboost`, with rise and fall
time `trf` and high-level duration `twrite`.

WBL pulses from `vdata0` to `vdata1`, with rise and fall time `trf` and
high-level duration `twrite + 2*trf`.

After WWL returns to `vhold` and an additional `thold`, RWL pulses from
`vss` to `vdd`, with rise and fall time `trf` and high-level duration
`tread`.

RBL remains at `vss`. Its voltage and current are sampled throughout the
complete waveform.

Inputs
------

`vhold`
: WWL standby voltage in volts.

`vboost`
: WWL write-pulse voltage in volts.

`vdata0`, `vdata1`
: Initial and pulsed WBL voltages in volts.

`vss`, `vdd`
: Low and high read voltages in volts.

`tdelay`
: Initial delay in seconds.

`trf`
: Rise and fall time in seconds. Use at least 20 ns.

`twrite`
: WWL high-level duration in seconds.

`thold`
: Delay between completion of the WWL pulse and start of the RWL pulse.

`tread`
: RWL high-level duration in seconds.

`sample_rate`
: PMU waveform sample rate in samples per second. Maximum is 200 MS/s.

`voltage_range`
: PMU source and voltage-measure range. Use 10 V or 40 V.

`current_range`
: PMU current-measure range. Valid values depend on whether a 4225-RPM
is installed.

`dut_resistance`
: Approximate DUT/load resistance used for PMU load-line compensation.

Outputs
-------

`WWL_V`
: Measured WWL voltage from PMU1 channel 1.

`WBL_V`
: Measured WBL voltage from PMU1 channel 2.

`RWL_V`
: Measured RWL voltage from PMU2 channel 1.

`RBL_I`
: Measured RBL current from PMU2 channel 2.

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

static double gc_pulse_value(
    double t,
    double low_value,
    double high_value,
    double t0,
    double rise,
    double high_time,
    double fall);

static void gc_add_time(double *times, int *count, double value);
static void gc_sort_times(double *times, int count);


/* USRLIB MODULE MAIN FUNCTION */
int gc_initialize( double vhold, double vboost, double vdata0, double vdata1, double vss, double vdd, double tdelay, double trf, double twrite, double thold, double tread, double sample_rate, double voltage_range, double current_range, double dut_resistance, char *PMU_ID1, char *PMU_ID2, double *WWL_V, int WWL_V_size, double *WBL_V, int WBL_V_size, double *RWL_V, int RWL_V_size, double *RBL_I, int RBL_I_size, double *Time, int Time_size )
{
/* USRLIB MODULE CODE */

    /*
     * A maximum of eleven unique time breakpoints produces ten
     * Segment ARB segments.
     */
    double breakpoints[11];
    double segment_time[10];

    double wwl_start[10];
    double wwl_stop[10];
    double wbl_start[10];
    double wbl_stop[10];
    double rwl_start[10];
    double rwl_stop[10];
    double rbl_start[10];
    double rbl_stop[10];

    long trigger_out[10];
    long wwl_ssr[10];
    long wbl_ssr[10];
    long rwl_ssr[10];
    long rbl_ssr[10];
    unsigned long measure_type[10];
    double measure_start[10];
    double measure_stop[10];

    long sequence_list[1] = {1};
    double sequence_loops[1] = {1.0};

    int pmu1;
    int pmu2;
    int status;
    int point_count = 0;
    int segment_count;
    int i;
    long expected_points;
    double elapsed_time;

    double wwl_rise_start;
    double wwl_rise_end;
    double wwl_high_end;
    double wwl_fall_end;

    double wbl_rise_start;
    double wbl_rise_end;
    double wbl_high_end;
    double wbl_fall_end;

    double rwl_rise_start;
    double rwl_rise_end;
    double rwl_high_end;
    double rwl_fall_end;

    double total_time;

    /*
     * Validate the timing parameters before programming either PMU.
     * Segment ARB segment durations must normally be at least 20 ns.
     */
    if (trf < 20e-9 || twrite < 20e-9 || tread < 20e-9 ||
        tdelay < 0.0 || thold < 0.0)
    {
        printf("gc_initialize: invalid timing parameter.");
        return -1;
    }

    if (sample_rate <= 0.0 || sample_rate > 200e6)
    {
        printf("gc_initialize: sample_rate must be > 0 and <= 200e6.");
        return -2;
    }

    /*
     * Define the requested edge times.
     *
     * WWL:
     *   rise(trf), high(twrite), fall(trf)
     *
     * WBL:
     *   rise(trf), high(twrite + 2*trf), fall(trf)
     *
     * RWL begins thold after the end of the WWL falling edge.
     */
    wwl_rise_start = tdelay;
    wwl_rise_end   = wwl_rise_start + trf;
    wwl_high_end   = wwl_rise_end + twrite;
    wwl_fall_end   = wwl_high_end + trf;

    wbl_rise_start = tdelay;
    wbl_rise_end   = wbl_rise_start + trf;
    wbl_high_end   = wbl_rise_end + twrite + 2.0 * trf;
    wbl_fall_end   = wbl_high_end + trf;

    rwl_rise_start = wwl_fall_end + thold;
    rwl_rise_end   = rwl_rise_start + trf;
    rwl_high_end   = rwl_rise_end + tread;
    rwl_fall_end   = rwl_high_end + trf;

    total_time = (rwl_fall_end > wbl_fall_end)
                   ? rwl_fall_end
                   : wbl_fall_end;

    /*
     * Create the union of all waveform transition times. This allows
     * WBL and RWL transitions to overlap correctly for arbitrary thold.
     */
    gc_add_time(breakpoints, &point_count, 0.0);
    gc_add_time(breakpoints, &point_count, wwl_rise_start);
    gc_add_time(breakpoints, &point_count, wwl_rise_end);
    gc_add_time(breakpoints, &point_count, wwl_high_end);
    gc_add_time(breakpoints, &point_count, wwl_fall_end);
    gc_add_time(breakpoints, &point_count, wbl_high_end);
    gc_add_time(breakpoints, &point_count, wbl_fall_end);
    gc_add_time(breakpoints, &point_count, rwl_rise_start);
    gc_add_time(breakpoints, &point_count, rwl_rise_end);
    gc_add_time(breakpoints, &point_count, rwl_high_end);
    gc_add_time(breakpoints, &point_count, total_time);

    gc_sort_times(breakpoints, point_count);
    segment_count = point_count - 1;

    if (segment_count < 3 || segment_count > 10)
    {
        printf("gc_initialize: invalid Segment ARB segment count.");
        return -3;
    }

    expected_points = (long)(total_time * sample_rate) + 1;

    if (expected_points > WWL_V_size ||
        expected_points > WBL_V_size ||
        expected_points > RWL_V_size ||
        expected_points > RBL_I_size ||
        expected_points > Time_size)
    {
        printf(
            "gc_initialize: output arrays are too small; "
            "need approximately %ld points.",
            expected_points);
        return -4;
    }

    /*
     * Evaluate every signal at each segment boundary. Segment ARB
     * linearly interpolates between the start and stop values.
     */
    for (i = 0; i < segment_count; ++i)
    {
        double t0 = breakpoints[i];
        double t1 = breakpoints[i + 1];

        segment_time[i] = t1 - t0;

        if (segment_time[i] < 20e-9)
        {
            printf(
                "gc_initialize: segment %d is shorter than 20 ns.",
                i + 1);
            return -5;
        }

        wwl_start[i] = gc_pulse_value(
            t0, vhold, vboost, wwl_rise_start,
            trf, twrite, trf);

        wwl_stop[i] = gc_pulse_value(
            t1, vhold, vboost, wwl_rise_start,
            trf, twrite, trf);

        wbl_start[i] = gc_pulse_value(
            t0, vdata0, vdata1, wbl_rise_start,
            trf, twrite + 2.0 * trf, trf);

        wbl_stop[i] = gc_pulse_value(
            t1, vdata0, vdata1, wbl_rise_start,
            trf, twrite + 2.0 * trf, trf);

        rwl_start[i] = gc_pulse_value(
            t0, vss, vdd, rwl_rise_start,
            trf, tread, trf);

        rwl_stop[i] = gc_pulse_value(
            t1, vss, vdd, rwl_rise_start,
            trf, tread, trf);

        rbl_start[i] = vss;
        rbl_stop[i] = vss;

        trigger_out[i] = (i == 0) ? 1 : 0;

        wwl_ssr[i] = 1;
        wbl_ssr[i] = 1;
        rwl_ssr[i] = 1;
        rbl_ssr[i] = 1;

        /*
         * Waveform measurement over 100% of every segment.
         * Requested results are routed to the Clarius sheet below.
         */
        measure_type[i] = PULSE_MEAS_WFM_PER;
        measure_start[i] = 0.0;
        measure_stop[i] = segment_time[i];
    }

    getinstid(PMU_ID1, &pmu1);
    getinstid(PMU_ID2, &pmu2);

    if (pmu1 == -1 || pmu2 == -1)
    {
        printf(
            "gc_initialize: cannot find %s and/or %s.",
            PMU_ID1, PMU_ID2);
        return -6;
    }

    /*
     * Route all four RPM channels to their pulse pathways.
     * This is also valid when no RPM is attached.
     */
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

    /*
     * Configure the assumed DUT impedance and fixed source/measure
     * ranges on all channels.
     */
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

    /*
     * Send the requested measurements directly to the corresponding
     * Clarius output arrays. The names must exactly match the KULT
     * output-parameter names. Only PMU1 channel 1 publishes timestamps.
     */
    status = pulse_measrt(
        pmu1, 1, "WWL_V", "", "Time", NULL);
    if (status) return status;

    status = pulse_measrt(
        pmu1, 2, "WBL_V", "", "", NULL);
    if (status) return status;

    status = pulse_measrt(
        pmu2, 1, "RWL_V", "", "", NULL);
    if (status) return status;

    status = pulse_measrt(
        pmu2, 2, "", "RBL_I", "", NULL);
    if (status) return status;

    /*
     * Define sequence 1 for every channel. All four channels use the
     * same segment durations to ensure internal-bus synchronization.
     */
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

    /*
     * pulse_exec starts every configured PMU through the chassis
     * internal trigger bus, keeping the two cards synchronized.
     */
    status = pulse_exec(PULSE_MODE_SIMPLE);
    if (status) return status;

    while (pulse_exec_status(&elapsed_time) == 1)
        Sleep(10);

    return 0;

/* USRLIB MODULE END */
}       /* End gc_initialize.c */

/*
 * Return a piecewise-linear pulse value.
 *
 * t0        = beginning of rising edge
 * rise      = rise time
 * high_time = time spent at high level
 * fall      = fall time
 */
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
