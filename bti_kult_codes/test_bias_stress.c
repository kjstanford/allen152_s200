/* Software-only direct waveform debugger. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#define MAX 2048
typedef struct{double t,gs,ge,ds,de,ms,me;int mt;}S;
static int add(S*a,int*n,double t,double gs,double ge,double ds,double de,int mt,double ms,double me){if(*n>=MAX||t<20e-9||t>20)return -1;a[*n]=(S){t,gs,ge,ds,de,ms,me,mt};(*n)++;return 0;}
static void staircase(S*a,int*n,int*r){int k;add(a,n,.2e-6,0,0,0,.1,0,0,0);add(a,n,10e-6,0,0,.1,.1,2e-6,8e-6,1);(*r)++;for(k=0;k<20;k++){add(a,n,.2e-6,k*.1,(k+1)*.1,.1,.1,0,0,0);add(a,n,10e-6,(k+1)*.1,(k+1)*.1,.1,.1,2e-6,8e-6,1);(*r)++;}for(k=19;k>=0;k--){double g=k?.1*k:0;add(a,n,.2e-6,(k==19?2:g),(k?g:0),.1,.1,0,0,0);add(a,n,10e-6,(k?g:0),(k?g:0),.1,.1,2e-6,8e-6,1);(*r)++;}add(a,n,.2e-6,0,0,.1,0,0,0,0);}
int main(int ac,char**av){const char*out=ac>1?av[1]:"bti_kult_codes/scratch/bti_bias_stress_debug.csv";const char*mode=ac>2?av[2]:"DC";double x[100]={0,.01,1},prev=0,dt;int nx=ac>3?ac-3:3,i,n=0,r=0;S a[MAX];FILE*f;for(i=0;i<nx;i++)if(ac>3)x[i]=strtod(av[i+3],0);staircase(a,&n,&r);for(i=0;i<nx;i++){dt=x[i]-prev;if(dt>1e-9){add(a,&n,.2e-6,0,2,0,0,0,0,0);while(dt>1e-9){double p=dt>20?20:dt;add(a,&n,p,2,2,0,0,0,0,0);dt-=p;}add(a,&n,.2e-6,2,0,0,0,0,0,0);}staircase(a,&n,&r);prev=x[i];}f=fopen(out,"w");if(!f)return 1;fprintf(f,"record_type,sequence_id,index,start_time_s,stop_time_s,duration_s,gate_start_V,gate_stop_V,drain_start_V,drain_stop_V,measure_type,measure_start_s,measure_stop_s,waveform_loops,stress_mode\n");double t=0;for(i=0;i<n;i++){fprintf(f,"segment,1,%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%d,%.17g,%.17g,,%s\n",i+1,t,t+a[i].t,a[i].t,a[i].gs,a[i].ge,a[i].ds,a[i].de,a[i].mt,a[i].ms,a[i].me,mode);t+=a[i].t;}fprintf(f,"waveform,1,1,,,,,,,,,,,1,%s\n",mode);fclose(f);printf("Wrote %d direct segments (%d spot-mean plateaus) to %s\n",n,r,out);return 0;}
