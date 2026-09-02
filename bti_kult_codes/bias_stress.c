/* USRLIB MODULE INFORMATION

    MODULE NAME: bias_stress
    MODULE RETURN TYPE: int
    NUMBER OF PARMS: 35
    ARGUMENTS:
        trf,                   double, Input,  2e-7,  60e-9, 20.0
        tplateau,              double, Input,  1e-5,  20e-9, 20.0
        vdrain,                double, Input,  0.1,   -40.0, 40.0
        vgate_start,           double, Input,  0.0,   -40.0, 40.0
        vgate_stop,            double, Input,  2.0,   -40.0, 40.0
        vgate_step,            double, Input,  0.1,   1e-6,  40.0
        measure_start_fraction,double, Input,  0.2,   0.0,   1.0
        measure_stop_fraction, double, Input,  0.8,   0.0,   1.0
        stress_mode,           char *, Input,  "DC", ,
        vstress,               double, Input,  2.0,   -40.0, 40.0
        vstdby,                double, Input,  0.0,   -40.0, 40.0
        thigh,                 double, Input,  1e-6,  20e-9, 20.0
        duty_cycle,            double, Input,  0.5,   1e-6,  1.0
        stress_times,          D_ARRAY_T, Input, , ,
        stress_times_size,     int,    Input,  10,    1,     100
        sample_rate,           double, Input,  1e8,   1.0,   2e8
        voltage_range,         double, Input,  10.0,  10.0,  40.0
        current_range,         double, Input,  1e-3,  100e-9,0.8
        dut_resistance,        double, Input,  1e6,   1.0,   1e9
        PMU_ID1,               char *, Input,  "PMU1", ,
        PMU_ID2,               char *, Input,  "PMU2", ,
        Gate_V,                D_ARRAY_T, Output, , ,
        Gate_V_size,           int, Input,  30000, 100, 30000
        Gate_I,                D_ARRAY_T, Output, , ,
        Gate_I_size,           int, Input,  30000, 100, 30000
        Drain_V,               D_ARRAY_T, Output, , ,
        Drain_V_size,          int, Input,  30000, 100, 30000
        Drain_I,               D_ARRAY_T, Output, , ,
        Drain_I_size,          int, Input,  30000, 100, 30000
        Source_V,              D_ARRAY_T, Output, , ,
        Source_V_size,         int, Input,  30000, 100, 30000
        Source_I,              D_ARRAY_T, Output, , ,
        Source_I_size,         int, Input,  30000, 100, 30000
        Time,                  D_ARRAY_T, Output, , ,
        Time_size,             int, Input,  30000, 100, 30000
    INCLUDES:
#include "keithley.h"
#include <math.h>
#include <string.h>
    END USRLIB MODULE INFORMATION
*/

/* USRLIB MODULE HELP DESCRIPTION
<!--MarkdownExtra-->
<link rel="stylesheet" type="text/css"
href="http://clariusweb/HelpPane/stylesheet.css">

BTI measure-stress-measure test
================================

Description
-----------

Runs the measure-stress-measure sequence described in `bti_prompt.pdf`
using three synchronized 4225-PMU channels:

* Gate: PMU1 channel 1
* Drain: PMU1 channel 2
* Source: PMU2 channel 1

One initial measurement is followed by one stress interval and another
measurement for each cumulative value in `stress_times`. If the first
cumulative value is zero, it refers to that initial measurement and does
not create a duplicate measurement.

During measurement, Drain is held at `vdrain`, Source is held at 0 V,
and Gate follows a bidirectional staircase from `vgate_start` through
`vgate_stop` and back to `vgate_start`. `vgate_stop` must be an integer
number of `vgate_step` increments from `vgate_start`. A spot-mean value
is acquired only on each `tplateau` segment. The averaging portion of a
plateau is selected by `measure_start_fraction` and
`measure_stop_fraction`.

For `stress_mode = "DC"`, Gate ramps to `vstress`, remains there for the
exact incremental stress time, and ramps back. Drain and Source remain
at 0 V. Stress time counts only the constant-voltage hold; transition
times and measurements are excluded. Long DC intervals are represented
by looped 60 s blocks, internally made from three 20 s segments.

For `stress_mode = "AC"`, Gate is pulsed between `vstdby` and `vstress`.
Each cycle contains a `trf` rise, a `thigh` high plateau, a `trf` fall,
and a standby plateau. The period is `thigh / duty_cycle`, so the
standby plateau is `period - thigh - 2*trf`. Cumulative stress times are
rounded to the nearest achievable whole-cycle count. Gate transitions
between `vgate_start` and `vstdby` before and after every AC interval.
Drain and Source remain at 0 V during stress.

Every Segment ARB segment is checked against the 20 ns to 20 s hardware
limits. Sequences contain at least three segments, and sequence looping
is used so long stress times do not consume the segment table.

Outputs
-------

`Gate_V`, `Gate_I`, `Drain_V`, `Drain_I`, `Source_V`, `Source_I`
: One spot-mean terminal voltage and current for every staircase
  plateau, including the initial measurement.

`Time`
: Synchronized timestamps returned by PMU1 channel 1.

Return values
-------------

`0`
: Measurement completed successfully.

Negative value
: Local parameter, timing, waveform, or output-array validation error.

Other nonzero value
: Error returned by a Keithley LPT/PMU function.

    END USRLIB MODULE HELP DESCRIPTION
*/

/* USRLIB MODULE PARAMETER LIST */

#include "keithley.h"
#include <math.h>
#include <string.h>

#define BTI_MAX_STRESS_POINTS 100
#define BTI_MAX_SEGMENTS 2048
#define BTI_MAX_WAVEFORM_ENTRIES 512
#define BTI_MEAS_SPOT_MEAN_DISCRETE 1L
#define BTI_TIME_RESOLUTION 10e-9
#define BTI_MIN_SEGMENT_TIME 20e-9
#define BTI_MAX_SEGMENT_TIME 20.0
#define BTI_DC_BLOCK_TIME 60.0
#define BTI_TIME_TOLERANCE 1e-9

static double bti_quantize_time(double value);
static int bti_mode_is(const char *value, const char *wanted);
static int bti_append_segment(
    int *count,
    double *gate_start, double *gate_stop,
    double *drain_start, double *drain_stop,
    double *source_start, double *source_stop,
    double *segment_time, long *trigger_out, long *ssr,
    long *measure_type, double *measure_start, double *measure_stop,
    double gate0, double gate1, double drain0, double drain1,
    double source0, double source1, double duration,
    long meas_type, double meas_start, double meas_stop,
    long trigger);
static int bti_append_hold_chunks(
    int *count,
    double *gate_start, double *gate_stop,
    double *drain_start, double *drain_stop,
    double *source_start, double *source_stop,
    double *segment_time, long *trigger_out, long *ssr,
    long *measure_type, double *measure_start, double *measure_stop,
    double gate, double drain, double source, double duration);
static int bti_make_transition(
    double from_gate, double to_gate, double duration,
    double *gate_start, double *gate_stop,
    double *drain_start, double *drain_stop,
    double *source_start, double *source_stop,
    double *segment_time, long *trigger_out, long *ssr,
    long *measure_type, double *measure_start, double *measure_stop);
static int bti_define_sequence(
    int pmu1, int pmu2, long sequence_number, int segment_count,
    double *gate_start, double *gate_stop,
    double *drain_start, double *drain_stop,
    double *source_start, double *source_stop,
    double *segment_time, long *trigger_out, long *ssr,
    long *measure_type, double *measure_start, double *measure_stop);


/* USRLIB MODULE MAIN FUNCTION */
int bias_stress( double trf, double tplateau, double vdrain, double vgate_start, double vgate_stop, double vgate_step, double measure_start_fraction, double measure_stop_fraction, char *stress_mode, double vstress, double vstdby, double thigh, double duty_cycle, double *stress_times, int stress_times_size, double sample_rate, double voltage_range, double current_range, double dut_resistance, char *PMU_ID1, char *PMU_ID2, double *Gate_V, int Gate_V_size, double *Gate_I, int Gate_I_size, double *Drain_V, int Drain_V_size, double *Drain_I, int Drain_I_size, double *Source_V, int Source_V_size, double *Source_I, int Source_I_size, double *Time, int Time_size )
{
/* USRLIB MODULE CODE */

    double gate_start[BTI_MAX_SEGMENTS];
    double gate_stop[BTI_MAX_SEGMENTS];
    double drain_start[BTI_MAX_SEGMENTS];
    double drain_stop[BTI_MAX_SEGMENTS];
    double source_start[BTI_MAX_SEGMENTS];
    double source_stop[BTI_MAX_SEGMENTS];
    double segment_time[BTI_MAX_SEGMENTS];
    long trigger_out[BTI_MAX_SEGMENTS];
    long ssr[BTI_MAX_SEGMENTS];
    long measure_type[BTI_MAX_SEGMENTS];
    double measure_start[BTI_MAX_SEGMENTS];
    double measure_stop[BTI_MAX_SEGMENTS];

    long waveform_sequences[BTI_MAX_WAVEFORM_ENTRIES];
    double waveform_loops[BTI_MAX_WAVEFORM_ENTRIES];

    int pmu1;
    int pmu2;
    int status;
    int is_dc;
    int is_ac;
    int segment_count;
    int waveform_count;
    int next_sequence;
    int steps;
    int plateau_count;
    int expected_points;
    int initial_measurement_extra;
    int i;
    int j;
    int split_parts;
    double previous_cycle_count;
    double cumulative_cycle_count;
    double direction;
    double span;
    double gate_value;
    double next_gate_value;
    double programmed_trf;
    double programmed_tplateau;
    double programmed_thigh;
    double measurement_start;
    double measurement_stop;
    double measurement_window;
    double previous_stress_time;
    double interval;
    double block_loops;
    double remainder;
    double period;
    double standby_time;
    double elapsed_time;

    if (stress_mode == NULL || PMU_ID1 == NULL || PMU_ID2 == NULL)
    {
        printf("bias_stress: stress mode and PMU IDs must not be NULL.");
        return -1;
    }

    is_dc = bti_mode_is(stress_mode, "DC");
    is_ac = bti_mode_is(stress_mode, "AC");
    if (!is_dc && !is_ac)
    {
        printf("bias_stress: stress_mode must be DC or AC.");
        return -1;
    }

    if (!(trf >= 60e-9) || !(trf <= BTI_MAX_SEGMENT_TIME) ||
        !(tplateau >= BTI_MIN_SEGMENT_TIME) ||
        !(tplateau <= BTI_MAX_SEGMENT_TIME))
    {
        printf("bias_stress: trf must be 60 ns to 20 s and tplateau must be 20 ns to 20 s.");
        return -2;
    }

    if (!(vgate_step > 0.0) || vgate_start == vgate_stop)
    {
        printf("bias_stress: vgate_step must be positive and gate endpoints must differ.");
        return -3;
    }

    span = fabs(vgate_stop - vgate_start);
    steps = (int)floor(span / vgate_step + 0.5);
    if (steps < 1 || fabs(span - steps * vgate_step) >
        1e-9 * (1.0 + span))
    {
        printf("bias_stress: gate span must be an integer multiple of vgate_step.");
        return -3;
    }

    if (4 * steps + 3 > BTI_MAX_SEGMENTS)
    {
        printf("bias_stress: gate staircase requires too many segments.");
        return -3;
    }

    if (!(measure_start_fraction >= 0.0) ||
        !(measure_stop_fraction <= 1.0) ||
        !(measure_start_fraction < measure_stop_fraction))
    {
        printf("bias_stress: measurement fractions must satisfy 0 <= start < stop <= 1.");
        return -4;
    }

    if (stress_times == NULL || stress_times_size < 1 ||
        stress_times_size > BTI_MAX_STRESS_POINTS)
    {
        printf("bias_stress: stress_times must contain 1 to 100 values.");
        return -5;
    }

    if (!(sample_rate > 0.0) || sample_rate > 200e6 ||
        !(dut_resistance > 0.0))
    {
        printf("bias_stress: invalid sample rate or DUT resistance.");
        return -6;
    }

    programmed_trf = bti_quantize_time(trf);
    programmed_tplateau = bti_quantize_time(tplateau);
    programmed_thigh = bti_quantize_time(thigh);
    if (programmed_trf < 60e-9 ||
        programmed_tplateau < BTI_MIN_SEGMENT_TIME)
    {
        printf("bias_stress: timing rounds below a Segment ARB minimum.");
        return -2;
    }

    measurement_start = bti_quantize_time(
        measure_start_fraction * programmed_tplateau);
    measurement_stop = bti_quantize_time(
        measure_stop_fraction * programmed_tplateau);
    if (measurement_stop > programmed_tplateau)
        measurement_stop = programmed_tplateau;
    measurement_window = measurement_stop - measurement_start;
    if (measurement_window < BTI_TIME_RESOLUTION ||
        measurement_window * sample_rate < 1.0)
    {
        printf("bias_stress: spot-mean window must contain at least one sample and be at least 10 ns.");
        return -4;
    }

    period = 0.0;
    standby_time = 0.0;
    if (is_ac)
    {
        if (!(thigh >= BTI_MIN_SEGMENT_TIME) ||
            !(duty_cycle > 0.0) || !(duty_cycle <= 1.0))
        {
            printf("bias_stress: AC thigh and duty_cycle are invalid.");
            return -7;
        }
        period = bti_quantize_time(programmed_thigh / duty_cycle);
        standby_time = bti_quantize_time(
            period - programmed_thigh - 2.0 * programmed_trf);
        if (standby_time < -BTI_TIME_TOLERANCE ||
            (standby_time > BTI_TIME_TOLERANCE &&
             standby_time < BTI_MIN_SEGMENT_TIME))
        {
            printf("bias_stress: duty cycle leaves an invalid AC standby interval after rise and fall.");
            return -7;
        }
        if (standby_time < BTI_TIME_TOLERANCE)
            standby_time = 0.0;
        period = 2.0 * programmed_trf + programmed_thigh + standby_time;
    }

    previous_stress_time = 0.0;
    previous_cycle_count = 0;
    for (i = 0; i < stress_times_size; ++i)
    {
        if (!(stress_times[i] >= 0.0) ||
            (i > 0 && !(stress_times[i] > previous_stress_time)) ||
            stress_times[i] - stress_times[i] != 0.0)
        {
            printf("bias_stress: stress_times must be finite, nonnegative, and strictly increasing after the optional initial zero.");
            return -5;
        }

        if (is_dc)
        {
            interval = bti_quantize_time(stress_times[i] - previous_stress_time);
            if (interval > BTI_TIME_TOLERANCE && interval < 60e-9)
            {
                printf("bias_stress: every incremental DC stress interval must be at least 60 ns.");
                return -5;
            }
        }
        else
        {
            cumulative_cycle_count =
                floor(stress_times[i] / period + 0.5);
            if (i > 0 && cumulative_cycle_count <= previous_cycle_count)
            {
                printf("bias_stress: adjacent AC stress times round to the same cycle count.");
                return -5;
            }
            previous_cycle_count = cumulative_cycle_count;
        }
        previous_stress_time = stress_times[i];
    }

    plateau_count = 2 * steps + 1;
    /* A leading zero denotes the initial measurement, rather than a
       second copy of the same measurement sequence. */
    initial_measurement_extra =
        (stress_times[0] > BTI_TIME_TOLERANCE) ? 1 : 0;
    expected_points = (stress_times_size + initial_measurement_extra) *
                      plateau_count;
    if (expected_points > Gate_V_size || expected_points > Gate_I_size ||
        expected_points > Drain_V_size || expected_points > Drain_I_size ||
        expected_points > Source_V_size || expected_points > Source_I_size ||
        expected_points > Time_size)
    {
        printf("bias_stress: output arrays are too small; need %d points.", expected_points);
        return -8;
    }

    /* Build sequence 1: drain ramp, bidirectional gate staircase, drain ramp down. */
    segment_count = 0;
    status = bti_append_segment(
        &segment_count, gate_start, gate_stop, drain_start, drain_stop,
        source_start, source_stop, segment_time, trigger_out, ssr,
        measure_type, measure_start, measure_stop,
        vgate_start, vgate_start, 0.0, vdrain, 0.0, 0.0,
        programmed_trf, 0, 0.0, 0.0, 1);
    if (status) return status;

    status = bti_append_segment(
        &segment_count, gate_start, gate_stop, drain_start, drain_stop,
        source_start, source_stop, segment_time, trigger_out, ssr,
        measure_type, measure_start, measure_stop,
        vgate_start, vgate_start, vdrain, vdrain, 0.0, 0.0,
        programmed_tplateau, BTI_MEAS_SPOT_MEAN_DISCRETE,
        measurement_start, measurement_stop, 0);
    if (status) return status;

    direction = (vgate_stop > vgate_start) ? 1.0 : -1.0;
    gate_value = vgate_start;
    for (i = 0; i < steps; ++i)
    {
        next_gate_value = (i == steps - 1)
                            ? vgate_stop
                            : vgate_start + direction * (i + 1) * vgate_step;
        status = bti_append_segment(
            &segment_count, gate_start, gate_stop, drain_start, drain_stop,
            source_start, source_stop, segment_time, trigger_out, ssr,
            measure_type, measure_start, measure_stop,
            gate_value, next_gate_value, vdrain, vdrain, 0.0, 0.0,
            programmed_trf, 0, 0.0, 0.0, 0);
        if (status) return status;
        status = bti_append_segment(
            &segment_count, gate_start, gate_stop, drain_start, drain_stop,
            source_start, source_stop, segment_time, trigger_out, ssr,
            measure_type, measure_start, measure_stop,
            next_gate_value, next_gate_value, vdrain, vdrain, 0.0, 0.0,
            programmed_tplateau, BTI_MEAS_SPOT_MEAN_DISCRETE,
            measurement_start, measurement_stop, 0);
        if (status) return status;
        gate_value = next_gate_value;
    }

    for (i = steps - 1; i >= 0; --i)
    {
        next_gate_value = (i == 0)
                            ? vgate_start
                            : vgate_start + direction * i * vgate_step;
        status = bti_append_segment(
            &segment_count, gate_start, gate_stop, drain_start, drain_stop,
            source_start, source_stop, segment_time, trigger_out, ssr,
            measure_type, measure_start, measure_stop,
            gate_value, next_gate_value, vdrain, vdrain, 0.0, 0.0,
            programmed_trf, 0, 0.0, 0.0, 0);
        if (status) return status;
        status = bti_append_segment(
            &segment_count, gate_start, gate_stop, drain_start, drain_stop,
            source_start, source_stop, segment_time, trigger_out, ssr,
            measure_type, measure_start, measure_stop,
            next_gate_value, next_gate_value, vdrain, vdrain, 0.0, 0.0,
            programmed_tplateau, BTI_MEAS_SPOT_MEAN_DISCRETE,
            measurement_start, measurement_stop, 0);
        if (status) return status;
        gate_value = next_gate_value;
    }

    status = bti_append_segment(
        &segment_count, gate_start, gate_stop, drain_start, drain_stop,
        source_start, source_stop, segment_time, trigger_out, ssr,
        measure_type, measure_start, measure_stop,
        vgate_start, vgate_start, vdrain, 0.0, 0.0, 0.0,
        programmed_trf, 0, 0.0, 0.0, 0);
    if (status) return status;

    getinstid(PMU_ID1, &pmu1);
    getinstid(PMU_ID2, &pmu2);
    if (pmu1 == -1 || pmu2 == -1)
    {
        printf("bias_stress: cannot find %s and/or %s.", PMU_ID1, PMU_ID2);
        return -9;
    }

    status = rpm_config(pmu1, 1, KI_RPM_PATHWAY, KI_RPM_PULSE);
    if (status) return status;
    status = rpm_config(pmu1, 2, KI_RPM_PATHWAY, KI_RPM_PULSE);
    if (status) return status;
    status = rpm_config(pmu2, 1, KI_RPM_PATHWAY, KI_RPM_PULSE);
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

    status = pulse_ranges(pmu1, 1, voltage_range,
        PULSE_MEAS_FIXED, voltage_range, PULSE_MEAS_FIXED, current_range);
    if (status) return status;
    status = pulse_ranges(pmu1, 2, voltage_range,
        PULSE_MEAS_FIXED, voltage_range, PULSE_MEAS_FIXED, current_range);
    if (status) return status;
    status = pulse_ranges(pmu2, 1, voltage_range,
        PULSE_MEAS_FIXED, voltage_range, PULSE_MEAS_FIXED, current_range);
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

    status = pulse_measrt(pmu1, 1, "Gate_V", "Gate_I", "Time", NULL);
    if (status) return status;
    status = pulse_measrt(pmu1, 2, "Drain_V", "Drain_I", "", NULL);
    if (status) return status;
    status = pulse_measrt(pmu2, 1, "Source_V", "Source_I", "", NULL);
    if (status) return status;

    status = bti_define_sequence(
        pmu1, pmu2, 1, segment_count,
        gate_start, gate_stop, drain_start, drain_stop,
        source_start, source_stop, segment_time, trigger_out, ssr,
        measure_type, measure_start, measure_stop);
    if (status) return status;

    /* Sequence 2 enters stress; sequence 4 returns to measurement bias. */
    segment_count = bti_make_transition(
        vgate_start, is_dc ? vstress : vstdby, programmed_trf,
        gate_start, gate_stop, drain_start, drain_stop,
        source_start, source_stop, segment_time, trigger_out, ssr,
        measure_type, measure_start, measure_stop);
    if (segment_count < 0) return segment_count;
    status = bti_define_sequence(
        pmu1, pmu2, 2, segment_count,
        gate_start, gate_stop, drain_start, drain_stop,
        source_start, source_stop, segment_time, trigger_out, ssr,
        measure_type, measure_start, measure_stop);
    if (status) return status;

    if (is_dc)
    {
        segment_count = 0;
        for (i = 0; i < 3; ++i)
        {
            status = bti_append_segment(
                &segment_count, gate_start, gate_stop, drain_start, drain_stop,
                source_start, source_stop, segment_time, trigger_out, ssr,
                measure_type, measure_start, measure_stop,
                vstress, vstress, 0.0, 0.0, 0.0, 0.0,
                BTI_MAX_SEGMENT_TIME, 0, 0.0, 0.0, 0);
            if (status) return status;
        }
    }
    else
    {
        segment_count = 0;
        status = bti_append_segment(
            &segment_count, gate_start, gate_stop, drain_start, drain_stop,
            source_start, source_stop, segment_time, trigger_out, ssr,
            measure_type, measure_start, measure_stop,
            vstdby, vstress, 0.0, 0.0, 0.0, 0.0,
            programmed_trf, 0, 0.0, 0.0, 0);
        if (status) return status;
        status = bti_append_hold_chunks(
            &segment_count, gate_start, gate_stop, drain_start, drain_stop,
            source_start, source_stop, segment_time, trigger_out, ssr,
            measure_type, measure_start, measure_stop,
            vstress, 0.0, 0.0, programmed_thigh);
        if (status) return status;
        status = bti_append_segment(
            &segment_count, gate_start, gate_stop, drain_start, drain_stop,
            source_start, source_stop, segment_time, trigger_out, ssr,
            measure_type, measure_start, measure_stop,
            vstress, vstdby, 0.0, 0.0, 0.0, 0.0,
            programmed_trf, 0, 0.0, 0.0, 0);
        if (status) return status;
        if (standby_time > 0.0)
        {
            status = bti_append_hold_chunks(
                &segment_count, gate_start, gate_stop, drain_start, drain_stop,
                source_start, source_stop, segment_time, trigger_out, ssr,
                measure_type, measure_start, measure_stop,
                vstdby, 0.0, 0.0, standby_time);
            if (status) return status;
        }
    }

    status = bti_define_sequence(
        pmu1, pmu2, 3, segment_count,
        gate_start, gate_stop, drain_start, drain_stop,
        source_start, source_stop, segment_time, trigger_out, ssr,
        measure_type, measure_start, measure_stop);
    if (status) return status;

    segment_count = bti_make_transition(
        is_dc ? vstress : vstdby, vgate_start, programmed_trf,
        gate_start, gate_stop, drain_start, drain_stop,
        source_start, source_stop, segment_time, trigger_out, ssr,
        measure_type, measure_start, measure_stop);
    if (segment_count < 0) return segment_count;
    status = bti_define_sequence(
        pmu1, pmu2, 4, segment_count,
        gate_start, gate_stop, drain_start, drain_stop,
        source_start, source_stop, segment_time, trigger_out, ssr,
        measure_type, measure_start, measure_stop);
    if (status) return status;

    waveform_count = 0;
    waveform_sequences[waveform_count] = 1;
    waveform_loops[waveform_count++] = 1.0;
    next_sequence = 5;
    previous_stress_time = 0.0;
    previous_cycle_count = 0.0;

    for (i = 0; i < stress_times_size; ++i)
    {
        if (is_dc)
        {
            interval = bti_quantize_time(stress_times[i] - previous_stress_time);
            if (interval > BTI_TIME_TOLERANCE)
            {
                waveform_sequences[waveform_count] = 2;
                waveform_loops[waveform_count++] = 1.0;
                block_loops = floor(interval / BTI_DC_BLOCK_TIME);
                remainder = bti_quantize_time(interval - block_loops * BTI_DC_BLOCK_TIME);
                if (remainder > 0.0 && remainder < 60e-9 && block_loops >= 1.0)
                {
                    block_loops -= 1.0;
                    remainder = bti_quantize_time(remainder + BTI_DC_BLOCK_TIME);
                }

            if (block_loops >= 1.0)
            {
                if (block_loops > 1e12)
                {
                    printf("bias_stress: a DC block loop count exceeds 1e12.");
                    return -10;
                }
                waveform_sequences[waveform_count] = 3;
                waveform_loops[waveform_count++] = block_loops;
            }

            if (remainder > 0.0)
            {
                double split_remaining;
                double split_duration;
                segment_count = 0;
                split_remaining = remainder;
                split_parts = (remainder > BTI_DC_BLOCK_TIME) ? 4 : 3;
                for (j = 0; j < split_parts; ++j)
                {
                    split_duration = bti_quantize_time(
                        split_remaining / (split_parts - j));
                    status = bti_append_segment(
                        &segment_count, gate_start, gate_stop,
                        drain_start, drain_stop, source_start, source_stop,
                        segment_time, trigger_out, ssr, measure_type,
                        measure_start, measure_stop,
                        vstress, vstress, 0.0, 0.0, 0.0, 0.0,
                        split_duration,
                        0, 0.0, 0.0, 0);
                    if (status) return status;
                    split_remaining = bti_quantize_time(
                        split_remaining - split_duration);
                }
                status = bti_define_sequence(
                    pmu1, pmu2, next_sequence, segment_count,
                    gate_start, gate_stop, drain_start, drain_stop,
                    source_start, source_stop, segment_time, trigger_out, ssr,
                    measure_type, measure_start, measure_stop);
                if (status) return status;
                waveform_sequences[waveform_count] = next_sequence++;
                waveform_loops[waveform_count++] = 1.0;
                }
            }
        }
        else
        {
            cumulative_cycle_count =
                floor(stress_times[i] / period + 0.5);
            if (cumulative_cycle_count > previous_cycle_count)
            {
                waveform_sequences[waveform_count] = 2;
                waveform_loops[waveform_count++] = 1.0;
                if (cumulative_cycle_count - previous_cycle_count > 1e12)
                {
                    printf("bias_stress: an AC cycle loop count exceeds 1e12.");
                    return -10;
                }
                waveform_sequences[waveform_count] = 3;
                waveform_loops[waveform_count++] =
                    cumulative_cycle_count - previous_cycle_count;
                waveform_sequences[waveform_count] = 4;
                waveform_loops[waveform_count++] = 1.0;
            }
            previous_cycle_count = cumulative_cycle_count;
        }

        if (!(i == 0 && stress_times[i] <= BTI_TIME_TOLERANCE))
        {
            waveform_sequences[waveform_count] = 1;
            waveform_loops[waveform_count++] = 1.0;
        }
        previous_stress_time = stress_times[i];
    }

    if (waveform_count > BTI_MAX_WAVEFORM_ENTRIES || next_sequence > 512)
    {
        printf("bias_stress: waveform exceeds Keithley sequence limits.");
        return -10;
    }

    status = seg_arb_waveform(pmu1, 1, waveform_count,
        waveform_sequences, waveform_loops);
    if (status) return status;
    status = seg_arb_waveform(pmu1, 2, waveform_count,
        waveform_sequences, waveform_loops);
    if (status) return status;
    status = seg_arb_waveform(pmu2, 1, waveform_count,
        waveform_sequences, waveform_loops);
    if (status) return status;

    status = pulse_output(pmu1, 1, 1);
    if (status) return status;
    status = pulse_output(pmu1, 2, 1);
    if (status) return status;
    status = pulse_output(pmu2, 1, 1);
    if (status) return status;

    status = pulse_exec(PULSE_MODE_SIMPLE);
    if (status) return status;
    while (pulse_exec_status(&elapsed_time) == 1)
        Sleep(10);

    return 0;

/* USRLIB MODULE END */
}


static double bti_quantize_time(double value)
{
    if (value <= 0.0)
        return 0.0;
    return floor(value / BTI_TIME_RESOLUTION + 0.5) *
           BTI_TIME_RESOLUTION;
}


static int bti_mode_is(const char *value, const char *wanted)
{
    int i;
    if (value == NULL || wanted == NULL)
        return 0;
    for (i = 0; value[i] != '\0' && wanted[i] != '\0'; ++i)
    {
        char a = value[i];
        char b = wanted[i];
        if (a >= 'a' && a <= 'z') a = (char)(a - 'a' + 'A');
        if (b >= 'a' && b <= 'z') b = (char)(b - 'a' + 'A');
        if (a != b) return 0;
    }
    return value[i] == '\0' && wanted[i] == '\0';
}


static int bti_append_segment(
    int *count,
    double *gate_start, double *gate_stop,
    double *drain_start, double *drain_stop,
    double *source_start, double *source_stop,
    double *segment_time, long *trigger_out, long *ssr,
    long *measure_type, double *measure_start, double *measure_stop,
    double gate0, double gate1, double drain0, double drain1,
    double source0, double source1, double duration,
    long meas_type, double meas_start, double meas_stop,
    long trigger)
{
    int index;
    duration = bti_quantize_time(duration);
    if (*count >= BTI_MAX_SEGMENTS ||
        duration < BTI_MIN_SEGMENT_TIME ||
        duration > BTI_MAX_SEGMENT_TIME)
    {
        printf("bias_stress: a segment is outside the 20 ns to 20 s limits.");
        return -11;
    }
    if (meas_type != 0 &&
        (!(meas_start >= 0.0) || !(meas_stop > meas_start) ||
         meas_stop > duration))
    {
        printf("bias_stress: invalid measurement window.");
        return -11;
    }

    index = *count;
    gate_start[index] = gate0;
    gate_stop[index] = gate1;
    drain_start[index] = drain0;
    drain_stop[index] = drain1;
    source_start[index] = source0;
    source_stop[index] = source1;
    segment_time[index] = duration;
    trigger_out[index] = trigger;
    ssr[index] = 1;
    measure_type[index] = meas_type;
    measure_start[index] = (meas_type != 0) ? meas_start : 0.0;
    measure_stop[index] = (meas_type != 0) ? meas_stop : 0.0;
    *count = index + 1;
    return 0;
}


static int bti_append_hold_chunks(
    int *count,
    double *gate_start, double *gate_stop,
    double *drain_start, double *drain_stop,
    double *source_start, double *source_stop,
    double *segment_time, long *trigger_out, long *ssr,
    long *measure_type, double *measure_start, double *measure_stop,
    double gate, double drain, double source, double duration)
{
    double remaining;
    double chunk;
    double after;
    int status;

    remaining = bti_quantize_time(duration);
    while (remaining > BTI_TIME_TOLERANCE)
    {
        chunk = (remaining > BTI_MAX_SEGMENT_TIME)
                    ? BTI_MAX_SEGMENT_TIME : remaining;
        after = bti_quantize_time(remaining - chunk);
        if (after > 0.0 && after < BTI_MIN_SEGMENT_TIME)
            chunk = bti_quantize_time(chunk - (BTI_MIN_SEGMENT_TIME - after));
        status = bti_append_segment(
            count, gate_start, gate_stop, drain_start, drain_stop,
            source_start, source_stop, segment_time, trigger_out, ssr,
            measure_type, measure_start, measure_stop,
            gate, gate, drain, drain, source, source,
            chunk, 0, 0.0, 0.0, 0);
        if (status) return status;
        remaining = bti_quantize_time(remaining - chunk);
    }
    return 0;
}


static int bti_make_transition(
    double from_gate, double to_gate, double duration,
    double *gate_start, double *gate_stop,
    double *drain_start, double *drain_stop,
    double *source_start, double *source_stop,
    double *segment_time, long *trigger_out, long *ssr,
    long *measure_type, double *measure_start, double *measure_stop)
{
    int count;
    int total_ticks;
    int remaining_ticks;
    int part_ticks;
    int i;
    int status;
    double elapsed;
    double next_elapsed;
    double gate0;
    double gate1;

    count = 0;
    total_ticks = (int)floor(
        bti_quantize_time(duration) / BTI_TIME_RESOLUTION + 0.5);
    remaining_ticks = total_ticks;
    elapsed = 0.0;
    for (i = 0; i < 3; ++i)
    {
        part_ticks = remaining_ticks / (3 - i);
        next_elapsed = elapsed + part_ticks * BTI_TIME_RESOLUTION;
        gate0 = from_gate + (to_gate - from_gate) *
                elapsed / (total_ticks * BTI_TIME_RESOLUTION);
        gate1 = from_gate + (to_gate - from_gate) *
                next_elapsed / (total_ticks * BTI_TIME_RESOLUTION);
        status = bti_append_segment(
            &count, gate_start, gate_stop, drain_start, drain_stop,
            source_start, source_stop, segment_time, trigger_out, ssr,
            measure_type, measure_start, measure_stop,
            gate0, gate1, 0.0, 0.0, 0.0, 0.0,
            part_ticks * BTI_TIME_RESOLUTION, 0, 0.0, 0.0, 0);
        if (status) return status;
        remaining_ticks -= part_ticks;
        elapsed = next_elapsed;
    }
    return count;
}


static int bti_define_sequence(
    int pmu1, int pmu2, long sequence_number, int segment_count,
    double *gate_start, double *gate_stop,
    double *drain_start, double *drain_stop,
    double *source_start, double *source_stop,
    double *segment_time, long *trigger_out, long *ssr,
    long *measure_type, double *measure_start, double *measure_stop)
{
    int status;
    if (segment_count < 3 || segment_count > BTI_MAX_SEGMENTS)
    {
        printf("bias_stress: every sequence must contain 3 to 2048 segments.");
        return -12;
    }

    status = seg_arb_sequence(
        pmu1, 1, sequence_number, segment_count,
        gate_start, gate_stop, segment_time,
        trigger_out, ssr, measure_type, measure_start, measure_stop);
    if (status) return status;
    status = seg_arb_sequence(
        pmu1, 2, sequence_number, segment_count,
        drain_start, drain_stop, segment_time,
        trigger_out, ssr, measure_type, measure_start, measure_stop);
    if (status) return status;
    status = seg_arb_sequence(
        pmu2, 1, sequence_number, segment_count,
        source_start, source_stop, segment_time,
        trigger_out, ssr, measure_type, measure_start, measure_stop);
    return status;
}
