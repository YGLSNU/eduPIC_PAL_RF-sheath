"""RF-duration-weighted block summaries; variation is not total numerical error."""
import numpy as np
import pandas as pd


def moments(values, weights):
    """Unbiased weighted block scatter and an exploratory 2.3*SE indicator."""
    values = np.asarray(values)
    weights = np.asarray(weights, dtype=float)
    if values.shape[0] != len(weights) or not np.all(np.isfinite(weights)) or np.any(weights <= 0):
        raise ValueError('Positive finite RF durations required for every block')
    mean = np.average(values, weights=weights, axis=0)
    effective = weights.sum() ** 2 / np.sum(weights ** 2)
    if len(weights) < 2:
        scatter = np.full(np.shape(mean), np.nan)
    else:
        shape = (len(weights),) + (1,) * (values.ndim - 1)
        denominator = weights.sum() - np.sum(weights ** 2) / weights.sum()
        scatter = np.sqrt(np.sum(weights.reshape(shape) * abs(values - mean) ** 2, axis=0) / denominator)
    return mean, scatter, 2.3 * scatter / np.sqrt(effective), effective


def summarize(tables, RF_durations):
    """Average common-time-origin phasors, preserving mean per-block powers."""
    if not tables:
        raise ValueError('At least one complete block required')
    frames = [table.sort_values('harmonic').reset_index(drop=True) for table in tables]
    first = frames[0]
    if not np.array_equal(first.harmonic, np.arange(len(first))) or len(first) < 2:
        raise ValueError('Contiguous DC and positive harmonic orders required')
    for table in frames:
        if not np.array_equal(first.harmonic, table.harmonic) or not np.allclose(first.frequency_Hz, table.frequency_Hz, rtol=1e-10, atol=1e-6):
            raise ValueError('Blocks must share harmonic orders and physical frequencies')
    weights = np.asarray(RF_durations, dtype=float)
    J = np.array([a.J_real_Am2.to_numpy() + 1j * a.J_imag_Am2.to_numpy() for a in frames])
    V = np.array([a.V_real_V.to_numpy() + 1j * a.V_imag_V.to_numpy() for a in frames])
    jm, js, jw, effective = moments(J, weights)
    vm, vs, vw, _ = moments(V, weights)
    noise = np.average(np.array([a.J_noise_floor_Am2 for a in frames]), weights=weights, axis=0)
    n = first.harmonic.to_numpy()
    j_valid = (n > 0) & (abs(jm) > noise) & ((~np.isfinite(jw)) | (jw < abs(jm)))
    v_valid = (n > 0) & (abs(vm) > max(1e-9, 1e-8 * abs(vm[1])))
    vi_valid = j_valid & v_valid
    phase_width = np.full(len(n), np.nan)
    use = j_valid & np.isfinite(jw) & (abs(jm) > jw)
    phase_width[use] = np.degrees(np.arcsin(jw[use] / abs(jm[use])))
    resolved = (n > 0) & np.isfinite(jw) & (abs(jm) > np.maximum(noise, 3 * jw))
    reference = np.angle(vm[1])
    phase = np.where(j_valid, np.degrees(np.angle(jm)), np.nan)
    aligned = np.where(j_valid & bool(v_valid[1]), np.degrees(np.angle(np.exp(1j * (np.angle(jm) - n * reference)))), np.nan)
    p, pstd, pwidth, _ = moments(np.array([a.terminal_P_Wm2.to_numpy() for a in frames]), weights)
    z = np.full(len(n), complex(np.nan, np.nan))
    z[vi_valid] = vm[vi_valid] / jm[vi_valid]
    return pd.DataFrame({
        'harmonic': n, 'frequency_Hz': first.frequency_Hz,
        'blocks': len(frames), 'total_RF': weights.sum(), 'effective_blocks': effective,
        'J_complex_mean_real_Am2': jm.real, 'J_complex_mean_imag_Am2': jm.imag,
        'J_coherent_mean_peak_Am2': abs(jm),
        'J_block_peak_mean_Am2': np.average(abs(J), weights=weights, axis=0),
        'J_complex_std_Am2': js, 'J_variation_indicator_Am2': jw,
        'J_mean_phase_deg': phase, 'J_aligned_phase_deg': aligned,
        'J_phase_variation_indicator_deg': phase_width, 'J_phase_valid': j_valid,
        'J_statistically_resolved': resolved, 'J_noise_floor_Am2': noise,
        'J_DC_mean_Am2': np.where(n == 0, jm.real, np.nan),
        'V_complex_mean_real_V': vm.real, 'V_complex_mean_imag_V': vm.imag,
        'V_coherent_mean_peak_V': abs(vm), 'V_complex_std_V': vs,
        'V_variation_indicator_V': vw,
        'V_mean_phase_deg': np.where(v_valid, np.degrees(np.angle(vm)), np.nan),
        'V_DC_mean_V': np.where(n == 0, vm.real, np.nan),
        'Delta_phi_VI_deg': np.where(vi_valid, np.degrees(np.angle(vm * jm.conj())), np.nan),
        'VI_phase_valid': vi_valid,
        'Z_app_of_mean_phasors_real_ohmm2': z.real, 'Z_app_of_mean_phasors_imag_ohmm2': z.imag,
        # Products are formed before averaging; covariance is retained.
        'terminal_P_mean_Wm2': p, 'terminal_P_block_std_Wm2': pstd,
        'terminal_P_variation_indicator_Wm2': pwidth,
    })
