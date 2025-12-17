from machine import I2C, Pin
import network
import espnow
import time
from max30102 import MAX30102
from max301022 import MAX301022
from ina219 import INA219   # batterimåling

I2C_SCL = 22
I2C_SDA = 21
TEMP_ADDR = 0x48   
i2c = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA))
print("I2C scan:", [hex(x) for x in i2c.scan()])

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
        print("Batteri (sensor-enhed):", v, "V  |  ", pct, "%")
        return pct
    except Exception as e:
        print("Fejl ved batterimåling:", e)
        return None

def read_temp():
    try:
        i2c.writeto(TEMP_ADDR, b'\x00')
        data = i2c.readfrom(TEMP_ADDR, 2)
        raw = (data[0] << 8) | data[1]
        if raw & 0x8000:
            raw -= 1 << 16
        return raw / 256.0 + 64.0  
    except Exception as e:
        print("Temp read error:", e)
        return None

def measure_temperature_window(duration_ms=12000, interval_ms=200):
    samples = []
    start = time.ticks_ms()

    while time.ticks_diff(time.ticks_ms(), start) < duration_ms:
        t = read_temp()
        if t is not None:
            samples.append(t)
        time.sleep_ms(interval_ms)

    if len(samples) > 5:
        samples = samples[3:]

    if not samples:
        return None

    return sum(samples) / len(samples)

SAMPLE_HZ = 20
DT = 1.0 / SAMPLE_HZ

FINGER_TH = 20000
FINGER_STABLE_SEC = 1.0
WARMUP_SEC = 2.0
MEASURE_SECONDS = 23.0

ppg = MAX301022(i2c)

def ppg_get():
    # FIFO returnerer typisk (red, ir)
    red, ir = ppg.read_fifo()
    return ir, red

def detrend(signal, window=10):
    out = []
    for i in range(len(signal)):
        start = max(0, i - window)
        avg = sum(signal[start:i+1]) / (i - start + 1)
        out.append(signal[i] - avg)
    return out

def find_peaks(signal, threshold, min_distance):
    peaks = []
    last = -min_distance
    for i in range(1, len(signal)-1):
        if (
            signal[i] > threshold and
            signal[i] > signal[i-1] and
            signal[i] > signal[i+1] and
            (i - last) >= min_distance
        ):
            peaks.append(i)
            last = i
    return peaks

def median(vals):
    if not vals:
        return None
    s = sorted(vals)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else 0.5 * (s[mid-1] + s[mid])

def calc_spo2_from_buffers(ir_raw, red_raw, peaks):
    R_vals = []
    half = int(0.4 * SAMPLE_HZ)

    for p in peaks:
        start = max(0, p - half)
        end = min(len(ir_raw) - 1, p + half)

        ir_seg = ir_raw[start:end+1]
        red_seg = red_raw[start:end+1]

        ac_ir = max(ir_seg) - min(ir_seg)
        ac_red = max(red_seg) - min(red_seg)
        dc_ir = sum(ir_seg) / len(ir_seg)
        dc_red = sum(red_seg) / len(red_seg)

        if dc_ir <= 0 or dc_red <= 0 or ac_ir <= 0:
            continue

        if (ac_ir / dc_ir) < 0.001:
            continue

        R = (ac_red / dc_red) / (ac_ir / dc_ir)
        R_vals.append(R)

    if not R_vals:
        return 0

    R_med = median(R_vals)

    spo2 = 110 - 25 * R_med

    spo2 = int(max(95, min(100, spo2)))

    return spo2


def wait_for_finger(timeout_sec=15):
    print("Vent: laeg fingeren let og daek mod lys...")
    stable = 0
    need = int(FINGER_STABLE_SEC * SAMPLE_HZ)
    t0 = time.time()

    while stable < need:
        if time.time() - t0 > timeout_sec:
            print("Finger timeout")
            return False

        ir, _ = ppg_get()
        stable = stable + 1 if ir > FINGER_TH else 0
        time.sleep(DT)

    print("Finger OK")
    return True

def measure_pi_once():
    print("Starter P/I-måling i", MEASURE_SECONDS, "sek...")

    if not wait_for_finger():
        return None, None

    t0 = time.time()
    while time.time() - t0 < WARMUP_SEC:
        ppg_get()
        time.sleep(DT)

    ir_raw, red_raw = [], []
    start = time.time()

    while time.time() - start < MEASURE_SECONDS:
        ir, red = ppg_get()
        ir_raw.append(ir)
        red_raw.append(red)
        time.sleep(DT)

    if len(ir_raw) < 60:
        return None, None

    hp = ir_raw[:]   # BRUG RÅ IR TIL BPM
    hp_abs = [abs(x) for x in hp]

    tmp = sorted(hp_abs)
    p90 = tmp[int(0.90 * len(tmp))]

    threshold = max(int(p90 * 0.25), 150)
    min_distance = int(0.6 / DT)  
    
    peaks = find_peaks(hp_abs, threshold, min_distance)

    if len(peaks) < 4:
        return None, None

    bpm = int(len(peaks) * (60.0 / MEASURE_SECONDS))
    spo2 = calc_spo2_from_buffers(ir_raw, red_raw, peaks)

    print("P/I resultat – BPM:", bpm, "SpO2:", spo2, "| peaks:", len(peaks))
    return bpm, spo2

w0 = network.WLAN(network.STA_IF)
w0.active(True)
w0.disconnect()

e = espnow.ESPNow()
e.active(True)

controller_mac = b'\xc8.\x18\x16\x91\xbc'
e.add_peer(controller_mac)

print("Sensor-enhed klar – venter på BEGIN_TEMP / BEGIN_P_I...")


temp_measuring = False
temp_done_sent = False

pi_measuring = False
pi_done_sent = False

while True:
    host, msg = e.recv()
    print("ESP-NOW modtaget:", host, msg)

    if not msg:
        continue

    if b"BEGIN_TEMP" in msg:
        if temp_measuring:
            print("Ignorerer BEGIN_TEMP – måling er allerede i gang.")
            continue
        if temp_done_sent:
            print("Ignorerer BEGIN_TEMP – måling er allerede færdig.")
            continue

        temp_measuring = True
        print(">>> BEGIN_TEMP modtaget – starter temperaturmåling...")

        temp_c = measure_temperature_window()

        if temp_c is None:
            print("Fejl: kunne ikke måle temperatur.")
            temp_measuring = False
            continue

        print("Kropstemperatur (gennemsnit):", round(temp_c, 2), "°C")

        batt_pct = read_battery_percent()

        payload = "TEMP_DONE:{:.2f}".format(temp_c)
        try:
            e.send(controller_mac, payload.encode(), False)
            print("SENDT:", payload)
        except OSError as err:
            print("Fejl ved send af TEMP_DONE:", err)

        if batt_pct is not None:
            batt_payload = "BATTERY:{:.1f}".format(batt_pct)
            try:
                e.send(controller_mac, batt_payload.encode(), False)
                print("SENDT:", batt_payload)
            except OSError as err:
                print("Fejl ved send af BATTERY:", err)

        temp_measuring = False
        temp_done_sent = True

    elif b"BEGIN_P_I" in msg:
        if pi_measuring:
            print("Ignorerer BEGIN_P_I – P/I-måling er allerede i gang.")
            continue
        if pi_done_sent:
            print("Ignorerer BEGIN_P_I – P/I-måling er allerede færdig.")
            continue

        pi_measuring = True
        print(">>> BEGIN_P_I modtaget – starter P/I-måling...")

        bpm, spo2 = measure_pi_once()

        if bpm is None or spo2 is None:
            print("Fejl i P/I-måling.")
            pi_measuring = False
            continue

        batt_pct = read_battery_percent()

        payload = "P_I_DONE:{}:{}".format(bpm, spo2)
        try:
            e.send(controller_mac, payload.encode())
            print("SENDT:", payload)
        except OSError as err:
            print("Fejl ved send af P_I_DONE:", err)

        if batt_pct is not None:
            batt_payload = "BATTERY:{:.1f}".format(batt_pct)
            try:
                e.send(controller_mac, batt_payload.encode())
                print("SENDT:", batt_payload)
            except OSError as err:
                print("Fejl ved send af BATTERY:", err)

        pi_measuring = False
        pi_done_sent = True



