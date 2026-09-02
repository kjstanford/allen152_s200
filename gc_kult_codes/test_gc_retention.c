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
#define GC_MAX_SEGMENTS (6 + 4 * GC_MAX_RETENTION_POINTS)
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
    double total_time[GC_MAX_SEGMENTS + 1];
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
    int read_index[GC_MAX_SEGMENTS];
} GcRetentionProgram;

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

static int gc_append_segment(
    const GcRetentionConfig *config,
    GcRetentionProgram *program,
    double duration,
    double wwl_start,
    double wwl_stop,
    double wbl_start,
    double wbl_stop,
    double rwl_start,
    double rwl_stop,
    unsigned long measure_type,
    double measure_start,
    double measure_stop,
    int read_index);

static int gc_parse_state(const char *text, int *state);
static int gc_parse_double(const char *text, double *value);
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
    int i;
    double gap;
    double measure_window;
    double wbl_base;
    double wbl_data;
    double programmed_tdelay;
    double programmed_trf;
    double programmed_twrite;
    double programmed_tread;
    double read_pulse_time;

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

    programmed_tdelay = gc_quantize_time(config->tdelay);
    programmed_trf = gc_quantize_time(config->trf);
    programmed_twrite = gc_quantize_time(config->twrite);
    programmed_tread = gc_quantize_time(config->tread);

    if (programmed_trf < 20e-9 || programmed_twrite < 20e-9 ||
        programmed_tread < 20e-9 ||
        (programmed_tdelay > 0.0 && programmed_tdelay < 20e-9))
    {
        fprintf(
            stderr,
            "Validation -1: timing rounds below the 20 ns minimum.\n");
        return -1;
    }

    measure_window =
        (config->measure_stop_fraction -
         config->measure_start_fraction) * programmed_tread;

    if (measure_window < 10e-9 ||
        measure_window * config->sample_rate < 1.0)
    {
        fprintf(
            stderr,
            "Validation -4: spot-mean window must be at least 10 ns "
            "and contain at least one sample.\n");
        return -4;
    }

    read_pulse_time = 2.0 * programmed_trf + programmed_tread;

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
                  read_pulse_time;
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

    wbl_base = (config->state == 1) ? config->vdata0 : config->vdata1;
    wbl_data = (config->state == 1) ? config->vdata1 : config->vdata0;

    program->segment_count = 0;
    program->total_time[0] = 0.0;

    if (programmed_tdelay > 0.0 &&
        gc_append_segment(
            config, program, programmed_tdelay,
            config->vhold, config->vhold,
            wbl_base, wbl_base,
            config->vss, config->vss,
            GC_MEAS_NONE, 0.0, 0.0, -1) != 0)
    {
        return -8;
    }

#define GC_DEBUG_APPEND(DURATION, WWL0, WWL1, WBL0, WBL1, RWL0, RWL1, MTYPE, MSTART, MSTOP, READ_INDEX) \
    do { \
        int gc_status = gc_append_segment( \
            config, program, (DURATION), \
            (WWL0), (WWL1), (WBL0), (WBL1), (RWL0), (RWL1), \
            (MTYPE), (MSTART), (MSTOP), (READ_INDEX)); \
        if (gc_status != 0) return gc_status; \
    } while (0)

    GC_DEBUG_APPEND(
        programmed_trf,
        config->vhold, config->vboost,
        wbl_base, wbl_data,
        config->vss, config->vss,
        GC_MEAS_NONE, 0.0, 0.0, -1);

    GC_DEBUG_APPEND(
        programmed_twrite,
        config->vboost, config->vboost,
        wbl_data, wbl_data,
        config->vss, config->vss,
        GC_MEAS_NONE, 0.0, 0.0, -1);

    GC_DEBUG_APPEND(
        programmed_trf,
        config->vboost, config->vhold,
        wbl_data, wbl_data,
        config->vss, config->vss,
        GC_MEAS_NONE, 0.0, 0.0, -1);

    GC_DEBUG_APPEND(
        programmed_trf,
        config->vhold, config->vhold,
        wbl_data, wbl_data,
        config->vss, config->vss,
        GC_MEAS_NONE, 0.0, 0.0, -1);

    GC_DEBUG_APPEND(
        programmed_trf,
        config->vhold, config->vhold,
        wbl_data, wbl_base,
        config->vss, config->vss,
        GC_MEAS_NONE, 0.0, 0.0, -1);

    program->retention_origin =
        program->total_time[program->segment_count];

    for (i = 0; i < retention_count; ++i)
    {
        if (i == 0)
            gap = retention_times[0];
        else
            gap = retention_times[i] - retention_times[i - 1] -
                  read_pulse_time;

        if (gap > GC_TIME_TOLERANCE)
        {
            GC_DEBUG_APPEND(
                gap,
                config->vhold, config->vhold,
                wbl_base, wbl_base,
                config->vss, config->vss,
                GC_MEAS_NONE, 0.0, 0.0, -1);
        }

        GC_DEBUG_APPEND(
            programmed_trf,
            config->vhold, config->vhold,
            wbl_base, wbl_base,
            config->vss, config->vdd,
            GC_MEAS_NONE, 0.0, 0.0, -1);

        GC_DEBUG_APPEND(
            programmed_tread,
            config->vhold, config->vhold,
            wbl_base, wbl_base,
            config->vdd, config->vdd,
            GC_MEAS_SPOT_MEAN_DISCRETE,
            config->measure_start_fraction * programmed_tread,
            config->measure_stop_fraction * programmed_tread,
            i);

        GC_DEBUG_APPEND(
            programmed_trf,
            config->vhold, config->vhold,
            wbl_base, wbl_base,
            config->vdd, config->vss,
            GC_MEAS_NONE, 0.0, 0.0, -1);
    }

#undef GC_DEBUG_APPEND

    if (program->segment_count < 3 ||
        program->segment_count > 2048)
    {
        fprintf(
            stderr,
            "Validation -6: invalid Segment ARB segment count: %d.\n",
            program->segment_count);
        return -6;
    }

    return 0;
}


static int gc_append_segment(
    const GcRetentionConfig *config,
    GcRetentionProgram *program,
    double duration,
    double wwl_start,
    double wwl_stop,
    double wbl_start,
    double wbl_stop,
    double rwl_start,
    double rwl_stop,
    unsigned long measure_type,
    double measure_start,
    double measure_stop,
    int read_index)
{
    int index = program->segment_count;
    double exact_duration = gc_quantize_time(duration);

    if (index >= GC_MAX_SEGMENTS)
    {
        fprintf(stderr, "Validation -6: too many Segment ARB segments.\n");
        return -6;
    }

    if (exact_duration < 20e-9)
    {
        fprintf(
            stderr,
            "Validation -8: segment %d is %.17g s, below 20 ns.\n",
            index + 1,
            exact_duration);
        return -8;
    }

    program->segment_time[index] = exact_duration;
    program->total_time[index + 1] =
        program->total_time[index] + exact_duration;
    program->wwl_start[index] = wwl_start;
    program->wwl_stop[index] = wwl_stop;
    program->wbl_start[index] = wbl_start;
    program->wbl_stop[index] = wbl_stop;
    program->rwl_start[index] = rwl_start;
    program->rwl_stop[index] = rwl_stop;
    program->rbl_start[index] = config->vss;
    program->rbl_stop[index] = config->vss;
    program->trigger_out[index] = (index == 0) ? 1 : 0;
    program->wwl_ssr[index] = 1;
    program->wbl_ssr[index] = 1;
    program->rwl_ssr[index] = 1;
    program->rbl_ssr[index] = 1;
    program->measure_type[index] = measure_type;
    program->measure_start[index] = measure_start;
    program->measure_stop[index] = measure_stop;
    program->read_index[index] = read_index;
    program->segment_count = index + 1;

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
        "sequence_id,segment_index,total_time_start_s,total_time_stop_s,"
        "segment_time_s,"
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
        int read_index = program->read_index[i];
        double retention_time =
            (read_index >= 0) ? retention_times[read_index] : -1.0;
        const char *measure_name =
            (program->measure_type[i] == GC_MEAS_SPOT_MEAN_DISCRETE)
                ? "spot_mean_discrete"
                : "none";

        fprintf(
            file,
            "1,%d,%.17g,%.17g,%.17g,"
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
            program->total_time[i],
            program->total_time[i + 1],
            program->segment_time[i],
            program->trigger_out[i],
            program->wwl_ssr[i],
            program->wbl_ssr[i],
            program->rwl_ssr[i],
            program->rbl_ssr[i],
            program->measure_type[i],
            measure_name,
            program->measure_start[i],
            program->measure_stop[i],
            program->total_time[i] + program->measure_start[i],
            program->total_time[i] + program->measure_stop[i],
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


static double gc_quantize_time(double value)
{
    return floor(value / GC_TIME_RESOLUTION + 0.5) *
           GC_TIME_RESOLUTION;
}
