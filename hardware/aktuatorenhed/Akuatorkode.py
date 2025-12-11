from machine import Pin, I2C
import network
import espnow
import time
from ina219 import INA219   # batterimåling

# ---------------- I2C + BATTERI (INA219) ----------------
I2C_SCL = 22
I2C_SDA = 21

i2c = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA))
battery = INA219(i2c)

def constrain(value, min_val, max_val):
    return max(min_val, min(value, max_val))

def get_battery_percentage_from_voltage(voltage):
    min_voltage = 3.0
    max_voltage = 4.2
    percent = 100.0 * (voltage - min_voltage) / (max_voltage - min_voltage)
    return constrain(percent, 0, 100)

def read_battery_percent():
    try:
        v = battery.get_bus_voltage()
        pct = get_battery_percentage_from_voltage(v)
        print("Batteri (aktuator-enhed):", v, "V  |  ", pct, "%")
        return pct
    except Exception as e:
        print("Fejl ved batterimåling:", e)
        return None

# ---------------- GPIO KONFIG ----------------
VIB_PIN = 5    # GPIO til vibrationsmotor (via transistor)
SOL_PIN = 27   # GPIO til solenoid (via transistor)

vib = Pin(VIB_PIN, Pin.OUT)
sol = Pin(SOL_PIN, Pin.OUT)

vib.value(0)
sol.value(0)

# ---------------- ESP-NOW SETUP ----------------
w0 = network.WLAN(network.STA_IF)
w0.active(True)
w0.disconnect()

e = espnow.ESPNow()
e.active(True)

controller_mac = b'\xc8.\x18\x16\x91\xbc'
e.add_peer(controller_mac)

print("Aktuatorenhed klar – venter på PUSH_VIB...")

# ---------------- HJÆLPEFUNKTIONER ----------------
def do_vibration_and_solenoid():
    print("Starter vibration i 2 sek...")
    vib.value(1)
    time.sleep(2.0)
    vib.value(0)
    print("Vibration stoppet.")

    time.sleep(0.3)

    print("Aktiverer solenoid...")
    sol.value(1)
    time.sleep(0.7)   # justér efter behov
    sol.value(0)
    print("Solenoid deaktiveret.")


# ---------------- MAIN LOOP ----------------
while True:
    host, msg = e.recv()  # blocking
    print("ESP-NOW modtaget:", host, msg)

    if msg and b"PUSH_VIB" in msg:
        print(">>> PUSH_VIB modtaget – kører actuationssekvens...")

        do_vibration_and_solenoid()

        batt_pct = read_battery_percent()

        # 1) P_I_READY som før
        try:
            e.send(controller_mac, b"P_I_READY")
            print("P_I_READY sendt til styreenhed")
        except OSError as err:
            print("Fejl ved send af P_I_READY:", err)

        # 2) BATTERY:<pct>
        if batt_pct is not None:
            batt_payload = "BATTERY:{:.1f}".format(batt_pct)
            try:
                e.send(controller_mac, batt_payload.encode())
                print("SENDT:", batt_payload)
            except OSError as err:
                print("Fejl ved send af BATTERY:", err)

