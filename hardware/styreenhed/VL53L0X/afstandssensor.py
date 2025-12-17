from machine import Pin, I2C
import time
from vl53l0x import VL53L0X

i2c = I2C(0, scl=Pin(22), sda=Pin(21))
sensor = VL53L0X(i2c)

led = Pin(12, Pin.OUT)

LOW_LIMIT = 21
HIGH_LIMIT = 40

hold_until = 0

while True:
    raw = sensor.range

    print("Raw distance:", raw, "mm")

    if raw != 20:

        if LOW_LIMIT <= raw <= HIGH_LIMIT:
            hold_until = time.ticks_add(time.ticks_ms(), 120000)  # 2 minutter

    if time.ticks_diff(hold_until, time.ticks_ms()) > 0:
        led.on()
    else:
        led.off()

    time.sleep(0.1)

