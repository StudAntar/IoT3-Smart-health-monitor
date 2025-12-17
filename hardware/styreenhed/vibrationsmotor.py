from machine import Pin
import time

motor = Pin(5, Pin.OUT)        
button = Pin(19, Pin.IN)       

while True:
    state = button.value()

    if state == 0:
        motor.value(1)
    else:
        motor.value(0)

    time.sleep(0.01)  

