
from dataclasses import dataclass
from typing import List, Literal, Type, Union
import ctypes
from .simpleserial.simpleserial import TargetSerial

class SimpleSerialPacket:
    def __init__(self, command, description, externalHandler=None):
        self.command = TargetSerial.type_convert_cmd(command)
        self.description = description

        if externalHandler:
            self.handler = externalHandler

    def handler(self, packetSelf, profilerSelf, data=None):
        """
        Handler function for the SimpleSerialPacket. Usually overwritten by the constructor parameter `externalHandler` or via inheritance.
        When defined it needs to return

        Args:
            packetSelf (SimpleSerialPacket): Instance of the handled packet.
            profilerSelf (CSProfiler): Instance of the CSProfiler currently in use.
            data (bytes, optional): Packet data. Defaults to None.

        Raises:
            RuntimeError: When not overwritten via the constructor parameter `externalHandler` or via inheritance.

        Returns:
            result_category | (result_category, extradata): Valid types for result_category: str
                                                            Valid types for result_category: dict, str, int, list
        """

        raise RuntimeError(
            f"SimpleSerialPacket {self.command}: no handler defined"
        )

@dataclass
class GlitchConfig:
    probe: str
    voltage: int
    pulse_width: int
    pulse_spacing: int
    pulse_repeats: int
    pulse_offset: int
    num_executions: int

    dead_timeout: int
    ack_timeout: int = 100
    osc_measured_pulse_voltage: float = 0 # (V), measured with oscilloscope on 20:1 port of ChipShouter
    osc_measured_pulse_width: float = 0   # (ns), measured with oscilloscope on 20:1 port of ChipShouter

@dataclass
class TargetConfig:
    # TODO: future generalizations
    # target_type: Literal["chipwhisperer"] # implement "standalone" target type, add serial number to chipwhisperer
    # target_power_cycle_driver: Literal["chipwhisperer"] # implement driver for relay board and benchtop external power supply
    # target_communication_driver: Literal["chipwhisperer-serial"] # in future could also be I2C, SPI, BusPirate, CAN etc.
    # firmware_flash_driver:(chipwhisperer, openocd, script, ...)

    firmware_build_dir: str
    firmware_build_command: List[str] # command + args (e.g. ["make", "memcpy"])
    firmware_path: str

@dataclass
class Point:
    x: float
    y: float
    z: float

@dataclass
class MovementConfig:
    point_1: Point
    point_2: Point
    step_x: float
    step_y: float

