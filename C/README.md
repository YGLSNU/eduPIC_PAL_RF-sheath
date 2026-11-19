This is the C version of the eduPIC 1.0 plasma simulation code.

This research branch compiles the source as C++11 and uses 20 mTorr,
with the upper electrode (`x=L`) powered and the lower electrode (`x=0`)
grounded. The default voltage is 250 V peak. Build with
`-DEDUPIC_VOLTAGE_V=100.0` or `300.0` for the other scan conditions.
Pressure input and reports use mTorr; internal collision calculations use SI.

See [the voltage-scan instructions](../scripts/voltage_scan/README.md) for
independent runs, adaptive stopping, diagnostics, and restart behavior.
The bundled reference data remain the original published reference case.
