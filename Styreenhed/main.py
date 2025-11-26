import network
import espnow

# 1) WiFi i station mode (krævet for ESP-NOW)
w0 = network.WLAN(network.STA_IF)
w0.active(True)

print("Receiver MAC:", w0.config('mac'))

# 2) Start ESP-NOW
e = espnow.ESPNow()
e.active(True)

print("ESP-NOW receiver klar... venter på beskeder")

while True:
    host, msg = e.recv()  # Blokkerer indtil der kommer noget
    if msg:
        try:
            text = msg.decode()
        except:
            text = str(msg)
        print("Fra:", host, "  besked:", text)
