/*
 * Standalone software model for gc_retention.c.
 *
 * This program does not require a 4200A-SCS or keithley.h. It constructs
 * the same Segment ARB arrays as gc_retention.c and writes the values that
 * would be passed to the Keithley LPT functions to a CSV file.
 *
 * Build from the repository root in Git Bash:
 *   mkdir -p gc_kult_codes/scratch
 *   gcc -std=c99 -O2 -Wall -Wextra \
 *       -o gc_kult_codes/scratch/test_gc_retention.exe \
 *       gc_kult_codes/test_gc_retention.c -lm
 *
 * Run with defaults:
 *   ./gc_kult_codes/scratch/test_gc_retention.exe
 *
 * Run with custom cumulative retention times:
 *   ./gc_kult_codes/scratch/test_gc_retention.exe \
 *       gc_kult_codes/scratch/output.csv 1 1e-6 1e-3 1 10
 *
 * Arguments are:
 *   output CSV path, state (0 or 1), retention time 1, time 2, ...
 */

#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define GC_MAX_RETENTION_POINTS 256
#define GC_MAX_BREAKPOINTS (8 + 4 * GC_MAX_RETENTION_POINTS)
#define GC_MAX_SEGMENTS (GC_MAX_BREAKPOINTS - 1)
#define GC_MEAS_NONE 0UL
#define GC_MEAS_SPOT_MEAN_DISCRETE 1UL
#define GC_TIME_RESOLUTION 10e-9
#define GC_TIME_TOLERANCE 1e-9

typedef struct
{
    double vhold;
    double vboost;
    double vdata0;
    double vdata1;
    double vss;
    double vdd;
    double tdelay;
    double trf;
    double twrite;
    double tread;
    double measure_start_fraction;
    double measure_stop_fraction;
    int state;
    double sample_rate;
    double voltage_range;
    double current_range;
    double dut_resistance;
    const char *pmu_id1;
    const char *pmu_id2;
} GcRetentionConfig;

typedef struct
{
    int segment_count;
    double retention_origin;
    double requested_start[GC_MAX_SEGMENTS];
    double requested_stop[GC_MAX_SEGMENTS];
    double programmed_duration[GC_MAX_SEGMENTS];

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
    int read_index[GC_MAX_SEGMENTS];
} GcRetentionProgram;

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
    const double *retention_times,
    int retention_count,
    double rise,
    double high_time,
    double fall);

static int gc_read_high_index(
    double segment_start,
    double segment_stop,
    double retention_origin,
    const double *retention_times,
    int retention_count,
    double rise,
    double high_time);

static int gc_build_program(
    const GcRetentionConfig *config,
    const double *retention_times,
    int retention_count,
    GcRetentionProgram *program);

static int gc_write_csv(
    const char *path,
    const GcRetentionConfig *config,
    const double *retention_times,
    const GcRetentionProgram *program);

static int gc_parse_state(const char *text, int *state);
static int gc_parse_double(const char *text, double *value);
static void gc_add_time(double *times, int *count, double value);
static void gc_sort_times(double *times, int count);
static double gc_quantize_time(double value);


int main(int argc, char **argv)
{
    /* Edit this block to match a specific Clarius/KULT test setup. */
    GcRetentionConfig config = {
        0.0,       /* vhold */
        2.0,       /* vboost */
        0.0,       /* vdata0 */
        1.0,       /* vdata1 */
        0.0,       /* vss */
        1.0,       /* vdd */
        1e-6,      /* tdelay */
        100e-9,    /* trf */
        1e-6,      /* twrite */
        1e-6,      /* tread */
        0.2,       /* measure_start_fraction */
        0.8,       /* measure_stop_fraction */
        1,         /* state */
        100e6,     /* sample_rate */
        10.0,      /* voltage_range */
        1e-3,      /* current_range */
        1e6,       /* dut_resistance */
        "PMU1",    /* PMU_ID1 */
        "PMU2"     /* PMU_ID2 */
    };

    const double default_retention_times[] = {
        1e-6,
        10e-6,
        1e-3,
        1.0,
        10.0
    };
    double retention_times[GC_MAX_RETENTION_POINTS];
    GcRetentionProgram program;
    const char *output_path =
        "gc_kult_codes/scratch/gc_retention_debug.csv";
    int retention_count;
    int status;
    int i;

    if (argc == 2 || argc == 3)
    {
        fprintf(
            stderr,
            "Usage: %s [output.csv state retention_time_s ...]\n",
            argv[0]);
        return 2;
    }

    if (argc >= 4)
    {
        output_path = argv[1];

        if (!gc_parse_state(argv[2], &config.state))
        {
            fprintf(stderr, "State must be 0 or 1, got: %s\n", argv[2]);
            return 2;
        }

        retention_count = argc - 3;
        if (retention_count > GC_MAX_RETENTION_POINTS)
        {
            fprintf(
                stderr,
                "At most %d retention times are supported.\n",
                GC_MAX_RETENTION_POINTS);
            return 2;
        }

        for (i = 0; i < retention_count; ++i)
        {
            if (!gc_parse_double(argv[i + 3], &retention_times[i]))
            {
                fprintf(
                    stderr,
                    "Invalid retention time at argument %d: %s\n",
                    i + 3,
                    argv[i + 3]);
                return 2;
            }
        }
    }
    else
    {
        retention_count = (int)(
            sizeof(default_retention_times) /
            sizeof(default_retention_times[0]));

        for (i = 0; i < retention_count; ++i)
            retention_times[i] = default_retention_times[i];
    }

    memset(&program, 0, sizeof(program));

    status = gc_build_program(
        &config, retention_times, retention_count, &program);
    if (status != 0)
        return 1;

    status = gc_write_csv(
        output_path, &config, retention_times, &program);
    if (status != 0)
        return 1;

    printf(
        "Wrote %d Segment ARB segments for %d retention reads to %s\n",
        program.segment_count,
        retention_count,
        output_path);
    printf(
        "Retention origin: %.17g s; one spot-mean result per read.\n",
        program.retention_origin);

    return 0;
}


static int gc_build_program(
    const GcRetentionConfig *config,
    const double *retention_times,
    int retention_count,
    GcRetentionProgram *program)
{
    double breakpoints[GC_MAX_BREAKPOINTS];
    int point_count = 0;
    int i;
    double gap;
    double measure_window;
    double write_start;
    double wwl_rise_end;
    double wwl_high_end;
    double wwl_end;
    double wbl_high_end;
    double total_time;
    double wbl_base;
    double wbl_data;

    if (!(config->trf >= 20e-9) ||
        !(config->twrite >= 20e-9) ||
        !(config->tread >= 20e-9) ||
        !(config->tdelay >= 0.0) ||
        (config->tdelay > 0.0 && config->tdelay < 20e-9))
    {
        fprintf(stderr, "Validation -1: invalid timing parameter.\n");
        return -1;
    }

    if (config->state != 0 && config->state != 1)
    {
        fprintf(stderr, "Validation -2: state must be 0 or 1.\n");
        return -2;
    }

    if (retention_times == NULL || retention_count < 1 ||
        retention_count > GC_MAX_RETENTION_POINTS)
    {
        fprintf(
            stderr,
            "Validation -3: retention list must contain 1 to %d values.\n",
            GC_MAX_RETENTION_POINTS);
        return -3;
    }

    if (!(config->sample_rate > 0.0) || config->sample_rate > 200e6)
    {
        fprintf(
            stderr,
            "Validation -4: sample rate must be > 0 and <= 200e6.\n");
        return -4;
    }

    if (!(config->measure_start_fraction >= 0.0) ||
        !(config->measure_stop_fraction <= 1.0) ||
        !(config->measure_start_fraction <
          config->measure_stop_fraction))
    {
        fprintf(
            stderr,
            "Validation -4: fractions must satisfy "
            "0 <= start < stop <= 1.\n");
        return -4;
    }

    measure_window =
        (config->measure_stop_fraction -
         config->measure_start_fraction) * config->tread;

    if (measure_window < 10e-9 ||
        measure_window * config->sample_rate < 1.0)
    {
        fprintf(
            stderr,
            "Validation -4: spot-mean window must be at least 10 ns "
            "and contain at least one sample.\n");
        return -4;
    }

    for (i = 0; i < retention_count; ++i)
    {
        if (!(retention_times[i] >= 0.0) ||
            retention_times[i] - retention_times[i] != 0.0)
        {
            fprintf(
                stderr,
                "Validation -5: retention_times[%d] is invalid.\n",
                i);
            return -5;
        }

        if (i == 0)
        {
            gap = retention_times[0];
        }
        else
        {
            gap = retention_times[i] - retention_times[i - 1] -
                  (2.0 * config->trf + config->tread);
        }

        if (gap < -GC_TIME_TOLERANCE ||
            (gap > GC_TIME_TOLERANCE &&
             gap < 20e-9 - GC_TIME_TOLERANCE))
        {
            fprintf(
                stderr,
                "Validation -5: read %d overlaps the previous event "
                "or creates a hold shorter than 20 ns.\n",
                i + 1);
            return -5;
        }
    }

    write_start = config->tdelay;
    wwl_rise_end = write_start + config->trf;
    wwl_high_end = wwl_rise_end + config->twrite;
    wwl_end = wwl_high_end + config->trf;
    wbl_high_end =
        wwl_rise_end + config->twrite + 2.0 * config->trf;
    program->retention_origin = wbl_high_end + config->trf;

    wbl_base = (config->state == 1) ? config->vdata0 : config->vdata1;
    wbl_data = (config->state == 1) ? config->vdata1 : config->vdata0;

    total_time = program->retention_origin +
                 retention_times[retention_count - 1] +
                 2.0 * config->trf + config->tread;

    gc_add_time(breakpoints, &point_count, 0.0);
    gc_add_time(breakpoints, &point_count, write_start);
    gc_add_time(breakpoints, &point_count, wwl_rise_end);
    gc_add_time(breakpoints, &point_count, wwl_high_end);
    gc_add_time(breakpoints, &point_count, wwl_end);
    gc_add_time(breakpoints, &point_count, wbl_high_end);
    gc_add_time(
        breakpoints, &point_count, program->retention_origin);

    for (i = 0; i < retention_count; ++i)
    {
        double read_start =
            program->retention_origin + retention_times[i];
        double read_rise_end = read_start + config->trf;
        double read_high_end = read_rise_end + config->tread;
        double read_end = read_high_end + config->trf;

        gc_add_time(breakpoints, &point_count, read_start);
        gc_add_time(breakpoints, &point_count, read_rise_end);
        gc_add_time(breakpoints, &point_count, read_high_end);
        gc_add_time(breakpoints, &point_count, read_end);
    }

    gc_add_time(breakpoints, &point_count, total_time);
    gc_sort_times(breakpoints, point_count);
    program->segment_count = point_count - 1;

    if (program->segment_count < 3 ||
        program->segment_count > GC_MAX_SEGMENTS ||
        program->segment_count > 2048)
    {
        fprintf(
            stderr,
            "Validation -6: invalid Segment ARB segment count: %d.\n",
            program->segment_count);
        return -6;
    }

    for (i = 0; i < program->segment_count; ++i)
    {
        double t0 = breakpoints[i];
        double t1 = breakpoints[i + 1];
        int read_index;

        program->requested_start[i] = t0;
        program->requested_stop[i] = t1;
        program->programmed_duration[i] =
            gc_quantize_time(t1 - t0);

        if (program->programmed_duration[i] < 20e-9)
        {
            fprintf(
                stderr,
                "Validation -8: segment %d is %.17g s, below 20 ns.\n",
                i + 1,
                program->programmed_duration[i]);
            return -8;
        }

        program->wwl_start[i] = gc_pulse_value(
            t0,
            config->vhold,
            config->vboost,
            write_start,
            config->trf,
            config->twrite,
            config->trf);
        program->wwl_stop[i] = gc_pulse_value(
            t1,
            config->vhold,
            config->vboost,
            write_start,
            config->trf,
            config->twrite,
            config->trf);

        program->wbl_start[i] = gc_pulse_value(
            t0,
            wbl_base,
            wbl_data,
            write_start,
            config->trf,
            config->twrite + 2.0 * config->trf,
            config->trf);
        program->wbl_stop[i] = gc_pulse_value(
            t1,
            wbl_base,
            wbl_data,
            write_start,
            config->trf,
            config->twrite + 2.0 * config->trf,
            config->trf);

        program->rwl_start[i] = gc_read_value(
            t0,
            config->vss,
            config->vdd,
            program->retention_origin,
            retention_times,
            retention_count,
            config->trf,
            config->tread,
            config->trf);
        program->rwl_stop[i] = gc_read_value(
            t1,
            config->vss,
            config->vdd,
            program->retention_origin,
            retention_times,
            retention_count,
            config->trf,
            config->tread,
            config->trf);

        program->rbl_start[i] = config->vss;
        program->rbl_stop[i] = config->vss;
        program->trigger_out[i] = (i == 0) ? 1 : 0;
        program->wwl_ssr[i] = 1;
        program->wbl_ssr[i] = 1;
        program->rwl_ssr[i] = 1;
        program->rbl_ssr[i] = 1;

        read_index = gc_read_high_index(
            t0,
            t1,
            program->retention_origin,
            retention_times,
            retention_count,
            config->trf,
            config->tread);
        program->read_index[i] = read_index;

        if (read_index >= 0)
        {
            program->measure_type[i] =
                GC_MEAS_SPOT_MEAN_DISCRETE;
            program->measure_start[i] =
                config->measure_start_fraction *
                program->programmed_duration[i];
            program->measure_stop[i] =
                config->measure_stop_fraction *
                program->programmed_duration[i];
        }
        else
        {
            program->measure_type[i] = GC_MEAS_NONE;
            program->measure_start[i] = 0.0;
            program->measure_stop[i] = 0.0;
        }
    }

    return 0;
}


static int gc_write_csv(
    const char *path,
    const GcRetentionConfig *config,
    const double *retention_times,
    const GcRetentionProgram *program)
{
    FILE *file;
    int i;
    double programmed_start = 0.0;

    file = fopen(path, "w");
    if (file == NULL)
    {
        fprintf(
            stderr,
            "Cannot open CSV output '%s': %s\n",
            path,
            strerror(errno));
        return -1;
    }

    fprintf(
        file,
        "sequence_id,segment_index,requested_start_s,requested_stop_s,"
        "programmed_start_s,programmed_stop_s,programmed_duration_s,"
        "trigger_out,wwl_ssr,wbl_ssr,rwl_ssr,rbl_ssr,measure_type,"
        "measure_name,measure_start_in_segment_s,"
        "measure_stop_in_segment_s,measure_absolute_start_s,"
        "measure_absolute_stop_s,read_index,retention_time_s,"
        "pmu1_id,pmu1_ch1_signal,wwl_start_V,wwl_stop_V,"
        "pmu1_ch2_signal,wbl_start_V,wbl_stop_V,"
        "pmu2_id,pmu2_ch1_signal,rwl_start_V,rwl_stop_V,"
        "pmu2_ch2_signal,rbl_start_V,rbl_stop_V,"
        "state,vhold_V,vboost_V,vdata0_V,vdata1_V,vss_V,vdd_V,"
        "tdelay_s,trf_s,twrite_s,tread_s,retention_origin_s,"
        "measure_start_fraction,measure_stop_fraction,sample_rate_Sps,"
        "source_voltage_range_V,measure_voltage_range_V,"
        "measure_current_range_A,dut_resistance_ohm,rpm_pathway,"
        "pulse_mode,limit_mode,burst_count,sequence_loop_count,"
        "output_enabled,exec_mode,voltage_route,current_route,"
        "timestamp_route\n");

    for (i = 0; i < program->segment_count; ++i)
    {
        double programmed_stop =
            programmed_start + program->programmed_duration[i];
        int read_index = program->read_index[i];
        double retention_time =
            (read_index >= 0) ? retention_times[read_index] : -1.0;
        const char *measure_name =
            (program->measure_type[i] == GC_MEAS_SPOT_MEAN_DISCRETE)
                ? "spot_mean_discrete"
                : "none";

        fprintf(
            file,
            "1,%d,%.17g,%.17g,%.17g,%.17g,%.17g,"
            "%ld,%ld,%ld,%ld,%ld,%lu,%s,"
            "%.17g,%.17g,%.17g,%.17g,%d,%.17g,"
            "%s,WWL,%.17g,%.17g,WBL,%.17g,%.17g,"
            "%s,RWL,%.17g,%.17g,RBL,%.17g,%.17g,"
            "%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,"
            "%.17g,%.17g,%.17g,%.17g,%.17g,"
            "%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,"
            "pulse,SARB,value,1,1,1,simple,"
            "WWL_V|WBL_V|RWL_V,RBL_I,Time\n",
            i + 1,
            program->requested_start[i],
            program->requested_stop[i],
            programmed_start,
            programmed_stop,
            program->programmed_duration[i],
            program->trigger_out[i],
            program->wwl_ssr[i],
            program->wbl_ssr[i],
            program->rwl_ssr[i],
            program->rbl_ssr[i],
            program->measure_type[i],
            measure_name,
            program->measure_start[i],
            program->measure_stop[i],
            programmed_start + program->measure_start[i],
            programmed_start + program->measure_stop[i],
            (read_index >= 0) ? read_index + 1 : 0,
            retention_time,
            config->pmu_id1,
            program->wwl_start[i],
            program->wwl_stop[i],
            program->wbl_start[i],
            program->wbl_stop[i],
            config->pmu_id2,
            program->rwl_start[i],
            program->rwl_stop[i],
            program->rbl_start[i],
            program->rbl_stop[i],
            config->state,
            config->vhold,
            config->vboost,
            config->vdata0,
            config->vdata1,
            config->vss,
            config->vdd,
            config->tdelay,
            config->trf,
            config->twrite,
            config->tread,
            program->retention_origin,
            config->measure_start_fraction,
            config->measure_stop_fraction,
            config->sample_rate,
            config->voltage_range,
            config->voltage_range,
            config->current_range,
            config->dut_resistance);

        programmed_start = programmed_stop;
    }

    if (fclose(file) != 0)
    {
        fprintf(
            stderr,
            "Failed while closing CSV output '%s': %s\n",
            path,
            strerror(errno));
        return -1;
    }

    return 0;
}


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
    {
        return low_value +
               (high_value - low_value) * (t - t0) / rise;
    }
    if (t <= t2)
        return high_value;
    if (t < t3)
    {
        return high_value +
               (low_value - high_value) * (t - t2) / fall;
    }
    return low_value;
}


static double gc_read_value(
    double t,
    double low_value,
    double high_value,
    double retention_origin,
    const double *retention_times,
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
                t,
                low_value,
                high_value,
                read_start,
                rise,
                high_time,
                fall);
        }
    }

    return low_value;
}


static int gc_read_high_index(
    double segment_start,
    double segment_stop,
    double retention_origin,
    const double *retention_times,
    int retention_count,
    double rise,
    double high_time)
{
    int i;
    const double tolerance = GC_TIME_TOLERANCE;

    for (i = 0; i < retention_count; ++i)
    {
        double high_start = retention_origin + retention_times[i] + rise;
        double high_stop = high_start + high_time;

        if (fabs(segment_start - high_start) < tolerance &&
            fabs(segment_stop - high_stop) < tolerance)
        {
            return i;
        }
    }

    return -1;
}


static int gc_parse_state(const char *text, int *state)
{
    char *end;
    long value;

    errno = 0;
    value = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' ||
        (value != 0 && value != 1))
    {
        return 0;
    }

    *state = (int)value;
    return 1;
}


static int gc_parse_double(const char *text, double *value)
{
    char *end;
    double parsed;

    errno = 0;
    parsed = strtod(text, &end);
    if (errno != 0 || end == text || *end != '\0' || !isfinite(parsed))
        return 0;

    *value = parsed;
    return 1;
}


static void gc_add_time(double *times, int *count, double value)
{
    int i;
    const double tolerance = GC_TIME_TOLERANCE;

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


static double gc_quantize_time(double value)
{
    return floor(value / GC_TIME_RESOLUTION + 0.5) *
           GC_TIME_RESOLUTION;
}
