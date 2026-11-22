"""Read-only diagnostics and explicit approximate stopping indicators for eduPIC."""
from pathlib import Path
import hashlib
import json
import re
import struct
import numpy as np
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parent
KEY = ROOT.name
XT = ['pot', 'efield', 'ne', 'ni', 'je', 'ji', 'powere', 'poweri', 'meanee', 'meanei', 'ioniz']
SOURCE_SHA = '7c7679c0f0c98844940ea911bbb7581ec33f818e8d14427c9837ffdcf1ecea41'
X = np.linspace(0, .025, 400)

def save_json(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temp.replace(path)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def checkpoint(path):
    b = Path(path).read_bytes()
    time_s, cycle, ne = struct.unpack_from('<ddd', b)
    assert ne == int(ne) and 0 < ne <= 1000000
    ni = struct.unpack_from('<d', b, 24 + 32 * int(ne))[0]
    assert ni == int(ni) and 0 < ni <= 1000000
    assert len(b) == 32 + 32 * (ne + ni)
    assert cycle == int(cycle) and abs(time_s - cycle / 13.56e6) < 1e-10
    values = np.frombuffer(b, dtype='<f8')
    assert np.isfinite(values).all()
    xe = values[3:3+int(ne)]
    xi = values[4+4*int(ne):4+4*int(ne)+int(ni)]
    assert ((xe >= 0) & (xe <= .025)).all()
    assert ((xi >= 0) & (xi <= .025)).all()
    return dict(cycle=int(cycle), time_seconds=time_s, electrons=int(ne), ions=int(ni), sha256=hashlib.sha256(b).hexdigest())

def complete_blocks(root=ROOT):
    return sorted(p.parent for p in (root/'blocks').glob('*/block.json'))

def read_arrays(path):
    a = {name: np.loadtxt(path/(name+'_xt.dat')) for name in XT}
    for name in ['density', 'eepf', 'ifed', 'conv']:
        a[name] = np.loadtxt(path/(name+'.dat'), ndmin=2)
    return a

def validate_block(path, start, count):
    a = read_arrays(path)
    for name in XT:
        assert a[name].shape == (400, 200), name
    for name, shape in [('density',(400,3)), ('eepf',(2000,2)), ('ifed',(200,3)), ('conv',(count,3))]:
        assert a[name].shape == shape, (name, a[name].shape)
    assert all(np.isfinite(v).all() for v in a.values())
    assert np.array_equal(a['conv'][:,0], np.arange(start, start+count))
    cp = checkpoint(path/'picdata.bin')
    assert cp['cycle'] == start + count - 1
    assert np.array_equal(a['conv'][-1,1:], [cp['electrons'], cp['ions']])
    info = (path/'info.txt').read_text()
    assert 'VIOLATED' not in info
    assert int(re.search(r'cycles in this run\s*=\s*(\d+)', info)[1]) == count
    patterns = [
        ('omega_pe_dt',r'Plasma frequency @ center \* DT_E\s*=\s*([\d.eE+-]+)', .2),
        ('dx_lambda_D',r'DX / Debye length @ center\s*=\s*([\d.eE+-]+)', 1.),
        ('nu_e_dt',r'Max\. electron coll\. frequency \* DT_E\s*=\s*([\d.eE+-]+)', .05),
        ('nu_i_dt',r'Max\. ion coll\. frequency \* DT_I\s*=\s*([\d.eE+-]+)', .05)]
    stability = {}
    for name, pattern, limit in patterns:
        value = float(re.search(pattern, info)[1])
        assert value < limit, name
        stability[name] = dict(value=value, limit=limit, passed=True)
    for s, col in [('e',1), ('i',2)]:
        assert np.allclose(a['n'+s].mean(axis=1), a['density'][:,col], rtol=2e-6)
        assert np.allclose(a['power'+s], a['j'+s]*a['efield'], rtol=3e-6, atol=.003)
    assert np.allclose(a['density'][:,0], X, atol=5.1e-6, rtol=0)
    eepf_norm = float(np.sum(a['eepf'][:,1]*np.sqrt(a['eepf'][:,0]))*.05)
    ifed_norm = a['ifed'][:,1:].sum(axis=0)
    assert abs(eepf_norm-1) < 2e-5
    assert np.allclose(ifed_norm, 1, atol=2e-5, rtol=0)
    cfl = float(re.search(r'Max e- energy for CFL condition\s*=\s*([\d.eE+-]+)', info)[1])
    tail = float(a['eepf'][a['eepf'][:,0] >= cfl,1].max())
    return dict(all_arrays_finite=True, expected_shapes=True, phase_mean_density_consistent=True,
                binned_jE_consistent=True, stability=stability, eepf_normalization=eepf_norm,
                ifed_normalizations=ifed_norm.tolist(), cfl_energy_eV=cfl,
                center_eepf_max_above_cfl=tail, center_eepf_tail_below_1e_6=tail<=1e-6), cp

def coarse(a):
    return a.reshape(40,10,40,5).mean(axis=(1,3))

def observables(pool):
    out = {}
    for s in ['e','i']:
        n = pool['n'+s].mean(axis=1)
        out['mean_density_'+s] = np.trapezoid(n, X)/.025
        out['center_density_'+s] = n[(X > .45*.025)&(X < .55*.025)].mean()
        out['density_profile_'+s] = n
        p = pool['j'+s]*pool['efield']
        out['mean_power_'+s] = p.mean()
        out['heating_map_'+s] = coarse(p)
    return out

def _indicators(stacks):
    """Delete-one jackknife, with a conservative positive-ACF inflation heuristic."""
    n = len(stacks['ne'])
    means = {k:v.mean(axis=0) for k,v in stacks.items()}
    obs = observables(means)
    leave = [observables({k:(v.sum(axis=0)-v[i])/(n-1) for k,v in stacks.items()}) for i in range(n)]
    indicators = {}
    for key, estimate in obs.items():
        samples = np.array([q[key] for q in leave])
        pseudo = n*np.asarray(estimate) - (n-1)*samples
        deviations = pseudo - pseudo.mean(axis=0)
        denom = float(np.sum(deviations*deviations))
        rhos = []
        if denom > 0:
            # Initial positive sequence, limited by the small available sample size.
            for lag in range(1, min(4, n//2)+1):
                rho = float(np.sum(deviations[:-lag]*deviations[lag:])/denom)
                if rho <= 0:
                    break
                rhos.append(rho)
        inflation = float(np.sqrt(1+2*sum(rhos)))
        half = student_t.ppf(.975, n-1) * pseudo.std(axis=0, ddof=1)/np.sqrt(n) * inflation
        scale = float(np.linalg.norm(np.asarray(estimate).ravel()))
        ratio = float(np.linalg.norm(np.asarray(half).ravel())/max(scale,1e-300))
        indicators[key] = dict(relative_uncertainty_indicator=ratio,
                               positive_acf_inflation=inflation,
                               positive_autocorrelations=rhos, block_samples=n)
        if np.ndim(estimate) == 0:
            indicators[key].update(estimate=float(estimate), half_width=float(half))
    return obs, indicators

def assess(root=ROOT):
    criteria = json.loads((root/'criteria.json').read_text())
    blocks = complete_blocks(root)
    n = len(blocks)
    count = n*criteria['block_cycles']
    base = dict(measurement_cycles=count, completed_blocks=n,
                minimum_measurement_cycles=criteria['minimum_measurement_cycles'],
                criteria_file='criteria.json', passed=False,
                note='Approximate exploratory stopping indicators; not guaranteed total error or simultaneous 95% coverage.')
    if n < 2:
        return {**base, 'reason':'insufficient_blocks'}
    fields = ['ne','ni','je','ji','efield']
    stacks = {key:np.array([np.loadtxt(p/(key+'_xt.dat')) for p in blocks]) for key in fields}
    obs, indicators = _indicators(stacks)
    # Longer blocks provide an additional safeguard against inter-block correlations.
    paired = None
    if n//2 >= 5:
        used = n - n%2
        paired_stacks = {k:v[:used].reshape(used//2,2,400,200).mean(axis=1) for k,v in stacks.items()}
        _, paired = _indicators(paired_stacks)
        for key in indicators:
            indicators[key]['relative_uncertainty_20_cycles'] = indicators[key]['relative_uncertainty_indicator']
            indicators[key]['relative_uncertainty_40_cycles'] = paired[key]['relative_uncertainty_indicator']
            indicators[key]['relative_uncertainty_indicator'] = max(indicators[key]['relative_uncertainty_indicator'], paired[key]['relative_uncertainty_indicator'])
            if 'half_width' in indicators[key]:
                indicators[key]['half_width'] = max(indicators[key]['half_width'], paired[key]['half_width'])
    half_n = n//2
    first = observables({k:v[:half_n].mean(axis=0) for k,v in stacks.items()})
    last = observables({k:v[-half_n:].mean(axis=0) for k,v in stacks.items()})
    for key in indicators:
        difference = np.asarray(last[key]) - np.asarray(first[key])
        rel = float(np.linalg.norm(difference.ravel()) / max(float(np.linalg.norm(np.asarray(obs[key]).ravel())),1e-300))
        tol = criteria['heating_map_relative_tolerance'] if key.startswith('heating') else criteria['mean_quantity_relative_tolerance']
        indicators[key].update(first_last_half_relative_change=rel, tolerance=tol,
                               passed=bool(rel<=tol and indicators[key]['relative_uncertainty_indicator']<=tol))
    history = [np.loadtxt(root/'history_through1705.dat', ndmin=2)]
    history.extend(np.loadtxt(p/'conv.dat', ndmin=2) for p in blocks)
    history = np.concatenate(history)
    assert np.array_equal(history[:,0], np.arange(1,1706+count))
    recent = history[-600:]
    stationary = {}
    for s, col in [('e',1),('i',2)]:
        y = recent[:,col]
        mean = y.mean()
        span = float(np.ptp(y.reshape(3,200).mean(axis=1))/mean)
        drift = float(abs(np.polyfit(np.arange(600), y,1)[0])*599/mean)
        stationary[s] = dict(block_mean_span=span, fitted_drift=drift,
                             passed=span<criteria['particle_count_block_span_tolerance'] and drift<criteria['particle_count_fitted_drift_tolerance'])
    ready = count >= criteria['minimum_measurement_cycles']
    all_passed = all(q['passed'] for q in indicators.values()) and all(q['passed'] for q in stationary.values())
    return {**base, 'ready':ready, 'passed':bool(ready and all_passed),
            'reason':'criteria_satisfied' if ready and all_passed else ('minimum_cycles_not_reached' if not ready else 'continue_sampling'),
            'indicators':indicators, 'particle_count_stationarity':stationary,
            'longer_block_check_available':paired is not None,
            'first_last_half_cycles_each':half_n*criteria['block_cycles'],
            'coarse_map_shape':criteria['coarse_map_shape']}
