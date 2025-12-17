import network
import espnow

w0 = network.WLAN(network.STA_IF)
w0.active(True)

print("Receiver MAC:", w0.config('mac'))

e = espnow.ESPNow()
e.active(True)

print("ESP-NOW receiver klar... venter på beskeder")

while True:
    host, msg = e.recv()  
    if msg:
        try:
            text = msg.decode()
        except:
            text = str(msg)
        print("Fra:", host, "  besked:", text)
