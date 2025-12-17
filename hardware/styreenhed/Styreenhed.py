from machine import Pin, I2C
import time
from vl53l0x import VL53L0X
from ina219 import INA219
import network
import espnow
import json
import urequests
import machine

WIFI_SSID = "testnest"
WIFI_PASSWORD = "AA12345678"
API_URL = "http://10.136.130.22:5000/api/measurements"
DEVICE_TOKEN = "ESP_32"

I2C_SCL = 22
I2C_SDA = 21

i2c = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA))

tof = VL53L0X(i2c)       
battery = INA219(i2c)  

led = Pin(12, Pin.OUT)

LOW_LIMIT = 21
HIGH_LIMIT = 40

hold_until = 0

screen_on_sent = False

last_temp_c = None

last_bpm = None
last_spo2 = None

last_ctrl_batt = None      
last_sensor_batt = None    
last_actuator_batt = None  

def constrain(value, min_val, max_val):
    return max(min_val, min(value, max_val))

def get_battery_percentage_from_voltage(voltage):
    min_voltage = 3.0
    max_voltage = 4.2
    percent = 100.0 * (voltage - min_voltage) / (max_voltage - min_voltage)
    return constrain(percent, 0, 100)

w0 = network.WLAN(network.STA_IF)
w0.active(True)
w0.disconnect()              


broadcast_mac = b'\xff\xff\xff\xff\xff\xff'
sensor_mac = b'\xc8\x2e\x18\x16\x8f\x14'
actuator_mac = b'\xd4\x8a\xfc\x66\xfd\x94'

def init_espnow():
    global e
    e = espnow.ESPNow()
    e.active(True)
    e.add_peer(broadcast_mac)
    e.add_peer(sensor_mac)
    e.add_peer(actuator_mac)

init_espnow()

print("Styreenhed klar – måler afstand + batteri og styrer SCREEN_ON/OFF")
print("Venter også på START fra skærm...")



def upload_payload_to_api(payload):
    """
    1) Slår ESP-NOW midlertidigt fra
    2) Forbinder til WiFi og sender payload til API
    3) Lukker WiFi
    4) Gendanner ESP-NOW på den gamle kanal (default = 1)
    """
    global e

    try:
        e.active(False)
    except Exception as err:
        print("Kunne ikke deaktivere ESP-NOW:", err)

    w = network.WLAN(network.STA_IF)
    try:
        w.active(True)
        print("Forbinder til WiFi for API-upload...")
        w.connect(WIFI_SSID, WIFI_PASSWORD)

        t0 = time.time()
        while not w.isconnected() and time.time() - t0 < 10:
            time.sleep(0.2)

        if not w.isconnected():
            print("WiFi-forbindelse til API fejlede.")
        else:
            print("WiFi forbundet:", w.ifconfig())
            try:
                headers = {
                    "Content-Type": "application/json",
                    "X-DEVICE-TOKEN": DEVICE_TOKEN,  
                }
                data = json.dumps(payload)
                print("Sender til API:", API_URL)
                r = urequests.post(API_URL, data=data, headers=headers)
                print("API-respons:", r.status_code)
                # print("Body:", r.text)
                r.close()
            except Exception as err:
                print("Fejl i API-request:", err)
    except Exception as outer_err:
        print("Fejl i upload_payload_to_api:", outer_err)
    finally:
        try:
            w.disconnect()
        except:
            pass
        try:
            w.active(False)
        except:
            pass

        print("Gendanner ESP-NOW efter API-upload...")
        w0.active(True)
        w0.disconnect()
        init_espnow()



def finalize_results():
    global last_temp_c, last_bpm, last_spo2
    global last_ctrl_batt, last_sensor_batt, last_actuator_batt
    global e

    if last_temp_c is None or last_bpm is None or last_spo2 is None:
        print("Mangler data endnu -> temp/bpm/spo2:", last_temp_c, last_bpm, last_spo2)
        return

    payload = {
        "cpr_nummer": "010203-1234",  # TEST-CPR, skal findes i patients.cpr_nummer
        "body_temperature": float(last_temp_c),
        "heart_rate": int(last_bpm),
        "spo2": int(last_spo2),
        "battery_controller": float(last_ctrl_batt) if last_ctrl_batt is not None else 0.0,
        "battery_sensor": float(last_sensor_batt) if last_sensor_batt is not None else 0.0,
        "battery_actuator": float(last_actuator_batt) if last_actuator_batt is not None else 0.0,
    }

    print("### PAYLOAD TIL API ###")
    print(json.dumps(payload))
    print("######################")

    try:
        e.send(broadcast_mac, b"RESULTS_DONE")
        print("RESULTS_DONE broadcastet")
    except OSError as err:
        print("ESP-NOW fejl ved RESULTS_DONE:", err)

    upload_payload_to_api(payload)

while True:
    now = time.ticks_ms()

    host, msg = e.recv(0)   # 0 = non-blocking
    if msg:
        print("ESP-NOW modtaget fra", host, ":", repr(msg))

        text = None
        try:
            text = msg.decode()
        except:
            text = None

        if b"START" in msg:
            print(">>> START-komando modtaget fra skærmen! <<<")

            for i in range(3):
                try:
                    e.send(sensor_mac, b"BEGIN_TEMP")
                    print("BEGIN_TEMP sendt til sensorenhed (#", i+1, ")", sensor_mac)
                except OSError as err:
                    print("ESP-NOW fejl ved BEGIN_TEMP:", err)
                time.sleep_ms(50)

        elif text and text.startswith("TEMP_DONE:"):
            try:
                temp_str = text.split(":", 1)[1]
                last_temp_c = float(temp_str)
                print(">>> TEMP_DONE modtaget – temp =", last_temp_c, "°C")
            except Exception as err:
                print("Fejl ved parsing af TEMP_DONE:", err)
                last_temp_c = None

            try:
                e.send(actuator_mac, b"PUSH_VIB")
                print("PUSH_VIB sendt til aktuatorenhed")
            except OSError as err:
                print("ESP-NOW fejl ved PUSH_VIB:", err)

        elif b"P_I_READY" in msg:
            print(">>> P_I_READY modtaget fra aktuatorenhed – klar til P/I-måling. <<<")

            for i in range(3):
                try:
                    e.send(sensor_mac, b"BEGIN_P_I")
                    print("BEGIN_P_I sendt til sensorenhed (#", i+1, ")", sensor_mac)
                except OSError as err:
                    print("ESP-NOW fejl ved BEGIN_P_I:", err)
                time.sleep_ms(50)

        elif text and text.startswith("P_I_DONE:"):
            try:
                _, bpm_str, spo2_str = text.split(":", 2)
                last_bpm = int(bpm_str)
                last_spo2 = int(spo2_str)
                print(">>> P_I_DONE modtaget – BPM =", last_bpm, "SpO2 =", last_spo2, "%")
            except Exception as err:
                print("Fejl ved parsing af P_I_DONE:", err)
                last_bpm = None
                last_spo2 = None

            finalize_results()

        elif text and text.startswith("BATTERY:"):
            try:
                batt_str = text.split(":", 1)[1]
                batt_val = float(batt_str)

                if host == sensor_mac:
                    last_sensor_batt = batt_val
                    print(">>> Batteri fra sensorenhed:", batt_val, "%")
                elif host == actuator_mac:
                    last_actuator_batt = batt_val
                    print(">>> Batteri fra aktuatorenhed:", batt_val, "%")
                else:
                    print("BATTERY modtaget fra ukendt enhed:", host, batt_val)

            except Exception as err:
                print("Fejl ved parsing af BATTERY-besked:", err)

    raw = tof.range
    print("Distance:", raw, "mm")

    if raw != 20:
        if LOW_LIMIT <= raw <= HIGH_LIMIT:
            # forlæng LED-timeren 2 min fra NU
            hold_until = time.ticks_add(now, 120000)

            if not screen_on_sent:
                try:
                    e.send(broadcast_mac, b"SCREEN_ON")
                    print("SCREEN_ON sendt pga. afstand i intervallet")
                    screen_on_sent = True
                except OSError as err:
                    print("ESP-NOW fejl ved SCREEN_ON:", err)

    if time.ticks_diff(hold_until, now) > 0:
        led.on()
    else:
        if screen_on_sent:
            try:
                e.send(broadcast_mac, b"SCREEN_OFF")
                print("SCREEN_OFF sendt (LED-timer udløbet)")
            except OSError as err:
                print("ESP-NOW fejl ved SCREEN_OFF:", err)
            screen_on_sent = False

        led.off()

    voltage = battery.get_bus_voltage()
    percent = get_battery_percentage_from_voltage(voltage)
    last_ctrl_batt = percent
    print("Battery (controller):", voltage, "V  |  ", percent, "%")

    print("-------------------------------------------------")
    time.sleep(1)
