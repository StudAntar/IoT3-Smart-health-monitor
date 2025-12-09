from machine import Pin, I2C
import time
from vl53l0x import VL53L0X

# I2C setup
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
sensor = VL53L0X(i2c)

# LED pin
led = Pin(12, Pin.OUT)

# Afstandsgrænser
LOW_LIMIT = 21
HIGH_LIMIT = 40

# LED hold-timer (tidsstempel)
hold_until = 0

while True:
    raw = sensor.range

    print("Raw distance:", raw, "mm")

    # Ignorer fejlværdien 20 mm
    if raw != 20:

        # HVIS målingen rammer området 50–60 mm → start 2 min LED hold
        if LOW_LIMIT <= raw <= HIGH_LIMIT:
            hold_until = time.ticks_add(time.ticks_ms(), 120000)  # 2 minutter

    # LED skal være tændt SÅ LÆNGE vi er inden for hold-tiden
    if time.ticks_diff(hold_until, time.ticks_ms()) > 0:
        led.on()
    else:
        led.off()

    time.sleep(0.1)

