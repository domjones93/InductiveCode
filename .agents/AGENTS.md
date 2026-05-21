# AGENTS.md

## Project overview
This repository contains firmware and MATLAB tools for reading an LDC1614 inductance-to-digital converter.

There are two main components:
- MCU firmware: runs on a microcontroller and reads values from the LDC1614 sensor.
- MATLAB acquisition script: reads values from the MCU over serial and records them.
- Experimental MATLAB calibration script: applies a calibration step before saving data.

## Repository layout
Describe the folders here, for example:
- `/firmware/` MCU code
- `/matlab/` stable MATLAB acquisition scripts
- `/matlab/experimental/` calibration or prototype scripts

## Agent working rules
- Keep firmware and MATLAB changes separate unless explicitly asked.
- Do not change serial message formats unless requested.
- Preserve compatibility between MCU output and MATLAB parsing.
- Treat experimental calibration code as less stable than the main acquisition path.
- Prefer small, well-scoped changes.

## Firmware guidance
- Maintain clear LDC1614 register/configuration comments.
- Avoid hard-coded magic numbers where named constants are possible.
- Be careful with timing, I2C/SPI communication, and serial output formatting.
- Do not introduce blocking delays unless necessary.

## MATLAB guidance
- Keep acquisition scripts readable and reproducible.
- Validate serial parsing against the MCU output format.
- Save raw data wherever possible, even when calibrated data is also saved.
- Keep calibration logic isolated from basic data acquisition.

## Testing and validation
Before finishing firmware changes:
- Build/compile the firmware.
- Check that serial output format is documented.

Before finishing MATLAB changes:
- Check that scripts run without syntax errors.
- Confirm saved data columns are clearly named.
- Preserve existing output file formats unless asked to change them.

## Reporting back
When finishing a task, summarize:
- Files changed
- Firmware impact
- MATLAB impact
- Tests or checks performed
- Any assumptions about hardware, serial format, or calibration