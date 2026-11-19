// Regression checks for the physical boundary and electrode diagnostics.
#define main edupic_program_main
#include "../../C/eduPIC.cc"
#undef main
#include <cassert>

int main() {
    assert(fabs(PRESSURE_PA - 2.6664473684210527) < 1e-12);
    assert(fabs(GAS_DENSITY * K_BOLTZMANN * TEMPERATURE - PRESSURE_PA) < 1e-12);
    xvector charge = {};
    for (int phase = 0; phase < 8; ++phase) {
        double time = PERIOD * phase / 8.0;
        double voltage = VOLTAGE * cos(OMEGA * time);
        solve_Poisson(charge, time);
        for (int j = 0; j < N_G; ++j) {
            assert(fabs(pot[j] - voltage * j / (N_G - 1)) < 1e-8);
            assert(fabs(efield[j] + voltage / L) < 1e-6);
        }
    }
    // Unequal left/right losses catch a swapped powered/grounded label.
    N_e = N_i = 3;
    for (int j = 0; j < 3; ++j) {
        x_e[j] = j < 2 ? 1e-10 : L - 1e-10;
        vx_e[j] = j < 2 ? -1e6 : 1e6;
        x_i[j] = j < 1 ? 1e-10 : L - 1e-10;
        vx_i[j] = j < 1 ? -1e4 : 1e4;
        vy_e[j] = vz_e[j] = vy_i[j] = vz_i[j] = 0;
    }
    datafile = tmpfile();
    assert(datafile);
    cycle = 1;
    do_one_cycle();
    fclose(datafile);
    assert(N_e == 0 && N_i == 0);
    assert(N_e_abs_gnd == 2 && N_e_abs_pow == 1);
    assert(N_i_abs_gnd == 1 && N_i_abs_pow == 2);
    double lower = 0, upper = 0;
    for (int j = 0; j < N_IFED; ++j) {
        lower += ifed_gnd[j]; upper += ifed_pow[j];
    }
    assert(lower == 1 && upper == 2);
    printf("PASS: %.0f V peak; 20 mTorr; upper powered; lower grounded; absorption and IFED labels\n", VOLTAGE);
    return 0;
}
