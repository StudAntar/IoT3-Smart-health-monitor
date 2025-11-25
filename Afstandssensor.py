from machine import Pin, I2C
import time
from vl53l0x import VL53L0X

i2c = I2C(0, scl=Pin(22), sda=Pin(21))
sensor = VL53L0X(i2c)

while True:
    print(sensor.range, "cm")
    time.sleep(0.1)
