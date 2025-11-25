
# Working MicroPython driver for VL53L0X (simplified)
# Tested on ESP32 + Thonny

import time
from machine import I2C

VL53L0X_REG_IDENTIFICATION_MODEL_ID = 0xC0
VL53L0X_REG_SYSRANGE_START = 0x00

class VL53L0X:
    def __init__(self, i2c, address=0x29):
        self.i2c = i2c
        self.address = address

        # Check device ID
        model_id = self._read_reg(VL53L0X_REG_IDENTIFICATION_MODEL_ID)
        if model_id != 0xEE:  # Expected for VL53L0X
            raise RuntimeError("VL53L0X not found")

    def _read_reg(self, reg):
        return self.i2c.readfrom_mem(self.address, reg, 1)[0]

    def _write_reg(self, reg, value):
        self.i2c.writeto_mem(self.address, reg, bytes([value]))

    @property
    def range(self):
        # Start measurement
        self._write_reg(VL53L0X_REG_SYSRANGE_START, 0x01)
        time.sleep_ms(50)

        # Read distance result registers (High + Low)
        hi = self._read_reg(0x1E)
        lo = self._read_reg(0x1F)
        return (hi << 8) | lo
