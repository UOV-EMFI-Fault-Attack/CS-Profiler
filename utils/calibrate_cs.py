from CSUtils import ChipShouter
import time

cs = ChipShouter()
cs.disarm()


cs.configure_pulsegen(
    10,
    100,
    80
)
cs.voltage = 400

cs.clear_faults()
cs.arm()
time.sleep(3)
while True:
    cs.pulse()
    time.sleep(3)

    # time.sleep(5)