import os
import sys
from .config_classes import GlitchConfig, TargetConfig, SimpleSerialPacket
from .profile_target import CSProfiler
import ctypes

from simpleserial.simpleserial import TargetSerial

def memcpy_fault_handler(profilerSelf, packetSelf, data=None):
    profilerSelf.reset_target() # TODO when resetting fails, will faults or bricked be written??

    fields = [
            ("target_buffer", ctypes.c_uint8 * 48), # 68 bytes memcpy target buffer
            ("var1", ctypes.c_uint8 * 10), # 68 bytes memcpy target buffer
            ("var2", ctypes.c_uint8 * 10), # 68 bytes memcpy target buffer
        ]

    parsed_data = TargetSerial.parse_packet_data_struct(data, fields)

    return "faults", parsed_data

def get_raster_positions(origin, dim_x, dim_y, stepsize_x, stepsize_y):
    """
    Rasterize a rectangle of dimensions (dim_x, dim_y) with stepsizes (stepsize_x, stepsize_y).
    Starting at origin, returned positions are absolute. Z axis stays fixed at value from origin.

    Returns:
        List: List of positions [x, y, z]
    """

    # Generate coordinate lists for x and y
    x_coords = [origin[0] + x * stepsize_x for x in range(int(dim_x / stepsize_x) + 1)]
    y_coords = [origin[1] + y * stepsize_y for y in range(int(dim_y / stepsize_y) + 1)]

    # Create grid positions
    positions = [
        [x, y, origin[2]]  # Constant z-value
        for x in x_coords
        for y in y_coords
    ]

    return positions


def main():
    # ---------------------------------------------------------------------------- #
    #                             Commandline Arguments                            #
    # ---------------------------------------------------------------------------- #
    build = False
    flash = False
    home = False
    if len(sys.argv) > 1:
        # Build firmware (based on target_config)
        if "--build" in sys.argv or "-b" in sys.argv:
            build = True
        # Flash chipwhisperer on commandline argument
        if "--flash" in sys.argv or "-f" in sys.argv:
            flash = True
        # Home xyz table on commandline argument
        if "--home" in sys.argv or "-h" in sys.argv:
            home = True

    # ---------------------------------------------------------------------------- #
    #                             Target Configuration                             #
    # ---------------------------------------------------------------------------- #
    current_dir = os.path.dirname(os.path.abspath(__file__))
    target_config = TargetConfig(
        firmware_build_dir = os.path.join(current_dir, "target-firmware", "build"),
        firmware_build_command = ["make", "memcpy"], # [] to prevent auto building
        firmware_path = os.path.join(current_dir, "target-firmware", "build", "emfi-profiler-CW308_STM32F4.hex"),
    )

    # ---------------------------------------------------------------------------- #
    #                            Positions Configuration                           #
    # ---------------------------------------------------------------------------- #
    origin = [24, 5, 15.59] # x,y,z orgin
    dim_x = 0
    dim_y = 0
    stepsize_x = 1
    stepsize_y = 1
    positions = get_raster_positions(origin, dim_x, dim_y, stepsize_x, stepsize_y)

    # ---------------------------------------------------------------------------- #
    #                             Glitch Configurations                            #
    # ---------------------------------------------------------------------------- #
    glitch_configs = []
    for offset in [3400]:
        for pulse_width in [40, 45, 50]:
            glitch_configs.append(
                GlitchConfig(
                    probe = "4mm CW",
                    voltage = 0,
                    pulse_width = pulse_width,
                    pulse_spacing = 50,
                    pulse_repeats = 0,
                    pulse_offset = offset,
                    num_executions = 5,
                    dead_timeout = 100,
                )
            )

    # ---------------------------------------------------------------------------- #
    #                        Create and configure CSProfiler                       #
    # ---------------------------------------------------------------------------- #
    profiler = CSProfiler(target_config, positions, glitch_configs)
    profiler.addSimpleSerialCommand(SimpleSerialPacket("f", "Fault signal from target with buffer content (fault)", memcpy_fault_handler), overwrite=True)
    # profiler.addResultType("foo", "bar")

    # ---------------------------------------------------------------------------- #
    #                            Run CSProfiler Campaign                           #
    # ---------------------------------------------------------------------------- #
    profiler.run_campaign(build, flash, home)

if __name__ == "__main__":
    main()