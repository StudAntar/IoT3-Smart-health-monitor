from machine import Pin
import time

motor = Pin(5, Pin.OUT)        # V919 IN-pin
button = Pin(19, Pin.IN)       # HW-483 S-pin

while True:
    state = button.value()

    # HW-483 er normalt AKTIV LOW (0 = trykket)
    if state == 0:
        motor.value(1)
    else:
        motor.value(0)

    time.sleep(0.01)  # Lidt pause for stabilitet

