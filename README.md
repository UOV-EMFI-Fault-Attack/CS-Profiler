# Chipshouter Profiler
This projects can be used to profile EMFI attacks using the ChipShouter on ChipWhisperer targets.

Unfinished, unstable state, not ready for release!
Not universally usable, requires special hardware like thorlabs motor controllers.


<!-- **TODO: OUTDATED, update RE instructions!!!** -->
<!-- The target runs the `emfi-profiler.c` program. After receiving a start signal via UART, it will execute a nested for loop, incrementing a counter to a known value. Afterwords it compares the counter with the expected result. If the counter is as expected, it will send an end signal. Otherwise a message indicating that a fault occurred and the value of the counter is sent via UART. The GPIO4/TRIG pin is set high before entering the counting loops and low afterwords.

The `profile_target.py` script is used to flash the target, control the execution and inject faults at different positions. The XYZ stage is used to scan the chip along a predefined grid. The grid is defined by the `movement_config` instance:

``` python
movement_config = MovementConfig(
    point_1 = Point(25, 1, 15.6),
    point_2 = Point(34, 10, 15.6),
    step_x = 8,
    step_y= 8,
)
```

At each point of the grid the ChipShouter can be used to inject faults with different configurations, each repeated `num_executions` times. Since the actual pulse width may vary from the ChipShouter configured values (especially with smaller injection coils), it is recommended to measure pulse_voltage and pulse_width of each glitch configuration with an oscilloscope and also store them for later analysis.

``` python
    glitch_configs = [
        GlitchConfig(
            probe = "4mm CCW",
            voltage = 400,
            pulse_width = 80,
            osc_measured_pulse_voltage = 300, # measurements may vary
            osc_measured_pulse_width = 80, # measurements may vary
            pulse_spacing = 15,
            pulse_repeat = 2,
            num_executions = 1,
            dead_timeout = 400,
        ),
        GlitchConfig(
            probe = "4mm CCW",
            voltage = 200,
            pulse_width = 80,
            osc_measured_pulse_voltage = 150, # measurements may vary
            osc_measured_pulse_width = 67, # measurements may vary
            pulse_spacing = 15,
            pulse_repeat = 2,
            num_executions = 1,
            dead_timeout = 400,
        )
    ]
```

Results will be stored in the `results/` directory and are composed of:

`xy_map.npy` storing the number of faults / resets / crashes for every position and glitch configuration.

- axis 0: glitch_configuration
- axis 1: position x
- axis 2: position y
- axis 3: [num_nofaults, num_faults, num_crashes, num_resets]

`extradata.json` file holding the glitch configurations and the counter values for all of their injected fault, together with their respective positions. `x` and `y` are indices of the xy_map and not absolute coordinates!

Suffixes `_1`, `_2`, ... will automatically be appended to the filenames to prevent overwriting.
 -->

## Setup
<!-- 
In case a ChipShouter communication error occurs, the script will try to power cycle the ChipShouter USB port. For that to work, [uhubctl](https://github.com/mvp/uhubctl) is needed.

Install with:
```
sudo apt install uhubctl
```

Your USB Hub needs to support power switching of individual ports. You can check that by running `uhubctl` without any arguments. To allow non-root users to control usb devices, the following udev rules have to be added to `52-usb.rules`:

```
# uhubctl udev rules for rootless operation on Linux for users in group `dialout`.

# This is for Linux before 6.0:
SUBSYSTEM=="usb", DRIVER=="hub|usb", MODE="0664", GROUP="dialout"

# This is for Linux 6.0 or later (ok to keep this block present for older Linux kernels):
SUBSYSTEM=="usb", DRIVER=="hub|usb", \
  RUN+="/bin/sh -c \"chown -f root:dialout $sys$devpath/*port*/disable || true\"" \
  RUN+="/bin/sh -c \"chmod -f 660 $sys$devpath/*port*/disable || true\""
```

You then need to add your user to the dialout group:
```
sudo usermod -a -G dialout $USER
```

Apply the udev rules and **start a new shell session**:
```
sudo udevadm trigger --attr-match=subsystem=usb
exit
``` -->


## Usage
<!-- 1. Build target firmware:
``` bash
cd target-firmware/build
make PLATFORM=CW308_STM32F4 CRYPTO_TARGET=NONE
```

2. Adjust `glitch_configs` and `movement_config` in `profile_target.py` to your needs.

3. Connect the GPIO4/TRIG pin of the ChipWhisperer target to the ChipShouter enable pin if you want to use it's internal pulse generator. Otherwise you can also trigger the ChipShouter with the ChipWhisperer glitch port or an external device like a [Raspberry Pi Pico](https://gitlab.cs.hs-rm.de/side-channel-fi-setup/pico-trigger-sweeper/).

3. Run profiling script. Use `-f` to flash the target before execution and `-h` to home the xyz-stage:

``` bash
python3 profile_target.py -h -f
```
**Make sure that the xyz-stage is always homed, otherwise the coordinate system will be shifted and you might crash the probe!**

Use an oscilloscope to verify that the glitches indeed hit during the nested loop execution (while trigger is high).

5. Plot the results for individual glitch configurations
``` bash
python3 plot.py results/xy_map.npy <glitch_config_index>
``` -->