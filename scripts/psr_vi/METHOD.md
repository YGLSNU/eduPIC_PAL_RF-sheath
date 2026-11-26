# eduPIC PSR / VI harmonics

This is an independent GPL-3.0 C++ solver and result flow. Existing BRH sources, running controllers, gaps and stopping criteria are unchanged. Baseline physical model: the archived `C/eduPIC_brh.cc` optical-depth Ar electron MCC and Ar+ MCC, absorbing walls, no SEE or material reflection, no binary Coulomb collisions. No empirical PSR force/heating or unprovided circuit is added.

## Requested condition and scope

Ar 20 mTorr, 350 K, gap15mm, 60MHz, 150V **peak**. Upper x=L is RF, lower x=0 ground. Ideal imposed cosine, fixed DC=0; this is a specified-voltage boundary, not a solved self-bias or matching network. The 1D equal-area model excludes sidewalls, geometrical area asymmetry, cables and external stray elements. A_sim=1e-4 m² normalizes macroparticles; A_eff is unknown. Currents are A/m² and powers W/m² or W/m³, not fitted experimental amperes/watts.

4000 electron steps/RF, 481 grid points (dx31.25µm), weight56000, **N_SUB=1**. Production initialization is a fresh preionized paired uniform e/ion seed at1e15m⁻³, electron3eV/ion350K; it is not a breakdown-voltage calculation. The changed-condition transient is excluded. Background gate: last600RF split3×200, particle-count span<1% and fitted drift<2%. Measure20RF blocks, min200RF, cap1000RF; cap is not full convergence. Resolved harmonic complex uncertainty, phase and first/last drift plus electron-power variation have separate block indicators. Native PIC accuracy/stability and discretization/seed convergence remain separate.

## Discrete current and power

Vgap=phi(L)-phi(0), positive terminal J points from RF into plasma, i.e. -x. Plasma currents retain +x. J_RF=-mean_x(j_conduction)+eps0*dVgap/dt/L. Terminal samples are at interval midpoints; potential/energy-current/power samples are at their force-evaluation time. Both timestamps are written. The derivative is finite difference; its transfer function approaches the exact derivative with dt convergence. Both analytical drive V(midpoint) and discrete average endpoint V are saved.

Continuity current is reconstructed from endpoint CIC charge changes in finite-volume cells (half volume at boundary nodes) and measured signed wall flux. Independent checks use (1) each particle's clipped displacement (Ramo weighting), (2) RF surface-charge change and arriving particle charge. Local total current includes eps0*dE/dt at the same time. This validates continuity of the existing discretization; it is not a claim of exact physical-current accuracy for an arbitrary timestep. N_SUB=40 leaves cached ion charge inconsistent with a smooth particle path; its test is flagged and not used for primary high-frequency interpretation.

Energy current uses centered kick velocity and the same CIC interpolation/volume weights as the force. Its dot product with E reproduces each species' exact field-kick kinetic-energy increment. It is distinct from the continuity/path current at finite dt. Electron power is first formed per timestep as je*E, then signed net/positive/negative parts are accumulated. The older200phase <j>*<E> output is preserved and labeled separately. Terminal work, interval-aligned kick work and electrostatic field-energy change have a reported residual; no machine-exact global energy-conserving PIC claim is made.

## Sampling and harmonic conventions

Every electron-step terminal and sheath sample is retained per block. Full grid-by-time-by-cycle data are avoided: nine fields are accumulated by RF phase with4000phase samples, preserving coherent per-block harmonics and instantaneous-power averages. Fields are binary float64[9,ng,nt], described in psr_metadata.json. Data compression is lossless and SHA256-verified. The terminal raw series and Hz-domain spectrum retain noncoherent/broadband information.

Positive orders use peak phasor X_n=(2/N)sum x(t_k)exp(-i*n*omega*t_k), DC=mean(x), RMS=peak/sqrt2. Actual timestamps determine the origin; Nyquist has its own one-sided normalization. Highest requested harmonic defaults64 and requires>=20samples/cycle plus below Nyquist; this is a sampling gate, not a convergence proof. Noncoherent samples require explicit sine/cosine fitting. No zero-padding resolution claim is made. VI phase=arg(V)-arg(J); circular errors wrap to[-180,180). Aligned phase subtracts n*phi_V1. Low-amplitude/noise-floor phases and V/J are invalid rather than arbitrarily zero.

The bounded `validate_resolution.py` check uses synthetic vacuum orders1/3/64 (including known phases and DC), verifies the exact finite-difference sinc transfer and second-order dt error, and compares requested-condition plasma copies at dt×2, dt/2, dx/2 and macroparticle weight/2. Every copy starts from the same immutable RF22 particle/RNG checkpoint, synchronizes/restaggers leapfrog velocities, discards1RF and measures RF24–25. A changed grid gets a fresh diagnostic endpoint; no research checkpoint is edited. Duplicated particles initially share positions/optical depths, so this is not independent-seed uncertainty. Current/power identities, native PIC conditions and terminal strides1/2/4 are checked. Short-transient differences include MCC noise and do not establish stationary grid/seed convergence. Research raw signals continue to be stored at stride1.

Local harmonic power=0.5*Re(jhat_n*conj(Ehat_n)), DC has no0.5. Products are formed **within each block**, then averaged across blocks. The difference between direct mean jeE and the resolved DC/integer-harmonic sum is explicitly retained as noncoherent/unresolved remainder. The ideal sine boundary has V_n=0 for n>1; terminal high-order P=0 does not exclude internal spatial redistribution/harmonic heating. Z_app is a nonlinear V/J ratio, not an independently identified linear impedance or PSR proof.

`harmonic_block_statistics.csv` combines completed blocks by RF duration. It retains signed DC, coherent complex-mean peak, mean of block peaks, absolute and V1-aligned phases, and block scatter. Angles are never averaged arithmetically across the±180° boundary. The exploratory indicator is2.3×weighted scatter/√effective_blocks, with effective_blocks=(Σw)²/Σw²; one block has unknown scatter. This is not a total-error confidence interval or an independence guarantee. Weak/noisy phases remain invalid. Power statistics retain the mean of per-block products (including covariance); RF-weighted means are separate from equal-block mean/std columns when block lengths differ. Grid, timestep and independent-seed uncertainty remain separate.

Missing regional diagnostics are not filled: a weighted region-power mean stays undefined if any included block lacks that region. The saved native2RF vs1+1RF identity check also verifies that the block-combined terminal phasor equals the continuous record and the mean terminal power retains its sign/covariance. This small numerical case is excluded from research statistics.

## Sheath and PSR interpretation

An instantaneous near-quasineutral reference is searched within the central40–60% of the gap, |ne/ni-1|<0.1. Brinkmann-type integral edges use cumulative density integrals. No root, overlapping boundaries, or no valid bulk gives valid=0/NaN, not invented positions. Bounds use the actual upper-RF geometry: sp=L-xp, sg=xg; Usp=phi(L)-phi(xp), Ub=phi(xp)-phi(xg), Usg=phi(xg)-phi(0); sum is checked. Q_s is sheath **space charge/area**, distinct from electrode surface charge. RF Usp is generally negative; Q-V drop magnitude uses -Usp.

Scaled degree1/2/3 Q-V fits report residuals; RF-colored trajectories show expansion/collapse hysteresis. Cubic local derivatives give only approximate differential capacitance, invalid for negative slope, large fit error or near collapse. Lbulk*A=(me/e²)integral dx/ne, combined with C/area, gives an area-independent approximate fLC. Validity limits and NaNs are retained. This approximate static fit is not a hysteretic circuit identification.

PSR remains **not established** by an isolated peak. Report raw terminal total J, midpoint electron energy-current, bulk voltage, sheath motion and signed jeE. A2..64f0 reconstruction may ring; raw data are retained. Stronger claims need coherent temporal evidence, grid/dt/particle/seed sensitivity and a control or explicit model for an attributed heating increment. Weak/absent PSR is a valid result. BRH and PSR are distinct mechanisms.

## Experiment interface

Empty CSV/JSON templates are intentional: no experiment was supplied. CSV/TSV column mapping, peak/RMS/peak-to-peak and common phasors or per-order VI differences are supported. A VI difference allows per-order P and Z but cannot reconstruct a full drive waveform. Measured-voltage drive needs calibrated electrode-plane voltage phases on a common time basis and an explicit DC. V is input, I is prediction; voltage agreement is excluded from prediction error. Unsupported/self-bias/circuit/DC/de-embedding information is not guessed. A_eff is required for absolute ampere comparison; normalized ratios remain usable. Measurements outside their provided band are not extrapolated.

Nonfinite phases, nonpositive supplied areas and ambiguous calibration booleans are rejected. Optional `I_noise_floor_A` and `V_noise_floor_V` are thresholds in the converted **peak** convention and invalidate weak-signal VI phases/ratios. Current normalization I_n/I_1 also requires a resolved fundamental; a weak fundamental is not replaced by an arbitrarily tiny denominator. Raw comparisons at an uncorrected probe plane retain that label; an area alone does not make them a calibrated electrode-plane validation.

## Commands

From the source branch `simulation/psr-vi`:

```bash
python -m unittest discover -s scripts/psr_vi -p 'test_psr.py' -v
python scripts/psr_vi/validate.py /workspace/work/psr-validation/new_attempt
python scripts/psr_vi/validate_resolution.py /workspace/work/psr-validation/resolution_new ROOT/warmup/RF000003-000022
python scripts/psr_vi/run.py /workspace/edupic-psr/YYMMDD_PSR_gap15_f60_V150 --prepare /workspace/work/psr-validation/new_attempt
python -u scripts/psr_vi/run.py /workspace/edupic-psr/YYMMDD_PSR_gap15_f60_V150
python scripts/psr_vi/report.py ROOT EXPORT
python scripts/results/verify_reports.py --export EXPORT
python scripts/results/publish_run.py EXPORT --branch results/20mTorr-60MHz-topRF --push
python scripts/psr_vi/compare.py harmonic_spectra.csv actual_measurement.csv metadata.json comparison.csv
```

Change YYMMDD to actual execution start in Asia/Seoul. `--prepare` refuses an existing run. Resume with the controller, using **picdata.bin + psr_rng.txt + psr_state.bin**, the same compile configuration and immutable source. Independent validation copies and synthetic signals are excluded from research statistics. Never mix production harmonic statistics with warmup or numerical-test samples.

Source/model references: [eduPIC official source](https://github.com/donkozoltan/eduPIC), [Donko et al. PSST30,095017(2021)](https://doi.org/10.1088/1361-6595/ac0b55); PSR diagnostic context: [Schungel et al. PSST24,044009(2015)](https://doi.org/10.1088/0963-0252/24/4/044009), [PoP22,043512(2015)](https://doi.org/10.1063/1.4918702). This run is not claimed as a reproduction of those papers or a calibrated VI-probe experiment.
