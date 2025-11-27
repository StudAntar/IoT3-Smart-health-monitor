from machine import I2C, Pin
from ina219 import INA219
from time import sleep

i2c = I2C(0, scl=Pin(22), sda=Pin(21))
ina = INA219(i2c)

def constrain(value, min_val, max_val):
    return max(min_val, min(value, max_val))

def get_battery_percentage_from_voltage(voltage):
    min_voltage = 3.0
    max_voltage = 4.2
    percent = 100.0 * (voltage - min_voltage) / (max_voltage - min_voltage)
    return constrain(percent, 0, 100)

while True:
    voltage = ina.get_bus_voltage()
    percent = get_battery_percentage_from_voltage(voltage)
    print("V:", voltage, " | ", percent, "%")
    sleep(1)
