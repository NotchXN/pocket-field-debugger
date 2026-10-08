# Contributing

Run `python -m unittest discover -s tests -v` before submitting changes. Include raw reproducible fixtures when changing protocol behavior, and preserve malformed captures rather than silently repairing their bytes.

Capture data shared with the repository should be synthetic or approved for publication. Remove private device labels and operational details from examples. Specify observed timing provenance; do not present host USB receipt times as precise wire timing.

Hardware contributions should include editable source files, pin/power-domain information, a BOM, and bench evidence. Keep measured results distinct from targets. A future hardware-design license will be selected when original circuit/CAD artifacts are introduced.
