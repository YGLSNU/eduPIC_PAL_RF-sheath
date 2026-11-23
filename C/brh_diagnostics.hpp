// Passive diagnostics for eduPIC (GPL-3.0, same license as the solver).
// No random draws and no writes to physical particle/field arrays.
#pragma once
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <vector>

namespace brh {
const int NP=200, NX=20, NE=271, STRIDE=16;
struct Encounter {
    bool valid; uint64_t seq; double t,turn,W,C,K; uint64_t n[3];
};
struct Track {
    uint64_t uid,parent,seq,n[3];
    double W,C,oldx,oldv,entry_t,entry_W,entry_C,entry_K,entry_Ex,turn,turn_ratio;
    int pending,streak[2]; bool turned;
    Encounter last[2];
};
struct Slot {uint64_t uid,parent; int track;};
std::vector<Slot> slots(MAX_N_P);
std::vector<Track> tracks;
std::vector<int> free_tracks;
uint64_t next_uid=1, kicks=0, sampled_kicks=0, hist_overflow=0, hist_samples=0;
double start_time=0, epoch_start_time=0, sample_work_eV=0, all_work_eV=0, max_ledger_error=0;
double min_sheath_ratio=.8, ref_fraction=.25;
int current_step=0,phase_bin=0;
std::vector<double> work_map(N_G*NP,0.);
std::vector<uint64_t> hist_E(NX*NP*2*NE,0),hist_Ex(NX*NP*2*NE,0);
FILE *encounters=nullptr,*returns=nullptr,*trajectories=nullptr,*probes=nullptr,*wall=nullptr;

uint64_t hash(uint64_t x) {x+=0x9e3779b97f4a7c15ULL;x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;x=(x^(x>>27))*0x94d049bb133111ebULL;return x^(x>>31);}
double K(double vx,double vy,double vz){return .5*E_MASS/EV_TO_J*(vx*vx+vy*vy+vz*vz);}
double phase(double time){double a=time/PERIOD;return a-floor(a);}
void fail(const char *s){fprintf(stderr,"BRH diagnostic error: %s\n",s);exit(5);}
int energy_bin(double E) {
    if(E<0 || !std::isfinite(E))fail("nonfinite energy");
    if(E<10)return std::min(99,int(E*10));
    if(E<100)return 100+int(E-10);
    if(E<500)return 190+int((E-100)/5);
    return 270;
}
void birth(int k,uint64_t parent) {
    Slot &s=slots[k];s.uid=next_uid++;s.parent=parent;s.track=-1;
    if(hash(s.uid)%STRIDE)return;
    int index;
    if(free_tracks.empty()){index=tracks.size();tracks.push_back(Track{});}
    else{index=free_tracks.back();free_tracks.pop_back();tracks[index]=Track{};}
    s.track=index;Track &a=tracks[index];a.uid=s.uid;a.parent=parent;a.pending=-1;
}
void remove(int k) {
    if(measurement_mode && wall)fprintf(wall,"%llu,%llu,%.16g,%d,%.12g\n",(unsigned long long)slots[k].uid,(unsigned long long)slots[k].parent,Time,x_e[k]>L?1:0,K(vx_e[k],vy_e[k],vz_e[k]));
    if(slots[k].track>=0)free_tracks.push_back(slots[k].track);
    slots[k]=slots[N_e-1];
}
template<class T>void write(std::ostream &o,const T &v){o.write(reinterpret_cast<const char*>(&v),sizeof(v));}
template<class T>void read(std::istream &o,T &v){o.read(reinterpret_cast<char*>(&v),sizeof(v));}
template<class T>void write_vec(std::ostream &o,const std::vector<T> &v,size_t n){uint64_t z=n;write(o,z);if(n)o.write(reinterpret_cast<const char*>(v.data()),sizeof(T)*n);}
template<class T>void read_vec(std::istream &o,std::vector<T> &v,size_t limit){uint64_t n;read(o,n);if(n>limit)fail("state vector exceeds limit");v.resize(n);if(n)o.read(reinterpret_cast<char*>(v.data()),sizeof(T)*n);}

void initialize() {
    start_time=Time;
    epoch_start_time=Time;
    if(const char *s=getenv("EDUPIC_BRH_MEASUREMENT_START_S"))epoch_start_time=atof(s);
    if(const char *s=getenv("EDUPIC_BRH_REFERENCE_FRACTION"))ref_fraction=atof(s);
    if(!(ref_fraction>.1 && ref_fraction<.45))fail("reference plane outside (0.1,0.45)");
    std::ifstream state("brh_state.bin",std::ios::binary);
    if(state) {
        uint64_t magic,n,ng,nt;double saved_time,gap,w,rf;
        read(state,magic);read(state,n);read(state,ng);read(state,nt);read(state,saved_time);read(state,gap);read(state,w);read(state,rf);
        if(magic!=0x4252483230323630ULL || n!=uint64_t(N_e) || ng!=N_G || nt!=N_T || saved_time!=Time || gap!=L || w!=WEIGHT || rf!=ref_fraction)fail("restart companion does not match checkpoint/config");
        read(state,next_uid);std::vector<Slot> a;read_vec(state,a,MAX_N_P);if(a.size()!=size_t(N_e))fail("slot count");std::copy(a.begin(),a.end(),slots.begin());
        read_vec(state,tracks,MAX_N_P);read_vec(state,free_tracks,MAX_N_P);
        state.read(reinterpret_cast<char*>(collision_optical_depth_e),sizeof(double)*N_e);
        if(!state)fail("truncated particle tag state");
        std::ifstream rng("brh_rng.txt");rng>>MTgen>>RMB>>R01;
        if(!rng)fail("missing or invalid RNG companion");
    } else for(int k=0;k<N_e;k++)birth(k,0);
    if(!measurement_mode)return;
    encounters=fopen("brh_encounters.csv","w");returns=fopen("brh_roundtrips.csv","w");trajectories=fopen("brh_trajectories.csv","w");probes=fopen("brh_probes.csv","w");wall=fopen("brh_wall_e.csv","w");
    if(!encounters||!returns||!trajectories||!probes||!wall)fail("cannot open diagnostic output");
    fprintf(encounters,"uid,parent,sequence,side,entry_t_s,turn_t_s,exit_t_s,entry_E_eV,entry_Ex_eV,exit_K_staggered_eV,exit_Ex_staggered_eV,W_field_eV,dK_collision_parent_eV,turn_ne_over_ni\n");
    fprintf(returns,"uid,side,start_t_s,end_t_s,tau_RF,start_phase,end_phase,turn_start_phase,turn_end_phase,W_field_eV,dK_collision_parent_eV,dK_staggered_eV,n_elastic,n_excitation,n_ionization,near_fundamental,consecutive_returns,ledger_residual_eV\n");
    fprintf(trajectories,"uid,t_s,x_m,vx_staggered_ms,E_staggered_eV,W_cumulative_eV,C_parent_cumulative_eV\n");
    fprintf(probes,"t_s,x_m,E_Vm,ne_m3,ni_m3,potential_V\n");
    fprintf(wall,"uid,parent,t_s,side,E_staggered_eV\n");
}
void step(int t){
    current_step=t;phase_bin=t/N_BIN;
    if(measurement_mode && t%8==0)for(int q=1;q<=3;q++) {
        int p=q*(N_G-1)/4;
        fprintf(probes,"%.16g,%.9g,%.9g,%.9g,%.9g,%.9g\n",Time,p*DX,efield[p],e_density[p],i_density[p],pot[p]);
    }
}
void sample(int k,int p,double c1,double c2,double Efield) {
    Slot &s=slots[k];
    if(measurement_mode && current_step%N_BIN==N_BIN/2) {
        double vx=vx_e[k]-.5*Efield*DT_E/E_MASS*E_CHARGE;
        int ix=std::min(NX-1,int(x_e[k]/L*NX)),direction=vx>=0?1:0;
        size_t offset=((ix*NP+phase_bin)*2+direction)*NE;
        double E=K(vx,vy_e[k],vz_e[k]),Ex=K(vx,0,0);
        hist_E[offset+energy_bin(E)]++;hist_Ex[offset+energy_bin(Ex)]++;hist_samples++;if(E>=500)hist_overflow++;
    }
    if(s.track<0)return;
    Track &a=tracks[s.track];a.oldx=x_e[k];a.oldv=vx_e[k];
    // Reference-plane entry is detected after the position push. Store a
    // synchronized incoming energy from this force evaluation.
    double nextx=x_e[k]+(vx_e[k]-Efield*DT_E/E_MASS*E_CHARGE)*DT_E;
    for(int side=0;side<2;side++) {
        double plane=(side?1-ref_fraction:ref_fraction)*L;
        if((!side && x_e[k]>=plane && nextx<plane) || (side && x_e[k]<=plane && nextx>plane)) {
            a.pending=side;a.turned=false;a.entry_t=Time;a.entry_W=a.W;a.entry_C=a.C;
            double vx=vx_e[k]-.5*Efield*DT_E/E_MASS*E_CHARGE;
            a.entry_K=K(vx,vy_e[k],vz_e[k]);a.entry_Ex=K(vx,0,0);
        }
    }
}
void encounter(int k,int side) {
    Track &a=tracks[slots[k].track];a.seq++;
    Encounter current={};current.valid=true;current.seq=a.seq;current.t=Time+DT_E;current.turn=a.turn;
    current.W=a.W;current.C=a.C;current.K=K(vx_e[k],vy_e[k],vz_e[k]);for(int q=0;q<3;q++)current.n[q]=a.n[q];
    if(measurement_mode && a.entry_t>=epoch_start_time) {
        fprintf(encounters,"%llu,%llu,%llu,%d,%.16g,%.16g,%.16g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.9g\n",(unsigned long long)a.uid,(unsigned long long)a.parent,(unsigned long long)a.seq,side,a.entry_t,a.turn,current.t,a.entry_K,a.entry_Ex,current.K,K(vx_e[k],0,0),a.W-a.entry_W,a.C-a.entry_C,a.turn_ratio);
    }
    Encounter &old=a.last[side];
    if(old.valid && a.last[1-side].valid && a.last[1-side].seq>old.seq) {
        double tau=(current.t-old.t)/PERIOD,W=current.W-old.W,C=current.C-old.C,dK=current.K-old.K;
        double residual=dK-W-C;bool near=fabs(tau-1)<=.1;a.streak[side]=near?a.streak[side]+1:0;
        if(measurement_mode && old.t>=epoch_start_time) {
            max_ledger_error=std::max(max_ledger_error,fabs(residual));
            fprintf(returns,"%llu,%d,%.16g,%.16g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%llu,%llu,%llu,%d,%d,%.12g\n",(unsigned long long)a.uid,side,old.t,current.t,tau,phase(old.t),phase(current.t),phase(old.turn),phase(current.turn),W,C,dK,(unsigned long long)(current.n[0]-old.n[0]),(unsigned long long)(current.n[1]-old.n[1]),(unsigned long long)(current.n[2]-old.n[2]),near?1:0,a.streak[side],residual);
        }
    } else a.streak[side]=0;
    old=current;a.pending=-1;a.turned=false;
}
void push(int k,int p,double c1,double c2,double oldvx) {
    double W=.5*E_MASS/EV_TO_J*(vx_e[k]-oldvx)*(vx_e[k]+oldvx);
    if(measurement_mode) {
        all_work_eV+=W;kicks++;
        work_map[p*NP+phase_bin]+=c1*W;work_map[(p+1)*NP+phase_bin]+=c2*W;
    }
    if(slots[k].track<0)return;
    Track &a=tracks[slots[k].track];a.W+=W;
    if(measurement_mode){sample_work_eV+=W;sampled_kicks++;}
    // Only an electric-field kick can qualify a turn. MCC-induced reversals
    // alone cannot create a sheath encounter, but all intervening MCC are kept.
    if(a.pending>=0 && !a.turned) {
        int side=a.pending;double ne=c1*e_density[p]+c2*e_density[p+1],ni=c1*i_density[p]+c2*i_density[p+1];
        bool reversal=side?(oldvx>0 && vx_e[k]<=0):(oldvx<0 && vx_e[k]>=0);
        bool region=side?x_e[k]>(1-ref_fraction)*L:x_e[k]<ref_fraction*L;
        if(reversal && region && ni>0 && ne/ni<min_sheath_ratio) {
            a.turned=true;a.turn=Time-.5*DT_E+DT_E*(-oldvx)/(vx_e[k]-oldvx);a.turn_ratio=ne/ni;
        }
    }
    double newx=x_e[k]+vx_e[k]*DT_E;
    if(a.pending>=0) {
        int side=a.pending;double plane=(side?1-ref_fraction:ref_fraction)*L;
        bool out=side?(x_e[k]>plane && newx<=plane):(x_e[k]<plane && newx>=plane);
        if(out){if(a.turned)encounter(k,side);else{a.pending=-1;a.turned=false;a.streak[side]=0;}}
    }
    // A small deterministic independent UID subsample illustrates paths only.
    if(measurement_mode && hash(a.uid)%1024==0 && current_step%16==0 && Time-start_time<5*PERIOD)
        fprintf(trajectories,"%llu,%.16g,%.9g,%.9g,%.12g,%.12g,%.12g\n",(unsigned long long)a.uid,Time,x_e[k],vx_e[k],K(vx_e[k],vy_e[k],vz_e[k]),a.W,a.C);
}
void collision(int k,int old_N,int process,double K_before) {
    int tr=slots[k].track;
    if(tr>=0){Track &a=tracks[tr];a.C+=K(vx_e[k],vy_e[k],vz_e[k])-K_before;a.n[process]++;}
    for(int j=old_N;j<N_e;j++)birth(j,slots[k].uid);
}
void save() {
    std::ofstream state("brh_state.bin",std::ios::binary);uint64_t magic=0x4252483230323630ULL,n=N_e,ng=N_G,nt=N_T;
    write(state,magic);write(state,n);write(state,ng);write(state,nt);write(state,Time);write(state,L);write(state,WEIGHT);write(state,ref_fraction);write(state,next_uid);
    write_vec(state,slots,N_e);write_vec(state,tracks,tracks.size());write_vec(state,free_tracks,free_tracks.size());
    state.write(reinterpret_cast<const char*>(collision_optical_depth_e),sizeof(double)*N_e);state.close();if(!state)fail("state save failed");
    std::ofstream rng("brh_rng.txt");rng<<std::setprecision(17)<<MTgen<<'\n'<<RMB<<'\n'<<R01<<'\n';rng.close();if(!rng)fail("RNG save failed");
    if(!measurement_mode)return;
    for(FILE *f:{encounters,returns,trajectories,probes,wall})fclose(f);
    // Native-endian f64/u64; dimensions, units, and overflow described below.
    std::ofstream wm("brh_work_sum_eV.bin",std::ios::binary);wm.write(reinterpret_cast<char*>(work_map.data()),sizeof(double)*work_map.size());
    std::ofstream he("brh_hist_E_counts.bin",std::ios::binary);he.write(reinterpret_cast<char*>(hist_E.data()),sizeof(uint64_t)*hist_E.size());
    std::ofstream hx("brh_hist_Ex_counts.bin",std::ios::binary);hx.write(reinterpret_cast<char*>(hist_Ex.data()),sizeof(uint64_t)*hist_Ex.size());
    std::ofstream out("brh_meta.json");out<<std::setprecision(17)
      <<"{\n\"schema_version\":1,\"sample_stride\":"<<STRIDE<<",\"reference_fraction\":"<<ref_fraction<<",\"turn_ne_ni_max\":"<<min_sheath_ratio
      <<",\"measurement_start_s\":"<<start_time<<",\"epoch_start_s\":"<<epoch_start_time<<",\"measurement_end_s\":"<<Time<<",\"RF_last\":"<<cycles_done
      <<",\"grid_points\":"<<N_G<<",\"phase_bins\":"<<NP<<",\"hist_shape\":["<<NX<<","<<NP<<",2,"<<NE<<"],\"hist_total_samples\":"<<hist_samples<<",\"hist_E_overflow_samples\":"<<hist_overflow
      <<",\"all_fieldwork_eV\":"<<all_work_eV<<",\"sample_fieldwork_eV\":"<<sample_work_eV<<",\"all_kicks\":"<<kicks<<",\"sample_kicks\":"<<sampled_kicks
      <<",\"maximum_return_energy_ledger_residual_eV\":"<<max_ledger_error
      <<",\"hist_energy_edges\":\"0:0.1:10,11:1:100,105:5:500; last bin >=500 eV\",\"hist_velocity\":\"native synchronized v at force evaluation, stratified one time sample per RF phase bin\",\"return_energy\":\"staggered velocity; exact field-kick/parent-collision ledger\",\"return_selection\":\"both qualified sheath encounters between same-side outward reference-plane crossings; independent of energy-gain sign\"}\n";
}
} // namespace brh
