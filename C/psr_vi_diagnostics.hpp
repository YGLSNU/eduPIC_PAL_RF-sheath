// GPL-3.0. Passive diagnostics for the isolated eduPIC PSR/VI solver.
// Currents: +x in the plasma; positive terminal current is RF(L) -> plasma (-x).
#pragma once
#include <vector>
#include <fstream>
#include <iomanip>
#include <algorithm>
#include <cstdint>
#include <limits>
#ifndef EDUPIC_PSR_DIAGNOSTICS
#define EDUPIC_PSR_DIAGNOSTICS 1
#endif
double drive_voltage(double);
void solve_Poisson(xvector,double);
namespace psr {
const bool enabled=EDUPIC_PSR_DIAGNOSTICS;
const int NF=9;
double previous_time=0,previous_voltage=0,pending_lower=0,pending_upper=0;
double pending_re=0,pending_ri=0,ramo_e=0,ramo_i=0,pending_work=0;
double current_lower=0,current_upper=0,particle_e=0,particle_i=0;
bool have_previous=false;
std::vector<double> previous_q(N_G),previous_face(N_G+1),je(N_G),ji(N_G);
std::vector<double> phase;
uint64_t samples=0;
double max_uniform_error=0,max_ramo_error=0,max_boundary_error=0,max_kick_error=0;
double source_energy=0,grid_work=0,field_first=0,field_last=0,field_energy_previous=0;
double terminal_time=0,terminal_voltage=0,terminal_current=0,terminal_voltage_disc=0;
FILE *terminal=nullptr,*sheath=nullptr;
template<class T>void write(std::ostream&o,const T&x){o.write((const char*)&x,sizeof x);}
template<class T>void read(std::istream&o,T&x){o.read((char*)&x,sizeof x);}
void die(const char*s){fprintf(stderr,"PSR error: %s\n",s);exit(6);}
double volume(int p){return ELECTRODE_AREA*DX*((p==0||p==N_G-1)?.5:1.);}
double interp(const double*a,double x){double u=std::max(0.,std::min(double(N_G-1),x/DX));int p=std::min(N_G-2,int(u));return a[p]+(u-p)*(a[p+1]-a[p]);}
void densities(){
 std::fill(e_density,e_density+N_G,0.);std::fill(i_density,i_density+N_G,0.);
 for(int s=0;s<2;s++){double*x=s?x_i:x_e;double*d=s?i_density:e_density;int n=s?N_i:N_e;
  for(int k=0;k<n;k++){double u=x[k]/DX;int p=std::min(N_G-2,std::max(0,int(u)));d[p]+=(p+1-u)*WEIGHT/(ELECTRODE_AREA*DX);d[p+1]+=(u-p)*WEIGHT/(ELECTRODE_AREA*DX);}
  d[0]*=2;d[N_G-1]*=2;
 }
}
void initialize(){
 std::ifstream rng("psr_rng.txt");
 if(rng){double time,freq,gap,weight;int ng,nt,sub,n; rng>>time>>freq>>gap>>weight>>ng>>nt>>sub>>n;
  if(time!=Time||freq!=FREQUENCY||gap!=L||weight!=WEIGHT||ng!=N_G||nt!=N_T||sub!=N_SUB||n!=N_e)die("RNG checkpoint/config mismatch");
  rng>>MTgen>>RMB>>R01;for(int k=0;k<N_e;k++)rng>>collision_optical_depth_e[k];if(!rng)die("invalid RNG checkpoint");
 }
 if(!enabled)return;
 std::ifstream in("psr_state.bin",std::ios::binary);
 if(in){uint64_t magic;double f,l,w;int ng,nt,sub;read(in,magic);read(in,f);read(in,l);read(in,w);read(in,ng);read(in,nt);read(in,sub);
  if(magic!=0x5053525649303031ULL||f!=FREQUENCY||l!=L||w!=WEIGHT||ng!=N_G||nt!=N_T||sub!=N_SUB)die("diagnostic checkpoint/config mismatch");
  read(in,previous_time);read(in,previous_voltage);read(in,pending_lower);read(in,pending_upper);read(in,pending_re);read(in,pending_ri);read(in,pending_work);read(in,field_energy_previous);
  in.read((char*)previous_q.data(),N_G*sizeof(double));in.read((char*)previous_face.data(),(N_G+1)*sizeof(double));
  if(!in||previous_time!=Time)die("diagnostic checkpoint time/truncation mismatch");have_previous=true;
 }else{
  // Establish the initial endpoint without advancing particles or drawing RNG.
  densities();xvector rho;for(int p=0;p<N_G;p++)rho[p]=E_CHARGE*(i_density[p]-e_density[p]);solve_Poisson(rho,Time);
  previous_time=Time;previous_voltage=drive_voltage(Time);have_previous=true;
  previous_face[0]=efield[0];previous_face[N_G]=efield[N_G-1];field_energy_previous=0;
  for(int p=0;p<N_G;p++)previous_q[p]=rho[p]*volume(p)/ELECTRODE_AREA;
  for(int p=0;p<N_G-1;p++){previous_face[p+1]=-(pot[p+1]-pot[p])/DX;field_energy_previous+=.5*EPSILON0*previous_face[p+1]*previous_face[p+1]*DX;}
 }
 if(measurement_mode){
  phase.assign(size_t(NF)*N_G*N_T,0.);
  terminal=fopen("terminal_timeseries.csv","w");sheath=fopen("sheath_timeseries.csv","w");if(!terminal||!sheath)die("output open");
  fprintf(terminal,"t_terminal_s,t_field_s,V_gap_V,V_discrete_mid_V,J_RF_Am2,J_ramo_RF_Am2,J_e_path_x_Am2,J_i_path_x_Am2,J_displacement_RF_Am2,J_RF_boundary_Am2,Jtotal_x_q25_Am2,Jtotal_x_q50_Am2,Jtotal_x_q75_Am2,Pe_Wm2,Pe_positive_Wm2,Pe_negative_Wm2,Pi_Wm2,field_energy_Jm2,Pe_kick_Wm2,Pi_kick_Wm2,J_e_midgap_energy_Am2,E_midgap_Vm\n");
  fprintf(sheath,"t_s,valid,x_g_m,x_p_m,s_g_m,s_p_m,U_sp_V,U_bulk_V,U_sg_V,Q_sp_Cm2,Q_sg_Cm2,L_bulk_times_area_Hm2,voltage_sum_error_V\n");
 }
}
void save(){
 std::ofstream rng("psr_rng.txt");rng<<std::setprecision(17)<<Time<<' '<<FREQUENCY<<' '<<L<<' '<<WEIGHT<<' '<<N_G<<' '<<N_T<<' '<<N_SUB<<' '<<N_e<<'\n'<<MTgen<<'\n'<<RMB<<'\n'<<R01<<'\n';
 for(int k=0;k<N_e;k++)rng<<collision_optical_depth_e[k]<<'\n';if(!rng)die("RNG save");
 if(!enabled)return;
 std::ofstream out("psr_state.bin",std::ios::binary);uint64_t magic=0x5053525649303031ULL;write(out,magic);write(out,FREQUENCY);write(out,L);write(out,WEIGHT);write(out,N_G);write(out,N_T);write(out,N_SUB);
 write(out,previous_time);write(out,previous_voltage);write(out,pending_lower);write(out,pending_upper);write(out,pending_re);write(out,pending_ri);write(out,pending_work);write(out,field_energy_previous);
 out.write((char*)previous_q.data(),N_G*sizeof(double));out.write((char*)previous_face.data(),(N_G+1)*sizeof(double));if(!out)die("state save");
 if(terminal)fclose(terminal);if(sheath)fclose(sheath);
 if(measurement_mode&&samples){
  std::ofstream fields("phase_fields.bin",std::ios::binary);for(double &v:phase){v/=no_of_cycles;fields.write((char*)&v,sizeof v);}if(!fields)die("phase field save");
  std::ofstream meta("psr_metadata.json");meta<<std::setprecision(17)<<"{\"schema_version\":1,\"grid_points\":"<<N_G<<",\"steps_per_RF\":"<<N_T<<",\"ion_subcycling\":"<<N_SUB<<",\"frequency_Hz\":"<<FREQUENCY<<",\"gap_m\":"<<L<<",\"A_sim_m2\":"<<ELECTRODE_AREA<<",\"A_eff_m2\":null,\"weight\":"<<WEIGHT<<",\"cycles\":"<<no_of_cycles<<",\"samples\":"<<samples<<",\"field_channels\":[\"potential_V\",\"E_Vm\",\"ne_m3\",\"ni_m3\",\"je_energy_Am2\",\"ji_energy_Am2\",\"pe_Wm3\",\"pe_positive_Wm3\",\"pe_negative_Wm3\"],\"field_shape\":[9,"<<N_G<<","<<N_T<<"],\"field_phase_first\":"<<1./N_T<<",\"current_positive\":\"RF(L) to plasma (-x)\",\"current_method\":\"finite-volume endpoint-CIC continuity; independently checked against clipped particle Ramo displacement and RF surface-charge balance\",\"current_uniform_max_abs_Am2\":"<<max_uniform_error<<",\"ramo_max_abs_Am2\":"<<max_ramo_error<<",\"boundary_max_abs_Am2\":"<<max_boundary_error<<",\"kick_power_max_abs_Wm2\":"<<max_kick_error<<",\"source_work_discrete_Jm2\":"<<source_energy<<",\"grid_kick_work_Jm2\":"<<grid_work<<",\"field_energy_change_Jm2\":"<<field_last-field_first<<",\"full_energy_residual_Jm2\":"<<source_energy-grid_work-(field_last-field_first)<<",\"subcycling_current_validated_mode\":"<<(N_SUB==1?"true":"false")<<"}\n";
 }
}
double prefix_at(const std::vector<double>&v,double x){int p=std::min(N_G-2,std::max(0,int(x/DX)));double f=x/DX-p;return v[p]+f*(v[p+1]-v[p]);}
double invert(const std::vector<double>&v,double target){auto it=std::lower_bound(v.begin(),v.end(),target);if(it==v.end())return std::numeric_limits<double>::quiet_NaN();int p=int(it-v.begin());if(p==0)return 0.;double d=v[p]-v[p-1];return ((p-1)+(d>0?(target-v[p-1])/d:0))*DX;}
void measure_sheath(){
 int b=N_G/2;double best=1e9;for(int p=int(.4*(N_G-1));p<=int(.6*(N_G-1));p++)if(i_density[p]>1e10){double score=fabs(e_density[p]/i_density[p]-1)+.01*fabs(p*DX/L-.5);if(score<best){best=score;b=p;}}
 std::vector<double> ci(N_G),ce(N_G),cq(N_G),cl(N_G);
 for(int p=1;p<N_G;p++){
  ci[p]=ci[p-1]+.5*DX*(i_density[p]+i_density[p-1]);ce[p]=ce[p-1]+.5*DX*(e_density[p]+e_density[p-1]);cq[p]=E_CHARGE*(ci[p]-ce[p]);
  cl[p]=cl[p-1]+.5*DX*(1/std::max(e_density[p],1.)+1/std::max(e_density[p-1],1.));
 }
 double tg=ci[b]-ce[b],tp=(ci.back()-ci[b])-(ce.back()-ce[b]);
 bool ok=best<.1&&tg>=0&&tp>=0&&tg<=ci[b]&&tp<=ci.back()-ci[b];
 double xg=ok?invert(ci,tg):NAN,xp=ok?invert(ci,ci.back()-tp):NAN;ok=ok&&std::isfinite(xg)&&std::isfinite(xp)&&xp-xg>=4*DX;
 if(!ok){fprintf(sheath,"%.17g,0,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan\n",Time);return;}
 double pg=interp(pot,xg),pp=interp(pot,xp),usp=pot[N_G-1]-pp,ub=pp-pg,usg=pg-pot[0];
 double qs_g=prefix_at(cq,xg),qs_p=cq.back()-prefix_at(cq,xp),la=E_MASS/(E_CHARGE*E_CHARGE)*(prefix_at(cl,xp)-prefix_at(cl,xg));
 fprintf(sheath,"%.17g,1,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g\n",Time,xg,xp,xg,L-xp,usp,ub,usg,qs_p,qs_g,la,usp+ub+usg-(pot[N_G-1]-pot[0]));
}
std::vector<double> total(N_G+1);
void begin(int t){
 if(!enabled)return;
 std::fill(je.begin(),je.end(),0.);std::fill(ji.begin(),ji.end(),0.);current_lower=current_upper=particle_e=particle_i=ramo_e=ramo_i=0;
 double dt=Time-previous_time,V=drive_voltage(Time);std::vector<double> face(N_G+1),q(N_G);face[0]=efield[0];face[N_G]=efield[N_G-1];
 for(int p=0;p<N_G-1;p++)face[p+1]=-(pot[p+1]-pot[p])/DX;
 for(int p=0;p<N_G;p++)q[p]=E_CHARGE*(i_density[p]-e_density[p])*volume(p)/ELECTRODE_AREA;
 double jc=pending_lower/dt,meanjc=0;total[0]=jc+EPSILON0*(face[0]-previous_face[0])/dt;
 for(int p=0;p<N_G;p++){jc-=(q[p]-previous_q[p])/dt;total[p+1]=jc+EPSILON0*(face[p+1]-previous_face[p+1])/dt;if(p<N_G-1)meanjc+=jc/(N_G-1);}
 terminal_time=.5*(Time+previous_time);terminal_voltage=drive_voltage(terminal_time);terminal_voltage_disc=.5*(V+previous_voltage);terminal_current=-meanjc+EPSILON0/L*(V-previous_voltage)/dt;
 pending_re/=dt;pending_ri/=dt;
 if(measurement_mode){
  for(double v:total)max_uniform_error=std::max(max_uniform_error,fabs(v+terminal_current));
  max_ramo_error=std::max(max_ramo_error,fabs(terminal_current-(-pending_re-pending_ri+EPSILON0/L*(V-previous_voltage)/dt)));
  double jb=-EPSILON0*(face[N_G]-previous_face[N_G])/dt-pending_upper/dt;max_boundary_error=std::max(max_boundary_error,fabs(jb-terminal_current));
  if(!samples)field_first=field_energy_previous;
  source_energy+=terminal_voltage_disc*terminal_current*dt;grid_work+=pending_work;
  for(int p=0;p<N_G;p++){size_t k=size_t(p)*N_T+t;phase[k]+=pot[p];phase[size_t(N_G)*N_T+k]+=efield[p];phase[2*size_t(N_G)*N_T+k]+=e_density[p];phase[3*size_t(N_G)*N_T+k]+=i_density[p];}
  measure_sheath();
 }
 previous_q=q;previous_face=face;previous_time=Time;previous_voltage=V;
 field_energy_previous=0;for(int p=1;p<N_G;p++)field_energy_previous+=.5*EPSILON0*face[p]*face[p]*DX;
 field_last=field_energy_previous;
}
void particle(bool ion,int p,double c1,double c2,double oldv,double newv,double oldx,double newx){
 if(!enabled)return;double charge=(ion?1:-1)*E_CHARGE*WEIGHT;
 double j=charge*.5*(oldv+newv);std::vector<double>&a=ion?ji:je;a[p]+=c1*j/volume(p);a[p+1]+=c2*j/volume(p+1);
 double path=charge*(std::max(0.,std::min(L,newx))-oldx)/(ELECTRODE_AREA*L);
 if(ion){ramo_i+=path;particle_i+=.5*AR_MASS*WEIGHT*(newv-oldv)*(newv+oldv)/ELECTRODE_AREA;}
 else{ramo_e+=path;particle_e+=.5*E_MASS*WEIGHT*(newv-oldv)*(newv+oldv)/ELECTRODE_AREA;}
 if(newx<0)current_lower-=charge/ELECTRODE_AREA;if(newx>L)current_upper+=charge/ELECTRODE_AREA;
}
void end(int t){
 if(!enabled)return;
 if(measurement_mode){
  double pe=0,pi=0,pos=0,neg=0;
  for(int p=0;p<N_G;p++){double a=je[p]*efield[p],b=ji[p]*efield[p],dx=volume(p)/ELECTRODE_AREA;pe+=a*dx;pi+=b*dx;pos+=std::max(a,0.)*dx;neg+=std::min(a,0.)*dx;
   size_t k=size_t(p)*N_T+t;phase[4*size_t(N_G)*N_T+k]+=je[p];phase[5*size_t(N_G)*N_T+k]+=ji[p];phase[6*size_t(N_G)*N_T+k]+=a;phase[7*size_t(N_G)*N_T+k]+=std::max(a,0.);phase[8*size_t(N_G)*N_T+k]+=std::min(a,0.);
  }
  max_kick_error=std::max(max_kick_error,std::max(fabs(pe-particle_e/DT_E),fabs(pi-particle_i/DT_E)));samples++;
  double dv=EPSILON0/L*(drive_voltage(Time)-drive_voltage(Time-DT_E))/DT_E;
  fprintf(terminal,"%.17g,%.17g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g\n",terminal_time,Time,terminal_voltage,terminal_voltage_disc,terminal_current,-pending_re-pending_ri+dv,pending_re,pending_ri,dv,-total[N_G],total[N_G/4],total[N_G/2],total[3*N_G/4],pe,pos,neg,pi,field_energy_previous,particle_e/DT_E,particle_i/DT_E,je[N_G/2],efield[N_G/2]);
 }
 pending_lower=current_lower;pending_upper=current_upper;pending_re=ramo_e;pending_ri=ramo_i;pending_work=particle_e+particle_i;
}
double K(double a,double b,double c){return .5*E_MASS/EV_TO_J*(a*a+b*b+c*c);}
}
// Preserve the fork's call sites without collecting unrelated BRH trajectories.
namespace brh {
double K(double a,double b,double c){return psr::K(a,b,c);}
void initialize(){psr::initialize();}void save(){psr::save();}
void step(int){}void sample(int,int,double,double,double){}void push(int,int,double,double,double){}void remove(int){}void collision(int,int,int,double){}
}
