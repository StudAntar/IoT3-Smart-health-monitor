# -------- SENSOR-ENHED: Temp (MAX30205) + P/I (MAX30102) + BATTERI (INA219) --------
from machine import I2C, Pin
import network
import espnow
import time
from max30102 import MAX30102
from ina219 import INA219   # batterimåling

# -------------------- I2C KONFIG --------------------
I2C_SCL = 22
I2C_SDA = 21
TEMP_ADDR = 0x48   # MAX30205

i2c = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA))
print("I2C scan:", [hex(x) for x in i2c.scan()])

# -------------------- BATTERI SENSOR (INA219) --------------------
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

# -------------------- TEMP LÆSNING (MAX30205) --------------------
def read_temp():
    try:
        i2c.writeto(TEMP_ADDR, b'\x00')
        data = i2c.readfrom(TEMP_ADDR, 2)
        raw = (data[0] << 8) | data[1]
        if raw & 0x8000:
            raw -= 1 << 16
        return raw / 256.0 + 64.0   # kalibrering
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

# -------------------- P/I MÅLING (MAX30102) --------------------
SAMPLE_HZ = 20
SAMPLE_INTERVAL = 1.0 / SAMPLE_HZ
MEASURE_SECONDS = 20

ppg = MAX30102(i2c)

def detrend(signal, window):
    if len(signal) < 2:
        return [0] * len(signal)
    out = []
    for i in range(len(signal)):
        start = max(0, i - window + 1)
        avg = sum(signal[start:i+1]) / (i - start + 1)
        out.append(signal[i] - avg)
    return out

def find_peaks(signal, min_height, min_distance):
    peaks = []
    for i in range(1, len(signal) - 1):
        if signal[i] > signal[i-1] and signal[i] > signal[i+1] and signal[i] >= min_height:
            if not peaks or (i - peaks[-1]) > min_distance:
                peaks.append(i)
    return peaks

def calc_bpm_from_peaks(peaks, duration_seconds):
    if not peaks or duration_seconds <= 0:
        return 0
    beats = len(peaks)
    bpm = int(beats * (60.0 / duration_seconds))
    return bpm

def calc_spo2_from_buffers(ir_raw, red_raw, peaks, fs):
    R_vals = []
    for p in peaks:
        half = int(0.4 * fs)
        start = max(0, p - half)
        end = min(len(ir_raw) - 1, p + half)
        ir_seg = ir_raw[start:end+1]
        red_seg = red_raw[start:end+1]
        if len(ir_seg) < 3 or len(red_seg) < 3:
            continue
        ac_ir = max(ir_seg) - min(ir_seg)
        ac_red = max(red_seg) - min(red_seg)
        dc_ir = sum(ir_seg) / len(ir_seg)
        dc_red = sum(red_seg) / len(red_seg)
        if dc_ir <= 0 or dc_red <= 0 or ac_ir <= 0:
            continue
        R = (ac_red / dc_red) / (ac_ir / dc_ir)
        R_vals.append(R)
    if not R_vals:
        return 0
    R_mean = sum(R_vals) / len(R_vals)
    spo2 = -45.06 * R_mean * R_mean + 30.354 * R_mean + 94.845
    spo2 = max(0, min(100, spo2))
    return int(spo2)

def measure_pi_once(seconds=MEASURE_SECONDS, fs=SAMPLE_HZ):
    print("Starter P/I-måling i", seconds, "sek...")
    ir_raw = []
    red_raw = []

    start_t = time.time()
    while time.time() - start_t < seconds:
        try:
            ir, red = ppg.read()
        except Exception as e:
            print("PPG read error:", e)
            time.sleep(SAMPLE_INTERVAL)
            continue

        ir_raw.append(ir)
        red_raw.append(red)
        time.sleep(SAMPLE_INTERVAL)

    if len(ir_raw) < 5:
        print("For få samples til P/I-beregning.")
        return None, None

    duration = len(ir_raw) / fs if fs > 0 else seconds

    hp = detrend(ir_raw, window=int(fs * 0.75))
    hp_max = max(hp)
    hp_min = min(hp)
    hp_range = hp_max - hp_min if (hp_max - hp_min) != 0 else 1
    threshold = max((0.30 * hp_range), 1000)
    min_distance = int(0.35 * fs)

    peaks = find_peaks(hp, threshold, min_distance)

    bpm = calc_bpm_from_peaks(peaks, duration)
    spo2 = calc_spo2_from_buffers(ir_raw, red_raw, peaks, fs)

    print("P/I resultat – BPM:", bpm, "SpO2:", spo2)
    return bpm, spo2

# ---------------- ESP-NOW SETUP ----------------
w0 = network.WLAN(network.STA_IF)
w0.active(True)
w0.disconnect()

e = espnow.ESPNow()
e.active(True)

controller_mac = b'\xc8.\x18\x16\x91\xbc'
e.add_peer(controller_mac)

print("Sensor-enhed klar – venter på BEGIN_TEMP / BEGIN_P_I...")

# Flags til temperatur
temp_measuring = False
temp_done_sent = False

# Flags til P/I
pi_measuring = False
pi_done_sent = False

# -------------------- MAIN LOOP --------------------
while True:
    host, msg = e.recv()
    print("ESP-NOW modtaget:", host, msg)

    if not msg:
        continue

    # --------- TEMPERATURDEL ---------
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

        # Batteri
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

    # --------- PULS / SpO2 DEL ---------
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

