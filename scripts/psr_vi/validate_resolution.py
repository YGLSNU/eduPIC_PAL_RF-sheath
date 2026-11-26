#!/usr/bin/env python3
"""Bounded, isolated resolution checks. Never advances a research checkpoint.

Vacuum has an analytic answer. Plasma copies sample the same short transient;
their differences include MCC noise and are not stationary convergence bounds.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile

import numpy as np
import pandas as pd

from spectral import phasors, circular_error
from validate import build, sha, validate_fields

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts/brh_scan'))
from prepare import read_checkpoint, field
from common import put

FREQUENCY = 60e6
GAP = .015
EPSILON0 = 8.85418781e-12
CASES = [
    ('baseline', 481, 4000, 56000),
    ('dt_double', 481, 2000, 56000),
    ('dt_half', 481, 8000, 56000),
    ('grid_half', 961, 4000, 56000),
    ('particles_double', 481, 4000, 28000),
]


def environment(**extra):
    env = dict(os.environ)
    # Isolated tests must not inherit an unrelated voltage-input override.
    for key in ['EDUPIC_PSR_VOLTAGE_FILE', 'EDUPIC_PSR_VDC']:
        env.pop(key, None)
    return {**env, 'EDUPIC_DIAGNOSTIC_SEED': '26112660', **extra}


def execute(binary, directory, cycles, measurement, **extra):
    with (directory / 'run.log').open('w') as log:
        subprocess.run([str(binary), str(cycles)] + (['m'] if measurement else []),
                       cwd=directory, env=environment(**extra), stdout=log,
                       stderr=subprocess.STDOUT, check=True)


def adapted_input(source, dest, ng, nt, weight):
    """Preserve point positions/charge; synchronize and restagger velocities."""
    dest.mkdir(parents=True)
    head, electrons, ions = read_checkpoint(source / 'picdata.bin')
    voltage = 150 * np.cos(2 * np.pi * FREQUENCY * head[0])
    old_field = field(electrons, ions, GAP, 481, 56000, voltage)
    copies = int(56000 / weight)
    assert copies * weight == 56000
    values = [np.tile(a, (1, copies)) for a in [electrons, ions]]
    new_field = field(*values, GAP, ng, weight, voltage)
    for a, charge, mass in zip(values, [-1.60217662e-19, 1.60217662e-19],
                                [9.10938356e-31, 6.63352090e-26]):
        old_e = np.interp(a[0], np.linspace(0, GAP, 481), old_field)
        new_e = np.interp(a[0], np.linspace(0, GAP, ng), new_field)
        a[1] += charge / (2 * mass) * (old_e / (FREQUENCY * 4000)
                                              - new_e / (FREQUENCY * nt))
    np.concatenate([head, [values[0].shape[1]], values[0].ravel(),
                    [values[1].shape[1]], values[1].ravel()]).astype('<f8').tofile(dest / 'picdata.bin')
    lines = (source / 'psr_rng.txt').read_text().splitlines()
    old = lines[0].split()
    assert int(old[4]) == 481 and int(old[5]) == 4000 and int(old[6]) == 1
    assert len(lines[4:]) == electrons.shape[1]
    lines[0] = f'{head[0]:.17g} {FREQUENCY:.17g} {GAP:.17g} {weight} {ng} {nt} 1 {values[0].shape[1]}'
    (dest / 'psr_rng.txt').write_text('\n'.join(lines[:4] + lines[4:] * copies) + '\n')
    # Old finite-volume history has a different discretization. Establish a
    # fresh endpoint, discard 1 RF, then measure the same next 2 RF in all cases.
    return {'input_SHA256': sha(dest / 'picdata.bin'),
            'input_rng_SHA256': sha(dest / 'psr_rng.txt'),
            'input_RF': int(head[1]), 'copies_per_particle': copies,
            'restaggering': 'v_new(-1/2)=v_old(-1/2)+q/(2m)*(E_old*dt_old-E_new*dt_new)',
            'noise_scope': 'Clones initially share positions/optical depths; this is a weight sensitivity test, not independent seeds.'}


def vacuum_case(root, binary, nt):
    dest = root / f'vacuum_nt{nt}'
    dest.mkdir()
    np.array([0., 0., 0., 0.], dtype='<f8').tofile(dest / 'picdata.bin')
    waveform = dest / 'synthetic_voltage.dat'
    waveform.write_text('1 150 0.27\n3 12 -0.43\n64 3 0.61\n')
    execute(binary, dest, 1, True, EDUPIC_PSR_VOLTAGE_FILE=str(waveform), EDUPIC_PSR_VDC='7')
    validation = validate_fields(dest)
    a = pd.read_csv(dest / 'terminal_timeseries.csv')
    z = phasors(a.t_terminal_s, a.J_RF_Am2.to_numpy(), FREQUENCY, 64)
    voltage = phasors(a.t_terminal_s, a.V_gap_V.to_numpy(), FREQUENCY, 64)
    rows = []
    assert abs(voltage[0] - 7) < 1e-7 and abs(z[0]) < 1e-7
    for order, amplitude, phase in [(1, 150, .27), (3, 12, -.43), (64, 3, .61)]:
        exact = 1j * EPSILON0 / GAP * 2 * np.pi * FREQUENCY * order * amplitude * np.exp(1j * phase)
        discrete = exact * np.sinc(order / nt)
        assert abs(z[order] - discrete) / abs(discrete) < 1e-7
        assert abs(voltage[order] - amplitude * np.exp(1j * phase)) < 1e-7
        rows.append({'nt': nt, 'harmonic': order, 'J_peak_Am2': float(abs(z[order])),
                     'analytic_continuous_peak_Am2': float(abs(exact)),
                     'analytic_discrete_peak_Am2': float(abs(discrete)),
                     'continuous_relative_error': float(abs(z[order] - exact) / abs(exact)),
                     'discrete_relative_error': float(abs(z[order] - discrete) / abs(discrete)),
                     'phase_lead_deg': float(np.degrees(np.angle(z[order] / voltage[order])))})
    assert abs(np.mean(a.V_discrete_mid_V * a.J_RF_Am2)) < 1e-6
    put(dest / 'numerical_validation.json', validation)
    return rows


def plasma_case(root, source, name, ng, nt, weight):
    dest = root / name
    dest.mkdir()
    binary = dest / 'solver'
    command = build(binary, ng=ng, nt=nt, sub=1, weight=weight)
    warm = dest / 'discard1RF'
    provenance = adapted_input(source, warm, ng, nt, weight)
    for n in ['picdata.bin', 'psr_rng.txt']:
        shutil.copy2(warm / n, dest / ('initial_' + n))
    started = time.monotonic()
    execute(binary, warm, 1, False)
    measured = dest / 'transient2RF'
    measured.mkdir()
    for n in ['picdata.bin', 'psr_rng.txt', 'psr_state.bin']:
        shutil.copy2(warm / n, measured / n)
    execute(binary, measured, 2, True)
    validation = validate_fields(measured)
    info = (measured / 'info.txt').read_text()
    assert 'VIOLATED' not in info, f'{name}: native PIC accuracy/stability condition failed'
    a = pd.read_csv(measured / 'terminal_timeseries.csv')
    z = phasors(a.t_terminal_s, a.J_RF_Am2.to_numpy(), FREQUENCY, 64)
    v = phasors(a.t_terminal_s, a.V_gap_V.to_numpy(), FREQUENCY, 64)
    spectra = pd.DataFrame({'harmonic': np.arange(65), 'frequency_Hz': np.arange(65) * FREQUENCY,
                            'J_real_Am2': z.real, 'J_imag_Am2': z.imag,
                            'J_peak_Am2': abs(z), 'J_phase_deg': np.degrees(np.angle(z)),
                            'terminal_P_Wm2': .5 * np.real(v * z.conj())})
    spectra.loc[0, 'terminal_P_Wm2'] *= 2
    spectra.to_csv(dest / 'harmonics.csv', index=False)
    stride = []
    for step in [1, 2, 4]:
        try:
            sampled = a.iloc[::step]
            sub = phasors(sampled.t_terminal_s, sampled.J_RF_Am2.to_numpy(), FREQUENCY, 64)
            stride.append({'stride': step, 'accepted': True,
                           'max_complex_difference_over_J1': float(np.max(abs(sub - z)) / abs(z[1]))})
        except ValueError as exc:
            stride.append({'stride': step, 'accepted': False, 'reason': str(exc)})
    summary = {**provenance, 'case': name, 'grid_points': ng, 'steps_per_RF': nt,
               'weight': weight, 'compiler_command': command,
               'solver_seconds': time.monotonic() - started,
               'measurement_scope': 'Short transient RF24-25 after common saved RF22; not stationary research statistics.',
               'native_PIC_conditions_passed': True, 'numerical_identities': validation,
               'electron_power_net_Wm2': float(a.Pe_Wm2.mean()),
               'electron_power_positive_Wm2': float(a.Pe_positive_Wm2.mean()),
               'electron_power_negative_Wm2': float(a.Pe_negative_Wm2.mean()),
               'terminal_power_Wm2': float(np.mean(a.V_gap_V * a.J_RF_Am2)),
               'J1_peak_Am2': float(abs(z[1])), 'THD_J_2_64': float(np.linalg.norm(z[2:]) / abs(z[1])),
               'sampling_stride': stride}
    put(dest / 'summary.json', summary)
    print(name, 'validated', flush=True)
    return summary


def main(root, source):
    # A completed immutable checkpoint is required; never copy an active block.
    assert (source / 'block.json').exists() and (source / 'psr_rng.txt').exists()
    record = json.loads((source / 'block.json').read_text())
    assert record['RF_last'] == 22, 'This bounded comparison is explicitly scoped to RF22'
    root.mkdir(parents=True, exist_ok=False)
    put(root / 'RUNNING.json', {'pid': os.getpid(), 'source_checkpoint': str(source),
                              'source_checkpoint_SHA256': sha(source / 'picdata.bin')})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda c: plasma_case(root, source, *c), CASES))
    rows = []
    for name, ng, nt, weight in CASES[:3]:
        rows.extend(vacuum_case(root, root / name / 'solver', nt))
    pd.DataFrame(rows).to_csv(root / 'vacuum_dt_convergence.csv', index=False)
    errors = pd.DataFrame(rows).query('harmonic == 64').set_index('nt').continuous_relative_error
    assert 3.95 < errors[2000] / errors[4000] < 4.05
    assert 3.95 < errors[4000] / errors[8000] < 4.05
    baseline = pd.read_csv(root / 'baseline/harmonics.csv')
    b = baseline.J_real_Am2.to_numpy() + 1j * baseline.J_imag_Am2.to_numpy()
    comparison = []
    for result in results:
        name = result['case']
        a = pd.read_csv(root / name / 'harmonics.csv')
        z = a.J_real_Am2.to_numpy() + 1j * a.J_imag_Am2.to_numpy()
        for n in range(1, 65):
            comparison.append({'case': name, 'harmonic': n,
                               'absolute_complex_difference_Am2': abs(z[n] - b[n]),
                               'complex_difference_over_baseline_J1': abs(z[n] - b[n]) / abs(b[1]),
                               'amplitude_ratio_to_baseline': abs(z[n]) / abs(b[n]) if abs(b[n]) > 1e-6 else np.nan,
                               'phase_difference_deg': float(circular_error(np.degrees(np.angle(z[n])), np.degrees(np.angle(b[n])))) if min(abs(z[n]), abs(b[n])) > 1e-3 else np.nan})
    pd.DataFrame(comparison).to_csv(root / 'plasma_sensitivity.csv', index=False)
    summary = {'passed_numerical_identities': True, 'vacuum_analytic_dt_order': 2,
               'source_SHA256': sha(REPO / 'C/eduPIC_psr_vi.cc'),
               'header_SHA256': sha(REPO / 'C/psr_vi_diagnostics.hpp'),
               'source_checkpoint_SHA256': sha(source / 'picdata.bin'),
               'source_RF': 22, 'plasma_cases': results,
               'stationary_grid_convergence_established': False,
               'scope': 'Analytic multiharmonic vacuum, dt/grid/weight sensitivity of common short transient, and sampling-stride checks. Plasma differences include MCC stochastic divergence and clone correlations. No confidence interval or stationary PSR proof.'}
    put(root / 'resolution_validation.json', summary)
    # Small reproduction bundle: exact common input/RNG, adapted inputs, command,
    # raw terminal signals and identity checks. Large phase arrays remain local.
    with zipfile.ZipFile(root / 'validation_reproduction.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as z:
        for n in ['picdata.bin', 'psr_rng.txt', 'block.json']:
            z.write(source / n, 'common_RF22/' + n)
        for p in sorted(root.rglob('*')):
            if not p.is_file() or p.name == 'validation_reproduction.zip':
                continue
            if p.name in ['resolution_validation.json', 'summary.json', 'harmonics.csv', 'plasma_sensitivity.csv', 'vacuum_dt_convergence.csv', 'numerical_validation.json', 'psr_metadata.json', 'info.txt', 'synthetic_voltage.dat', 'initial_picdata.bin', 'initial_psr_rng.txt', 'terminal_timeseries.csv']:
                z.write(p, str(p.relative_to(root)))
    (root / 'RUNNING.json').unlink()
    print(json.dumps({'root': str(root), 'identities_passed': True, 'stationary_convergence': False}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('completed_RF22_block', type=Path)
    args = parser.parse_args()
    main(args.output.resolve(), args.completed_RF22_block.resolve())
