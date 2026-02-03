import time
import chipwhisperer as cw
from tenacity import retry, wait_fixed, stop_after_attempt
import timeout_decorator
import subprocess
from .USBUtils import find_usb_port_by_tty, find_tty_by_id

class ChipWhisperer:
    # TODO: handle multiple connected ChipWhisperers (pass serial number and get usb hub port from that)
    def __init__(self, target_type=cw.targets.SimpleSerial):
        self._target_type=target_type
        self.scope = cw.scope()
        self.scope.default_setup()
        try:
            self.target = cw.target(self.scope, target_type)
        except:
            print("INFO: Caught exception on reconnecting to target - attempting to reconnect to self.scope first.")
            print("INFO: This is a work-around when USB has died without Python knowing. Ignore errors above this line.")
            self.scope = cw.scope()
            self.target = cw.target(self.scope, target_type)

        # Find ChipWhisperer USB hub_path and hub_port_num (used for power cycling with uhubctl)
        try:
            # TODO: handle multiple ChipWhipserers
            self.chipwhisperer_tty = find_tty_by_id("ChipWhisperer_Lite")
            self._hub_path, self._hub_port_num = find_usb_port_by_tty(self.chipwhisperer_tty)
        except Exception as e:
            print(f"ChipWhisperer: {str(e)}")
            print("ChipWhisperer: USB Power cycling unavailable!")

    def configure_scope(self, samples:int, offset:int, decimate:int, timeout:float):
        self.scope.default_setup()
        self.scope.adc.decimate = 1
        self.scope.adc.timeout = 5
        self.scope.adc.samples = 24400 # max = 24573
        self.scope.adc.offset = 25000 # number of samples to be skipped (not recorded) after trigger (32 bit uint)

        print("INFO: Found ChipWhisperer😍")
        print(f"sample rate = adc_frequency({self.scope.clock.adc_freq}) * multiplier({self.scope.clock.adc_mul}) = {self.scope.clock.adc_freq * self.scope.clock.adc_mul}")

    def reset_target(self):
        self.scope.io.nrst = 'low'
        time.sleep(0.2)
        self.scope.io.nrst = 'high'
        time.sleep(0.2)

    def power_cycle_usb(self):
        if self._hub_path and self._hub_port_num:
            self._power_cycle_usb()
        else:
            raise Exception("ChipWhisperer: USB Power cycling is unavailable (check if your hub supports it with uhubctl)")

    @retry(wait=wait_fixed(10), stop=stop_after_attempt(3))
    def _power_cycle_usb(self):
        print("Power cycling ChipWhisperer USB Port")
        subprocess.run(
            ["uhubctl", "-l", self._hub_path, "-p", self._hub_port_num, "-a", "off"],
            stdout=subprocess.DEVNULL
        )
        time.sleep(5)
        subprocess.run(
            ["uhubctl", "-l", self._hub_path, "-p", self._hub_port_num, "-a", "on"],
            stdout=subprocess.DEVNULL
        )
        time.sleep(5)
        self.__init__(self._target_type)

    def flash(self, binary_path):
        prog = cw.programmers.STM32FProgrammer
        cw.program_target(self.scope, prog, binary_path)




