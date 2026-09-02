/* USRLIB MODULE INFORMATION
    MODULE NAME: bias_stress
    MODULE RETURN TYPE: int
    NUMBER OF PARMS: 36
    ARGUMENTS:
        trf,double,Input,2e-7,60e-9,20
        trf2,double,Input,2e-7,60e-9,20
        tplateau,double,Input,1e-5,20e-9,20
        vdrain,double,Input,.1,-40,40
        vgate_start,double,Input,0,-40,40
        vgate_stop,double,Input,2,-40,40
        vgate_step,double,Input,.1,1e-6,40
        measure_start_fraction,double,Input,.2,0,1
        measure_stop_fraction,double,Input,.8,0,1
        stress_mode,char *,Input,"DC",,
        vstress,double,Input,2,-40,40
        vstdby,double,Input,0,-40,40
        thigh,double,Input,1e-6,20e-9,20
        duty_cycle,double,Input,.5,1e-6,1
        stress_times,D_ARRAY_T,Input,,
        stress_times_size,int,Input,10,1,100
        sample_rate,double,Input,1e8,1,2e8
        voltage_range,double,Input,10,10,40
        current_range,double,Input,1e-3,100e-9,.8
        dut_resistance,double,Input,1e6,1,1e9
        PMU_ID1,char *,Input,"PMU1",,
        PMU_ID2,char *,Input,"PMU2",,
        Gate_V,D_ARRAY_T,Output,,
        Gate_V_size,int,Input,30000,100,30000
        Gate_I,D_ARRAY_T,Output,,
        Gate_I_size,int,Input,30000,100,30000
        Drain_V,D_ARRAY_T,Output,,
        Drain_V_size,int,Input,30000,100,30000
        Drain_I,D_ARRAY_T,Output,,
        Drain_I_size,int,Input,30000,100,30000
        Source_V,D_ARRAY_T,Output,,
        Source_V_size,int,Input,30000,100,30000
        Source_I,D_ARRAY_T,Output,,
        Source_I_size,int,Input,30000,100,30000
        Time,D_ARRAY_T,Output,,
        Time_size,int,Input,30000,100,30000
    INCLUDES:
#include "keithley.h"
#include <math.h>
#include <string.h>
    END USRLIB MODULE INFORMATION
*/

/* USRLIB MODULE PARAMETER LIST */

#include "keithley.h"
#include <math.h>
#include <string.h>

#define BTI_MAX_SEGMENTS 2048
#define BTI_MIN_TIME 20e-9
#define BTI_MAX_TIME 20.0
#define BTI_TIME_RESOLUTION 10e-9
#define BTI_SPOT_MEAN 1L

static double bti_qtime(double t)
{
    return (t <= 0.0) ? 0.0 : floor(t / BTI_TIME_RESOLUTION + 0.5) * BTI_TIME_RESOLUTION;
}

static int bti_is_ac(const char *mode)
{
    return mode && (!strcmp(mode, "AC") || !strcmp(mode, "ac"));
}

static int bti_add(int *n, double *gs, double *ge, double *ds, double *de,
                   double *ss, double *se, double *dt, long *trigger,
                   long *ssr, long *mt, double *ms, double *me,
                   double g0, double g1, double d0, double d1,
                   double s0, double s1, double t, long measure,
                   double m0, double m1)
{
    t = bti_qtime(t);
    if (*n >= BTI_MAX_SEGMENTS || t < BTI_MIN_TIME || t > BTI_MAX_TIME)
        return -11;
    gs[*n] = g0; ge[*n] = g1; ds[*n] = d0; de[*n] = d1;
    ss[*n] = s0; se[*n] = s1; dt[*n] = t;
    trigger[*n] = (*n == 0) ? 1 : 0;
    ssr[*n] = 1; mt[*n] = measure;
    ms[*n] = measure ? m0 : 0.0; me[*n] = measure ? m1 : 0.0;
    ++*n;
    return 0;
}

static int bti_hold(int *n, double *gs, double *ge, double *ds, double *de,
                    double *ss, double *se, double *dt, long *trigger,
                    long *ssr, long *mt, double *ms, double *me,
                    double gate, double duration)
{
    double part;
    while (duration > 1e-9)
    {
        part = duration > BTI_MAX_TIME ? BTI_MAX_TIME : duration;
        if (bti_add(n, gs, ge, ds, de, ss, se, dt, trigger, ssr, mt, ms, me,
                    gate, gate, 0, 0, 0, 0, part, 0, 0, 0))
            return -11;
        duration = bti_qtime(duration - part);
    }
    return 0;
}

static int bti_staircase(int *n, int *points, int steps, double start,
                         double stop, double step, double trf, double plateau,
                         double vdrain, double f0, double f1,
                         double *gs, double *ge, double *ds, double *de,
                         double *ss, double *se, double *dt, long *trigger,
                         long *ssr, long *mt, double *ms, double *me)
{
    int k, status;
    double direction = stop > start ? 1.0 : -1.0;
    double gate = start, next;

    status = bti_add(n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,
                     start,start,0,vdrain,0,0,trf,0,0,0); if(status)return status;
    status = bti_add(n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,
                     start,start,vdrain,vdrain,0,0,plateau,BTI_SPOT_MEAN,f0*plateau,f1*plateau); if(status)return status;
    ++*points;
    for (k = 0; k < steps; ++k)
    {
        next = (k == steps - 1) ? stop : start + direction * (k + 1) * step;
        status = bti_add(n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,
                         gate,next,vdrain,vdrain,0,0,trf,0,0,0); if(status)return status;
        status = bti_add(n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,
                         next,next,vdrain,vdrain,0,0,plateau,BTI_SPOT_MEAN,f0*plateau,f1*plateau); if(status)return status;
        ++*points; gate = next;
    }
    for (k = steps - 1; k >= 0; --k)
    {
        next = k ? start + direction * k * step : start;
        status = bti_add(n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,
                         gate,next,vdrain,vdrain,0,0,trf,0,0,0); if(status)return status;
        status = bti_add(n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,
                         next,next,vdrain,vdrain,0,0,plateau,BTI_SPOT_MEAN,f0*plateau,f1*plateau); if(status)return status;
        ++*points; gate = next;
    }
    return bti_add(n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,
                   start,start,vdrain,0,0,0,trf,0,0,0);
}

/* USRLIB MODULE MAIN FUNCTION */
int bias_stress(double trf,double trf2,double tplateau,double vdrain,double vgate_start,double vgate_stop,double vgate_step,double measure_start_fraction,double measure_stop_fraction,char *stress_mode,double vstress,double vstdby,double thigh,double duty_cycle,double *stress_times,int stress_times_size,double sample_rate,double voltage_range,double current_range,double dut_resistance,char *PMU_ID1,char *PMU_ID2,double *Gate_V,int Gate_V_size,double *Gate_I,int Gate_I_size,double *Drain_V,int Drain_V_size,double *Drain_I,int Drain_I_size,double *Source_V,int Source_V_size,double *Source_I,int Source_I_size,double *Time,int Time_size)
{
/* USRLIB MODULE CODE */
    double gs[BTI_MAX_SEGMENTS], ge[BTI_MAX_SEGMENTS], ds[BTI_MAX_SEGMENTS], de[BTI_MAX_SEGMENTS];
    double ss[BTI_MAX_SEGMENTS], se[BTI_MAX_SEGMENTS], dt[BTI_MAX_SEGMENTS], ms[BTI_MAX_SEGMENTS], me[BTI_MAX_SEGMENTS];
    long trigger[BTI_MAX_SEGMENTS], ssr[BTI_MAX_SEGMENTS], mt[BTI_MAX_SEGMENTS], sequence = 1;
    double loops[1] = {1.0};
    double a=bti_qtime(trf), b=bti_qtime(trf2), p=bti_qtime(tplateau), prev=0, interval;
    double span, period=0, standby=0, cycles;
    int n=0, i, k, steps, points=0, pmu1, pmu2, status, ac;

    ac = bti_is_ac(stress_mode);
    if ((!ac && (!stress_mode || (strcmp(stress_mode,"DC") && strcmp(stress_mode,"dc")))) || !PMU_ID1 || !PMU_ID2) return -1;
    if (a < 60e-9 || b < 60e-9 || p < BTI_MIN_TIME || vgate_step <= 0.0) return -2;
    span=fabs(vgate_stop-vgate_start); steps=(int)floor(span/vgate_step+.5);
    if (steps < 1 || fabs(span-steps*vgate_step)>1e-9*(1+span)) return -3;
    if (measure_start_fraction < 0 || measure_stop_fraction > 1 || measure_start_fraction >= measure_stop_fraction) return -4;
    if (!stress_times || stress_times_size < 1 || stress_times_size > 100) return -5;
    if (ac) { if (thigh<BTI_MIN_TIME || duty_cycle<=0 || duty_cycle>1) return -7; period=bti_qtime(thigh/duty_cycle); standby=bti_qtime(period-thigh-2*b); if (standby<0) return -7; }
    for(i=0;i<stress_times_size;i++) { if(stress_times[i]<0 || (i&&stress_times[i]<=stress_times[i-1])) return -5; }

    status=bti_staircase(&n,&points,steps,vgate_start,vgate_stop,vgate_step,a,p,vdrain,measure_start_fraction,measure_stop_fraction,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me); if(status)return status;
    for(i=0;i<stress_times_size;i++)
    {
        interval=bti_qtime(stress_times[i]-prev);
        if(interval>1e-9)
        {
            status=bti_add(&n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,vgate_start,ac?vstdby:vstress,0,0,0,0,b,0,0,0); if(status)return status;
            if(!ac) { status=bti_hold(&n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,vstress,interval); if(status)return status; }
            else { cycles=floor(stress_times[i]/period+.5)-(i?floor(stress_times[i-1]/period+.5):0); for(k=0;k<(int)cycles;k++){ if(bti_add(&n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,vstdby,vstress,0,0,0,0,b,0,0,0)||bti_add(&n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,vstress,vstress,0,0,0,0,thigh,0,0,0)||bti_add(&n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,vstress,vstdby,0,0,0,0,b,0,0,0)) return -11; if(standby>0&&bti_hold(&n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,vstdby,standby))return -11; } }
            status=bti_add(&n,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me,ac?vstdby:vstress,vgate_start,0,0,0,0,b,0,0,0); if(status)return status;
        }
        status=bti_staircase(&n,&points,steps,vgate_start,vgate_stop,vgate_step,a,p,vdrain,measure_start_fraction,measure_stop_fraction,gs,ge,ds,de,ss,se,dt,trigger,ssr,mt,ms,me); if(status)return status;
        prev=stress_times[i];
    }
    if(points>Gate_V_size||points>Gate_I_size||points>Drain_V_size||points>Drain_I_size||points>Source_V_size||points>Source_I_size||points>Time_size)return -8;
    getinstid(PMU_ID1,&pmu1); getinstid(PMU_ID2,&pmu2); if(pmu1==-1||pmu2==-1)return -9;
    status=rpm_config(pmu1,1,KI_RPM_PATHWAY,KI_RPM_PULSE);if(status)return status; status=rpm_config(pmu1,2,KI_RPM_PATHWAY,KI_RPM_PULSE);if(status)return status; status=rpm_config(pmu2,1,KI_RPM_PATHWAY,KI_RPM_PULSE);if(status)return status;
    status=pg2_init(pmu1,PULSE_MODE_SARB);if(status)return status; status=pg2_init(pmu2,PULSE_MODE_SARB);if(status)return status;
    pulse_load(pmu1,1,dut_resistance); pulse_load(pmu1,2,dut_resistance); pulse_load(pmu2,1,dut_resistance);
    pulse_ranges(pmu1,1,voltage_range,PULSE_MEAS_FIXED,voltage_range,PULSE_MEAS_FIXED,current_range); pulse_ranges(pmu1,2,voltage_range,PULSE_MEAS_FIXED,voltage_range,PULSE_MEAS_FIXED,current_range); pulse_ranges(pmu2,1,voltage_range,PULSE_MEAS_FIXED,voltage_range,PULSE_MEAS_FIXED,current_range);
    pulse_sample_rate(pmu1,(long)sample_rate); pulse_sample_rate(pmu2,(long)sample_rate); pulse_burst_count(pmu1,1,1); pulse_burst_count(pmu1,2,1); pulse_burst_count(pmu2,1,1);
    pulse_measrt(pmu1,1,"Gate_V","Gate_I","Time",NULL); pulse_measrt(pmu1,2,"Drain_V","Drain_I","",NULL); pulse_measrt(pmu2,1,"Source_V","Source_I","",NULL);
    status=seg_arb_sequence(pmu1,1,1,n,gs,ge,dt,trigger,ssr,mt,ms,me);if(status)return status; status=seg_arb_sequence(pmu1,2,1,n,ds,de,dt,trigger,ssr,mt,ms,me);if(status)return status; status=seg_arb_sequence(pmu2,1,1,n,ss,se,dt,trigger,ssr,mt,ms,me);if(status)return status;
    status=seg_arb_waveform(pmu1,1,1,&sequence,loops);if(status)return status; status=seg_arb_waveform(pmu1,2,1,&sequence,loops);if(status)return status; status=seg_arb_waveform(pmu2,1,1,&sequence,loops);if(status)return status;
    pulse_output(pmu1,1,1); pulse_output(pmu1,2,1); pulse_output(pmu2,1,1); status=pulse_exec(PULSE_MODE_SIMPLE);if(status)return status; while(pulse_exec_status(&interval)==1)Sleep(10);
    return 0;
/* USRLIB MODULE END */
}
