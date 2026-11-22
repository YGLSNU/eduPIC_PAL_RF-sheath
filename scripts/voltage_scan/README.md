# 20 mTorr voltage scan

This scan uses `C/eduPIC.cc` (compiled as C++11). The upper electrode at
`x=L=25 mm` is powered and the lower electrode at `x=0` is grounded.
Voltage values are sinusoidal peak amplitudes, not RMS or peak-to-peak.
The public pressure parameter and report use mTorr; only the internal
neutral-density calculation converts pressure to pascals.

Build each independent case with:

```sh
g++ -std=c++11 -O3 -DEDUPIC_VOLTAGE_V=100.0 C/eduPIC.cc -o edupic_100V
g++ -std=c++11 -O3 -DEDUPIC_VOLTAGE_V=250.0 C/eduPIC.cc -o edupic_250V
g++ -std=c++11 -O3 -DEDUPIC_VOLTAGE_V=300.0 C/eduPIC.cc -o edupic_300V
```

`EDUPIC_PRESSURE_MTORR` defaults to 20.0 and can also be set at compile time.
Run binaries in separate directories. `./edupic_100V 0` starts the original
1000-particle initialization; `./edupic_100V 20 m` continues an existing
`picdata.bin` by 20 RF cycles while collecting diagnostics.

For this scan the initial checkpoint is a spatial reflection of the
previous stationary 250 V case: transform every position to `L-x` and
every normal velocity to `-vx`, preserving transverse velocities and
particle weight. Reset the RF time and cycle at an integer RF phase.
This is only an initial condition; none of the previous or new transient
diagnostics are included in final averages.

`run_scan.py ROOT` runs the prepared cases independently on three CPU
workers. It saves warmup checkpoints every 50 cycles, requires a stable
600-cycle particle-count window, then saves measurements every 20 cycles.
`stopping.py` retains the previously used 3% scalar/profile and 5% coarse
heating-map criteria with two consecutive passes, Student-t block estimates,
positive autocorrelation inflation, and an additional 40-cycle-block check.
Renewed secular density drift starts a new measurement epoch rather than
mixing transients into an average. Checkpoints, completed-block metadata,
and histories support restarting an interrupted controller in its complete
workspace. A `STOP_AFTER_BLOCK` file in ROOT or a case directory requests
a stop at the next complete checkpoint.

`analyze_scan.py ROOT` checks and exports final averages, CSV, DAT, PNG,
PDF, and a summary ZIP. `publish_scan.py ROOT --watch` backs up snapshots
to `results/20mTorr-topRF` and exports completed cases automatically.
Uploads use a short `YYMMDD_gap25_V100-300` folder, the standard report,
and the main/condition-branch catalog updater. See the
[result guide](../../docs/RESULTS_GUIDE.md).
`publish_scan.py ROOT --export-only /path/to/EXPORT` prepares a report
locally without uploading or starting a simulation.
Publishing uses the user's authorized repository and a separate results
branch; it does not publish or change the cloud environment.

`verify_boundary.cc` checks vacuum Poisson solutions at eight RF phases,
the pressure conversion, and unequal particle losses at the two ends to
verify electrode flux and ion-energy-distribution labels. Compile and run
it with each of the three `EDUPIC_VOLTAGE_V` values.

The original phase-binned `jE` definition, 400-point mesh, 4000 electron
steps per RF period, ion subcycling, collision physics, and particle weight
are retained. A restart preserves particle state but not the original
random-number generator state. The statistical stopping test is not a
guarantee of total physical or numerical error.
