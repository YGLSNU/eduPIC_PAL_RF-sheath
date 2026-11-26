# eduPIC PSR / VI harmonics

Independent PSR diagnostics and execution tree. Existing 13.56MHz BRH calculations remain on their original source/controller.

**Requested run:** Ar20mTorr,350K,gap15mm,60MHz,150V **peak**, upper RF/lower ground; equal-area1D3V electrostatic PIC/MCC, absorbing walls. Imposed sine, fixed DC0; no invented circuit, material reflection, SEE or empirical PSR force/heating.

- [PSR results, plots and downloads](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/tree/results/20mTorr-60MHz-topRF)
- [Definitions, limitations, validation and exact commands](scripts/psr_vi/METHOD.md)
- Solver: [C/eduPIC_psr_vi.cc](C/eduPIC_psr_vi.cc), [passive diagnostics](C/psr_vi_diagnostics.hpp)
- [Original BRH results](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/tree/results/20mTorr-topRF)

## Implemented

1. Finite-volume CIC continuity current plus displacement current; independently checked using particle Ramo displacement and RF electrode-charge balance. RF-to-plasma is positive. Production ions update each electron step.
2. Actual terminal/force timestamps, raw terminal/sheath/midgap signals, signed instantaneous electron power, positive/negative contributions and exact field-kick checks.
3. Peak/RMS/DC phasors, normalized amplitudes/dBc/THD, circular phases, V/J ratios and harmonic powers through configurable order64. Per-block complex products, full Hz spectra and unresolved power remainder are retained.
4. Integral sheath edges, phase-colored Q-V, scaled polynomial residuals and approximate LC frequencies, retaining invalid states as NaN.
5. Synchronized PSR diagnostics with raw and filtered currents. No automatic PSR or heating-gain declaration by a peak alone.
6. CSV/TSV experiment importer, phase/amplitude/reference-plane metadata and empty templates. No experiment was supplied; A_eff and external circuit are unknown.
7. Recoverable controller,20RF blocks, stationary/uncertainty gates, verified lossless compression and audited GitHub publication with report/restart readback.

## Validation scope

Analytic synthetic phasor/DC/power tests, a vacuum capacitor and small isolated two-RF plasma copies were run. The vacuum current leads by90degrees and matches epsilon0*omega*V/L. Diagnostic on/off and continuous/split restarts preserve particle/RNG output byte-for-byte. N_SUB=40 is compared but excluded from primary HF inference.

These tests do not establish stationary production results or full grid/particle/seed convergence. The requested run is in progress; early two-RF plots are marked transient and excluded from normal measurements. RF caps are never labeled full convergence. Ideal sine terminal voltage harmonics n>1 are zero by boundary condition; internal harmonic power is diagnosed separately.
