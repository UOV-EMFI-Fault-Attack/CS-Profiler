import time
import os
import sys
import subprocess
import tty
from tenacity import retry, wait_fixed, stop_after_attempt
import timeout_decorator
from chipshouter import ChipSHOUTER
from .USBUtils import find_usb_port_by_tty, find_tty_by_id


class ChipShouter:
    def __init__(self, tty_or_id="NewAE_ChipSHOUTER_Serial"):
        self._tty_or_id=tty_or_id

        # Find ChipShouter tty
        if tty_or_id.startswith("/dev/tty"):
            # If tty_or_id starts with /dev/tty check if the specified device exists
            if os.path.exists(tty_or_id):
                self._tty = tty_or_id
            else:
                raise FileNotFoundError(f"TTY device '{tty_or_id}' not found.")
        else:
            # Else try to find tty by substring matching serial_ids (from /dev/serial/by-id)
            try:
                self._tty = find_tty_by_id(tty_or_id)
            except Exception as e:
                raise FileNotFoundError(f"ChipShouter USB: {str(e)}")

        # Find ChipShouter USB hub_path and hub_port_num (used for power cycling with uhubctl)
        try:
            self._hub_path, self._hub_port_num = find_usb_port_by_tty(self._tty)
        except Exception as e:
            print(f"ChipShouter: {str(e)}")
            print("ChipShouter: USB Power cycling unavailable!")

        # Initialize ChipShouter
        self.cs = ChipSHOUTER(self._tty)
        self.reset() # takes about 5s
        print("Chipshouter connected!")

    def disconnect(self):
        self.disarm()
        self.cs.disconnect()
        del self.cs

    def power_cycle_usb(self):
        if self._hub_path and self._hub_port_num:
            self._power_cycle_usb()
        else:
            raise Exception("ChipShouter: USB Power cycling is unavailable (check if your hub supports it with uhubctl)")

    @retry(wait=wait_fixed(10), stop=stop_after_attempt(3))
    def _power_cycle_usb(self):
        print("Power cycling ChipShouter USB Port")
        subprocess.run(
            ["uhubctl", "-l", self._hub_path, "-p", self._hub_port_num, "-a", "cycle"],
            stdout=subprocess.DEVNULL
        )
        self.__init__(self._tty_or_id)

    def reset(self):
        # Reset ChipShouter
        self.cs.reset = True
        # Wait till ChipShouter is reset and ready
        time.sleep(0.5)

        self.cs.absent_temp = 60
        self.cs.mute = True

    @retry(wait=wait_fixed(5), stop=stop_after_attempt(3))
    def clear_faults(self):
        print(f"Chipshouter faults: current={self.cs.faults_current}, latched={self.cs.faults_latched}. Clearing...")

        # This sometimes does not work (overtemp faults cannot be cleared even though this passes)
        # There might be additional temp sensors that are not available through ChipShouter python library
        while self.temps_too_high():
            print("Chipshouter Temp too high, waiting...")
            time.sleep(10)

        # Try to clear overtemp fault for 5 minutes
        overtemp_clear_try = 1
        overtemp_clear_max_tries = 30
        while "fault_overtemp" in self.cs.faults_current and overtemp_clear_try < overtemp_clear_max_tries:
            print("Trying to clear ChiShouter overtemp fault (try {overtemp_clear_try}/{overtemp_clear_max_tries})...")
            self.cs.faults_current = 0
            time.sleep(10)
            overtemp_clear_try += 1

        # Clear faults (also non-overtemp faults)
        self.cs.faults_current = 0
        # Raise error if faults persist
        current = self.cs.faults_current
        if current:
            raise RuntimeError(f"Failed to clear ChipSHOUTER faults: {current}!")

    def temps_too_high(self, threshold=65):
        return any(temp > threshold for temp in [
            self.cs.temperature_diode,
            self.cs.temperature_mosfet,
            self.cs.temperature_xformer,
        ])

    def _wait_for_safe(self, timeout=1):
        """Wait until trigger_safe becomes True or timeout (in seconds) occurs."""
        deadline = time.time() + timeout
        while not self.cs.trigger_safe and time.time() < deadline:
            time.sleep(0.1)
        return self.cs.trigger_safe

    class ArmingTimeoutError(TimeoutError):
        def __init__(self, message="ChipShouter: Arming failed due to timeout!"):
            super().__init__(message)

    # @retry(
    #     wait=wait_fixed(1),
    #     stop=stop_after_attempt(3)
    # )
    @timeout_decorator.timeout(10, timeout_exception=ArmingTimeoutError)
    def arm(self):
        state = self.cs.state
        if state == "armed":
            # Even if already armed, set armed variable again
            # because ChipShouter has internal timeout of 60s
            # and might auto-disarm at bad time
            # self.cs.armed = True
            return True
        elif state == "disarmed":
            # Always arm at 150V and then set the actual desired voltage
            # https://github.com/newaetech/ChipSHOUTER/issues/5
            voltage_setpoint = self.cs.voltage.set
            self.cs.voltage = 150
            self.cs.armed = True
        elif state == "fault":
            raise RuntimeError("ChipShouter has faults!")

        # wait till CS is armed
        print("arming.", end="")
        while self.cs.state != "armed":
            time.sleep(0.1)
            print(".", end="")
            sys.stdout.flush()
        print(f"{self.cs.state}")
        # Set actual desired voltage after arming
        self.cs.voltage = voltage_setpoint

        return self.cs.state == "armed"

    def disarm(self):
        self.cs.pulse = False
        self.cs.armed = False

    def configure_pulsegen(self, deadtime, repeat, width):
        assert deadtime in range(1, 1001), "Chipshouter pulse.deadtime has to be 1 to 1000 ms!"
        assert repeat in range(1, 10001), "Chipshouter pulse.repeat has to be between 1 and 10000!"
        assert width in range(80, 961), "Chipshouter pulse.width has to be between 80 and 960 ns!"

        self.cs.emode = False # configure enable pin, to trigger a pulse
        self.cs.pulse.deadtime = deadtime
        self.cs.pulse.repeat = repeat
        self.cs.pulse.width = width

    @property
    def voltage(self):
        return self.cs.voltage

    @voltage.setter
    def voltage(self, value):
        self.cs.voltage = value

    def pulse(self):
        self.cs.pulse = 1