# -------- SENSOR-ENHED: Temp (MAX30205) + P/I (MAX30102) + BATTERI (INA219) --------
from machine import I2C, Pin
import network
import espnow
import time
from max301022 import MAX301022   # <-- RIGTIG DRIVER (har read_latest)
from ina219 import INA219         # batterimåling

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

# -------------------- P/I MÅLING (MAX301022) - STABIL FIFO VERSION --------------------
SAMPLE_HZ = 20
DT = 1.0 / SAMPLE_HZ

FINGER_TH = 20000
FINGER_STABLE_SEC = 1.0
WARMUP_SEC = 2.0
MEASURE_SECONDS = 23.0

ppg = MAX301022(i2c)

def ppg_get():
    """
    Returnerer altid (IR, RED) uanset om driveren leverer (red, ir) eller (ir, red).
    MAX30102: IR er næsten altid større end RED når du har finger på.
    """
    a, b = ppg.read_fifo()

    # vælg den største som IR
    if a > b:
        ir, red = a, b
    else:
        ir, red = b, a

    return ir, red

def detrend(signal, window):
    out = []
    for i in range(len(signal)):
        start = max(0, i - window + 1)
        avg = sum(signal[start:i+1]) / (i - start + 1)
        out.append(signal[i] - avg)
    return out

def find_peaks(signal, min_height, min_distance):
    peaks = []
    for i in range(1, len(signal)-1):
        if signal[i] > signal[i-1] and signal[i] > signal[i+1] and signal[i] >= min_height:
            if not peaks or (i - peaks[-1]) > min_distance:
                peaks.append(i)
    return peaks

def median(vals):
    if not vals:
        return None
    s = vals[:]
    s.sort()
    mid = len(s) // 2
    if len(s) % 2 == 1:
        return s[mid]
    return 0.5 * (s[mid-1] + s[mid])

def calc_spo2_from_buffers(ir_raw, red_raw, peaks, fs):
    R_vals = []
    half = int(0.4 * fs)

    for p in peaks:
        start = max(0, p - half)
        end = min(len(ir_raw) - 1, p + half)

        ir_seg = ir_raw[start:end+1]
        red_seg = red_raw[start:end+1]
        if len(ir_seg) < 10:
            continue

        ac_ir = max(ir_seg) - min(ir_seg)
        ac_red = max(red_seg) - min(red_seg)
        dc_ir = sum(ir_seg) / len(ir_seg)
        dc_red = sum(red_seg) / len(red_seg)

        if dc_ir <= 0 or dc_red <= 0 or ac_ir <= 0 or ac_red <= 0:
            continue

        # reject very weak pulsations (typisk for hårdt tryk / bevægelse)
        if (ac_ir / dc_ir) < 0.002:
            continue

        R = (ac_red / dc_red) / (ac_ir / dc_ir)
        R_vals.append(R)

    if not R_vals:
        return 0, 0, None

    R_med = median(R_vals)
    spo2 = -45.06 * (R_med ** 2) + 30.354 * R_med + 94.845
    spo2 = int(max(0, min(100, spo2)))
    return spo2, len(R_vals), R_med

def wait_for_finger(timeout_sec=15):
    print("Vent: laeg fingeren let og daek mod lys...")
    stable = 0
    need = int(FINGER_STABLE_SEC * SAMPLE_HZ)

    t0 = time.time()
    last = 0

    while stable < need:
        if time.time() - t0 > timeout_sec:
            print("Finger timeout -> ingen stabil finger registreret.")
            return False

        try:
            ir, red = ppg_get()
        except Exception as e:
            if time.time() - last > 0.5:
                print("FIFO read fejl:", e)
                last = time.time()
            time.sleep(DT)
            continue

        if time.time() - last > 0.5:
            print("IR:", ir, "RED:", red, "| stable:", stable, "/", need)
            last = time.time()

        if ir > FINGER_TH:
            stable += 1
        else:
            stable = 0

        time.sleep(DT)

    print("Finger OK")
    return True

def measure_pi_once(seconds=MEASURE_SECONDS, fs=SAMPLE_HZ):
    print("Starter P/I-måling i", seconds, "sek...")

    ok = wait_for_finger()
    if not ok:
        return None, None

    # warmup
    t0 = time.time()
    while time.time() - t0 < WARMUP_SEC:
        try:
            _ = ppg_get()
        except:
            pass
        time.sleep(DT)

    # measure
    ir_raw = []
    red_raw = []
    start = time.time()

    while time.time() - start < seconds:
        try:
            ir, red = ppg_get()
            ir_raw.append(ir)
            red_raw.append(red)
        except:
            pass
        time.sleep(DT)

    if len(ir_raw) < 50:
        print("For få samples til P/I-beregning.")
        return None, None

    hp = detrend(ir_raw, window=int(fs * 0.75))
    mean_hp = sum(hp) / len(hp)
    hp_abs = [abs(x - mean_hp) for x in hp]

    tmp = hp_abs[:]
    tmp.sort()
    p95 = tmp[int(0.95 * (len(tmp)-1))]

    threshold = max(int(0.35 * p95), 200)
    peaks = find_peaks(hp_abs, threshold, int(0.35 * fs))

    if len(peaks) < 3:
        print("For få peaks -> ustabil måling. Prøv igen.")
        return None, None

    bpm = int(len(peaks) * (60.0 / seconds))
    spo2, beats_used, R_med = calc_spo2_from_buffers(ir_raw, red_raw, peaks, fs)

    print("P/I resultat – BPM:", bpm, "SpO2:", spo2,
          "| peaks:", len(peaks),
          "| beats_used:", beats_used,
          "| R_med:", (None if R_med is None else round(R_med, 3)))

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
            print("Ignorerer BEGIN_P_I – måling er allerede færdig.")
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

