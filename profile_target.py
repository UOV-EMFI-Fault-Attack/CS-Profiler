import os
import re
import sys
import glob
import signal
import subprocess
import traceback
import time
from dataclasses import dataclass, asdict
import json
import copy

from tenacity import RetryError

# local imports
from .CWUtils import ChipWhisperer
from .CSUtils import ChipShouter
from .config_classes import GlitchConfig, SimpleSerialPacket

from .simpleserial.simpleserial import TargetSerial
from .simpleserial.simpleserial_readers.cwlite import SimpleSerial_ChipWhispererLite

from .lib.pico_pulsegen.delay_control import DelayController
from .lib.emf_table.table import xyzTable

# TODO:
# - Add start and end timestamp to log file
# - Documentation

class ResetTimeoutError(TimeoutError):
    def __init__(self, message="Failed to reset target!"):
        super().__init__(message)

class CSProfiler:
    # glitch_configs = None
    # target_config = None
    # simpleserial_config = None
    # positions = None
    # num_positions = None

    # cw = None
    # target_serial = None
    # cs = None
    # table = None

    # catched_errors = None
    # results = None = None

    def __init__(self, target_config, positions, glitch_configs, simpleserial_config = None):
        self.target_config = target_config
        self.positions = positions
        self.num_positions = len(self.positions)
        self.glitch_configs = glitch_configs

        if simpleserial_config:
            self.simpleserial_config = simpleserial_config
        else:
            self.simpleserial_config = [
                SimpleSerialPacket("s", "Start signal for target (acknowleged by target)"),
                SimpleSerialPacket("e", "End signal from target (nofault)", self.nofaultPacketHandler),
                SimpleSerialPacket("r", "Reset signal from target (reset)", self.resetPacketHandler),
                SimpleSerialPacket("f", "Fault occured on target", self.faultPacketHandler)
            ]
        # Default result_types (Identifier: Description)
        self.result_types = {
            "nofaults": "No Fault",
            "faults": "FAULT",
            "crashes": "Target unresponsive",
            "resets": "Target reset",
            "soft_bricked": "Soft reset failed",
            "hard_bricked": "Hard reset failed",
            "skipped": "Skipped"
        }
        self._results = [
            {
                f"num_{key}": [0] * self.num_positions
                for key in self.result_types
            } for _ in self.glitch_configs
        ]

        self.valid_commands = [ss_packet.command for ss_packet in self.simpleserial_config]

    def addResultType(self, key: str, label: str):
        """
        Add a new result type to the configuration.

        Parameters
        ----------
        key : str
            The internal identifier for the result type (e.g., "timeouts").
        label : str
            The human-readable label (e.g., "Timeout occurred").

        Raises
        ------
        ValueError
            If key is not a string or label is not a string.
        KeyError
            If a result type with the same key already exists.

        Notes
        -----
        - Successfully added result types are tracked in `self.result_types`.
        - A new `num_<key>` entry will also be added to all `self._results` dictionaries
        (initialized with zeros, sized to `self.num_positions`).
        """
        if not isinstance(key, str) or not isinstance(label, str):
            raise ValueError("addResultType: Both key and label must be strings.")

        if key in self.result_types:
            raise KeyError(
                f"addResultType: Result type '{key}' already exists in result_types."
            )

        # Add to result_types mapping
        self.result_types[key] = label

        # Add corresponding counters to existing results
        for res in self._results:
            res[f"num_{key}"] = [0] * self.num_positions

    def addSimpleSerialCommand(self, packet, overwrite=False):
        """
        Add a new SimpleSerial command to the configuration.

        Parameters
        ----------
        packet : SimpleSerialPacket
            The command object to add. The object must define a unique `.command` attribute.

        Raises
        ------
        ValueError
            If the object is not a `SimpleSerialPacket`
        KeyError
            If a command with the same identifier already exists in command_configuration.

        Notes
        -----
        - Successfully added commands are tracked in `self.simpleserial_config`.
        - Duplicate commands are not allowed and will raise an error.
        """
        if not (isinstance(packet, SimpleSerialPacket)):
            raise ValueError(
                "addCommand: Can only add objects of type: SimpleSerialPacket"
            )

        if packet.command == 0:
            raise KeyError(f"SimpleSerial command cannot be 0 since zero is the termination character.")

        if packet.command in self.valid_commands:
            if not overwrite:
                raise KeyError(
                    f"addCommand: Command '{packet.command}' already exists in valid_commands."
                )
            # Remove old packet and command entry
            self.simpleserial_config = [
                p for p in self.simpleserial_config if p.command != packet.command
            ]
            self.valid_commands.remove(packet.command)

        # Append to configuration and update valid commands
        self.simpleserial_config.append(packet)
        self.valid_commands.append(packet.command)

    def send_packet(self, cmd, data=None):
        cmd = TargetSerial.type_convert_cmd(cmd)
        if not cmd in self.valid_commands:
            raise ValueError(f"sendPacket: Command: `{cmd}` is not a valid command, add it using addSimpleSerialCommand()")

        self.target_serial.send_packet(cmd, data)

    def ctrl_c_signal_handler(self, sig, frame):
        print("STORING RESULTS BEFORE EXIT")
        self.store_results(self.results, partial=True)
        self.cs.disarm()
        sys.exit(0)

    @staticmethod
    def make_json_serializable(obj):
        """
        Recursively convert a Python dict to a JSON-serializable format.

        - dict: process keys/values recursively
        - list/tuple: process elements recursively
        - bytes/bytearray: convert to uppercase hex string
        - other types: returned as-is
        """
        if isinstance(obj, dict):
            return {k: CSProfiler.make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [CSProfiler.make_json_serializable(v) for v in obj]
        elif isinstance(obj, (bytes, bytearray)):
            return bytes(obj).hex().upper()
        else:
            return obj

    def store_results(self, results, partial=False):
        # Find a unique filename
        counter = 0
        results_path = "results/"
        os.makedirs(results_path, exist_ok=True)
        while os.path.exists(f"{results_path}results_{counter}.json") or os.path.exists(f"{results_path}results_{counter}_partial.json"):
            counter += 1

        # Add info strings to the top of the results JSON
        log_json = dict()
        log_json.update({"Info: glitch_config results structure": "num_nofaults specifies the number of faults for every position from the positions array (equivalent for num_nofaults, num_resets, num_crashes)"})
        # log_json.update({"Info: positions structure": "All positions [x,y,z] from the positions array are relative to the origin"}) # TODO: maybe make positions relative to origin?

        # Convert glitch_configs to dicts
        glitch_config_dicts = [asdict(cfg) for cfg in self.glitch_configs]

        # Add results to glitch_config dicts
        for config_index, config_result in enumerate(results):
            glitch_config_dicts[config_index].update({"results": config_result})

        log_json.update({"catched_errors": self.catched_errors})
        log_json.update({"positions": self.positions})
        log_json.update({"glitch_configs": glitch_config_dicts})

        # Make log_json serializable
        log_json = self.make_json_serializable(log_json)

        # Save log_json as file
        def default_serializer(obj):
            print(f"ERROR: Serialization failed for: {obj}")
            return "SERIALIZATION_FAILED"

        with open(f"{results_path}results_{counter}{'_partial' if partial else ''}.json", "w") as f:
            json.dump(log_json, f, indent=4, default=default_serializer)

    def configure_chipshouter(self, glitch_config:GlitchConfig):
        # Configure voltage
        self.cs.voltage = glitch_config.voltage

        # Using Pi Pico as pulse generator
        with DelayController(port="/dev/ttyACM1") as dc:
            dc.set_parameters({"offset": glitch_config.pulse_offset, "length": glitch_config.pulse_width, "spacing": glitch_config.pulse_spacing, "repeats": glitch_config.pulse_repeats})

        # Configure internal pulse generator
        # cs.configure_pulsegen(
        #     glitch_config.pulse_spacing // 1000000, # convert from ns to ms
        #     glitch_config.pulse_repeats,
        #     glitch_config.pulse_width
        # )


    def reset_target(self, timeout=5000, retries=3):
        reset_seq = self.target_serial._reset_sequence
        for _ in range(retries):
            self.cw.reset_target()
            if self.target_serial.read_until(reset_seq, timeout).endswith(reset_seq):
                return 0

        raise ResetTimeoutError(f"Failed to reset target after {retries} tries!")

    def power_cycle_target(self):
        self.cw.power_cycle_usb() # Power cycle chipwhisperer USB port

    def handlePacket(self, cmd, data=None) -> tuple[str, dict]:
        # Find packet object in simpleserial_config that matches the command
        for packet in self.simpleserial_config:
            # Convert string commands to int if needed
            command_byte = (
                ord(packet.command[0]) if isinstance(packet.command, str) else packet.command
            )

            if command_byte == cmd:
                matched_packet = packet
                break
        if matched_packet is None:
            raise ValueError(f"No matching packet definition found for command: `{cmd}`")

        # Calls handler function of packet if it is defined
        if callable(matched_packet.handler):
            result = matched_packet.handler(self, matched_packet, data)
            if isinstance(result, tuple) and len(result) == 2:
                result_category, extradata = result
            elif isinstance(result, str):
                result_category, extradata = result, None
            else:
                raise ValueError(f"Handler of SimpleSerialPacket {matched_packet.command} must return either a string or a (string, extradata) tuple!")

            # Verify that returned result_category is valid
            if result_category not in self.result_types:
                raise ValueError(f"PacketHandler of command: `{matched_packet.command}` returned invalid result_category: `{result_category}`")

            # Verify that returned extradata is of type dict
            if extradata is not None and not isinstance(extradata, (dict, str, int, list)):
                raise ValueError(f"PacketHandler of command: `{matched_packet.command}` returned invalid extradata type (has to be dict, str, int, list)")

        return result_category, extradata

    def resetPacketHandler(_, profilerSelf, packetSelf, data=None) -> tuple[str, dict]:
        return "resets"

    def nofaultPacketHandler(_, profilerSelf, packetSelf, data=None) -> tuple[str, dict]:
        return "nofaults"

    def faultPacketHandler(_, profilerSelf, packetSelf, data=None) -> tuple[str, dict]:
        profilerSelf.reset_target() # TODO when resetting fails, will faults or bricked be written??
        # When resetting fails, error will be thrown here...
        return "faults"

    def crashHandler(self) -> tuple[str, dict]:
        """
        Handler for when target crashed (is unresponsive).

        Returns:
            tuple[str, dict]: result_category, extradata
        """
        self.reset_target()

        return "crashes", None

    def test_execution(self, position_index: int, config_index: int, execution_index: int) -> tuple[int, str, dict | None]:
        """
        Execute a single fault injection. Called by test_position.

        This function can be overwritten with overwrite_test_exeuction(newFunction) which allows
        for completely custom control flow for the fault injection.
        By default it does the following steps:
            - Arm ChipShouter
            - Check ChipShouter temperature (wait till cooled off if necessary)
            - Validate if ChipShouter is ready for trigger (trigger_safe)
            - Send start packet to target
            - Wait for target to acknowledge the start packet
            - Wait for target response packet
                - If received: call self.handlePacket(cmd, raw_data) to handle the command and parse data from it
                - If not received in time: call self.crashHandler()
            - Return incremented execution_index, result_category, extradata (optional)

        If self._test_execution is defined (by self.overwrite_test_execution()), call that function instead.

        Args:
            position_index (int):
            config_index (int):
            execution_index (int):

        Raises:
            e: Unknown error from chipshouter arming
            RuntimeError: ChipShouter is not ready for trigger (trigger_safe failed)

        Returns:
            tuple[int, str, dict | none (optional)]: (next_execution_index, result_category, extradata)
            tuple[int, str]: (next_execution_index, result_category)
        """

        # ------------------------------ If overwritten ------------------------------ #

        if hasattr(self, "_test_execution") and self._test_execution:
            # test_execution function was overwritten call self._test_execution() instead.
            ret = self._test_execution(self, position_index, config_index, execution_index)

            # Verify the return type
            if (isinstance(ret, tuple)):
                if len(ret) == 2:
                    next_execution_index, result_category = ret
                    data = None
                elif len(ret) == 3:
                    next_execution_index, result_category, data  = ret
                else:
                    raise TypeError(f"test_execution must return a tuple (int, str, dict) or (int, str), got {type(ret)}")
            else:
                raise TypeError(f"test_execution must return a tuple (int, str, dict) or (int, str), got {type(ret)}")

            if not isinstance(next_execution_index, int):
                raise TypeError(f"First element (next_execution_index) must be int, got {type(next_execution_index)}")
            if not isinstance(result_category, str):
                raise TypeError(f"Second element (result_category) must be str, got {type(result_category)}")
            if not (isinstance(data, dict) or data is None):
                raise TypeError(f"Third element (extradata) must be dict or None, got {type(data)}")

            return ret

        glitch_config = self.glitch_configs[config_index]
        next_execution_index = execution_index + 1

        # -------------------------- Default Implementation -------------------------- #

        time.sleep(0.05) # Small delay required to prevent ChipShouter from disconnecting

        # Arm ChipShouter. If it has faults, try to clear them.
        try:
            self.cs.arm()
        except Exception as e:
            # TODO: remove this separate handler and throw the fault into the main execution error handler
            self.catched_errors.append({"position_index": position_index, "error": str(e)})
            if str(e) == "ChipShouter has faults!":
                self.cs.clear_faults()
                return next_execution_index, "skipped", None
            else:
                print(e)
                raise e

        # Check ChipShouter temps
        while self.cs.temps_too_high():
            print("Chipshouter Temp too high, waiting...")
            time.sleep(10)

        # Validate that ChipShouter is ready for trigger
        if not self.cs.cs.trigger_safe:
            raise RuntimeError("ChipShouter is not ready for trigger (trigger_safe failed)!")

        # TODO: check CS measured voltage (prevents too fast shooting where CS cant charge quick enough)
        # print(f"Voltage_measured: {self.cs.voltage.measured}")
        
        # Send start signal to target
        self.send_packet("s")

        # Wait for target to acknowlege start packet
        if self.target_serial.wait_ack("s", glitch_config.ack_timeout) != 0:
            # ack not received -> target bricked
            result_category, extradata = self.crashHandler()
        else:
            # Read next packet from target
            try:
                cmd, raw_data = self.target_serial.read_packet(timeout=glitch_config.dead_timeout)
            except Exception as e:
                result_category, extradata = self.crashHandler()
            else: # if no exception was raised
                # Handle packet (according to simpleserial_config)
                result_category, extradata = self.handlePacket(cmd, raw_data)

        return next_execution_index, result_category, extradata

    def overwrite_test_execution(self, func):
        """
        Overwrite test_execution with a new function.
        The new function must have the same signature as CSProfiler.test_execution():
            test_execution(self, position_index, config_index, execution_index) -> (result_category, extradata, new_execution_index)
        """
        # Check if func has correct number of arguments
        orig_count = self.test_execution.__code__.co_argcount
        new_count = func.__code__.co_argcount
        if orig_count != new_count:
            raise TypeError(
                f"overwrite_test_execution: Function has wrong number of arguments."
            )

        self._test_execution = func

    def test_position(self, position_index):
        self.reset_target() #TODO: usually not needed but make configurable
        for config_index, glitch_config in enumerate(self.glitch_configs):
            # Verify that sequence of faults is not longer than dead_timeout
            pulse_spacing_ns = glitch_config.pulse_spacing
            faulting_duration_ns = (glitch_config.pulse_width + pulse_spacing_ns) * glitch_config.pulse_repeats
            faulting_duation_ms = faulting_duration_ns / 1e6
            assert faulting_duation_ms < glitch_config.dead_timeout, f"""
                Faulting for {faulting_duation_ms} ms
                but dead_timeout is only {glitch_config.dead_timeout} ms.
            """

            self.configure_chipshouter(glitch_config)
            config_results = self.results[config_index]

            self.target_serial.flush()

            execution_index = 0
            retry_count = 0
            while execution_index < glitch_config.num_executions:

                try: # Main try block, allowing 3 retries
                    # Run a single fault injection execution
                    execution_index, result_category, extradata = self.test_execution(position_index, config_index, execution_index)

                    # Print info string
                    print(f"pos: {position_index+1}/{self.num_positions} ; config: {config_index+1}/{len(self.glitch_configs)} ; execution {execution_index}/{glitch_config.num_executions}: {self.result_types[result_category]}]")

                    # Increment result_category in log
                    config_results[f"num_{result_category}"][position_index] += 1

                    # Add extradata to results
                    if extradata:
                        # Ensure the category exists
                        if result_category not in config_results:
                            config_results[result_category] = []
                        # Check if there is a already a data object for the current position and config_result
                        try:
                            if config_results[result_category][-1]["position_index"] == position_index:
                                data_array = config_results[result_category][-1]["data"]
                            else:
                                raise Exception("")
                        except: # If not, create one
                            config_results[result_category].append({
                                "position_index": position_index,
                                "data": []
                            })
                            data_array = config_results[result_category][-1]["data"]

                        data_array.append(extradata)

                # Handle all kinds of errors that can occur
                # TODO: allow adding error handlers
                except Exception as e:
                    # If e is a retry error, extract the underlying exception that caused it
                    if type(e) == RetryError:
                        last_exc = e.last_attempt.exception() if e.last_attempt else None
                        if last_exc:
                            e = last_exc

                    # Add error to catched_errors (for logging purposes)
                    self.catched_errors.append({"position_index": position_index, "error": str(e)})

                    # Allow a maximum of 3 retries per execution
                    if retry_count < 3:
                        retry_count += 1
                        if str(e) in {"No response from shouter.", "Failed to clear ChipSHOUTER faults!"}:
                            self.cs.power_cycle_usb()
                            self.target_serial.flush()
                            self.reset_target() # TODO: potential errors unhandled
                            self.configure_chipshouter(glitch_config)

                        elif str(e) in {"ChipWhisperer: reset_target timed out"}: # TODO: custom error type
                            # Try to power cycle and if not enough, reflash target
                            # Increment config_results["soft_bricked"] or config_results["hard_bricked"] accordingly and go to next execution index
                            self.cs.disarm() # Disarm shouter to prevent glitching while flashing
                            self.power_cycle_target() # Power cycle chipwhisperer USB port
                            self.target_serial = TargetSerial(SimpleSerial_ChipWhispererLite, self.cw.scope)

                            try:
                                # Try to reset target after power cycling
                                self.reset_target()
                                config_results["soft_bricked"] += 1
                                execution_index += 1
                            except Exception as e:
                                # If resetting still fails, reflash target and try again (hard_bricked)
                                print("Resetting, target failed even after power cycling, reflashing target firmware")
                                self.cw.flash("./target-firmware/build/emfi-profiler-CW308_STM32F4.hex") # Reprogram chipwhisperer
                                self.reset_target() # TODO: potential errors unhandled
                                config_results["hard_bricked"] += 1
                                execution_index += 1

                        else: # unknown error
                            raise e
                    else: # Limit number of errors per glitch_config and position to 3
                        # Skip the rest of the executions of current glitch_config at current position
                        num_skipped = glitch_config.num_executions - execution_index
                        config_results["num_skipped"] = num_skipped
                        print(f"Glitch config {config_index} retries exceeded, skipping {num_skipped}")
                        break

    def prepare_hardware(self):
        self.cw = ChipWhisperer()
        self.target_serial = TargetSerial(SimpleSerial_ChipWhispererLite, self.cw.scope)

        self.cs = ChipShouter()
        self.cs.disarm()

        # Setup XYZ Table
        self.table = xyzTable(debug=False)

    def run_campaign(self, build=False, flash=False, home=False):
        self.prepare_hardware()

        if build:
            subprocess.run(
                self.target_config.firmware_build_command,
                cwd=self.target_config.firmware_build_dir,
                check=True
                # stdout=subprocess.DEVNULL
            )
        if flash:
            self.cw.flash(self.target_config.firmware_path)
        if home:
            self.table.home_all()

        # Reset catched_errors and results
        self.catched_errors = []
        self.results = copy.deepcopy(self._results)

        # Store partial results on Ctrl+c
        signal.signal(signal.SIGINT, self.ctrl_c_signal_handler)

        prev_y = 0
        stepsize_y = 1 # TODO temp workaround, all of this shit should not be needed if xyztable library was properly written
        try:
            # Iterate over positions
            for (position_index, position) in enumerate(self.positions):
                # Move to position
                x, y, z = position
                self.table.move_absolute(x, y, z)
                if(prev_y - y >= stepsize_y):
                    print("changing pos")
                    time.sleep(5)
                prev_y = y

                # Test position
                self.test_position(position_index)

        # Global last resort error handling (store partial results and exit)
        except Exception as e:
            self.catched_errors.append({"position_index": "unknown", "error": str(e)})

            # Store partial results
            print("An error occurred:", file=sys.stderr)
            print("TRYING TO SAVE PARTIAL RESULTS!")
            self.store_results(self.results, partial=True)

            # Print full traceback to stderr
            traceback.print_exc()
            return -1


        # Finish campaign
        self.cs.disarm()
        self.store_results(self.results, partial=False)
        return 0