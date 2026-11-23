#!/usr/bin/env python3
"""Add passive hooks to the saved optical-depth reference; fail on source drift."""
from pathlib import Path
import argparse,shutil

def instrument(source):
    def replace(old,new):
        nonlocal source
        assert source.count(old)==1,(old,source.count(old))
        source=source.replace(old,new)
    replace('double sample_collision_optical_depth() {', '#include "brh_diagnostics.hpp"\n\ndouble sample_collision_optical_depth() {')
    replace('void collision_electron (double xe, double *vxe, double *vye, double *vze, int eindex){',
        'void collision_electron (double xe, double *vxe, double *vye, double *vze, int eindex){\n    const int brh_k=vxe-vx_e, brh_old_N=N_e;\n    const double brh_K_before=brh::K(*vxe,*vye,*vze);\n    int brh_process=0;')
    replace('diagnostic_excitation_events++;','diagnostic_excitation_events++;brh_process=1;')
    replace('diagnostic_ionization_events++;','diagnostic_ionization_events++;brh_process=2;')
    replace('    (*vze) = wz + F2 * gz;','    (*vze) = wz + F2 * gz;\n    brh::collision(brh_k,brh_old_N,brh_process,brh_K_before);')
    replace('        // steps 3 & 4: move particles', '        brh::step(t);\n        // steps 3 & 4: move particles')
    replace('            const double diagnostic_v_before = vx_e[k];','            brh::sample(k,p,c1,c2,e_x);\n            const double diagnostic_v_before = vx_e[k];')
    replace('            x_e[k]  += vx_e[k] * DT_E;','            brh::push(k,p,c1,c2,diagnostic_v_before);\n            x_e[k]  += vx_e[k] * DT_E;')
    replace('                x_e [k] = x_e [N_e-1];','                brh::remove(k);\n                x_e [k] = x_e [N_e-1];')
    replace('        init(N_INIT);', '        init(N_INIT);brh::initialize();')
    replace('        load_particle_data();','        load_particle_data();brh::initialize();')
    replace('    save_particle_data();','    save_particle_data();brh::save();')
    return source

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    repo=Path(__file__).resolve().parents[2]
    source=instrument((a.root/'source_control.cc').read_text())
    (a.root/'source_brh.cc').write_text(source)
    shutil.copy2(repo/'C/brh_diagnostics.hpp',a.root/'brh_diagnostics.hpp')
    (repo/'C/eduPIC_brh.cc').write_text(source)
