"""
pk232_hostmode_sub.py — Host Mode entry subprocess helper.
Called by serial_manager.py with: python pk232_hostmode_sub.py PORT BAUD
Prints "OK" on success, "FAIL:hexdata" on failure.
"""
import serial, time, sys

PORT = sys.argv[1]
BAUD = int(sys.argv[2])
SOH=0x01; ETB=0x17; CTL=0x4F
HPOLL_Y   = bytes([SOH, CTL, 0x48, 0x50, 0x59, ETB])
HPOLL_ACK = bytes([SOH, CTL, 0x48, 0x50, 0x00, ETB])

port = serial.Serial(PORT, BAUD, bytesize=8, parity='N', stopbits=1,
                     timeout=0.1, xonxoff=False, rtscts=False)
time.sleep(0.3)
port.reset_input_buffer()

def read_until(marker, timeout=3.0):
    buf = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        n = port.in_waiting
        if n:
            buf.extend(port.read(n))
            if isinstance(marker, list):
                if any(m in buf for m in marker):
                    return bytes(buf)
            elif marker in buf:
                return bytes(buf)
            deadline = time.monotonic() + 0.15
        else:
            time.sleep(0.02)
    return bytes(buf)

port.write(b"\rXFLOW OFF\r\rHOST 3")
port.flush()
r1 = read_until(b"cmd:cmd:", timeout=2.0)

port.write(b"\r")
port.flush()
r2 = read_until(b"\r\n", timeout=1.0)

port.write(HPOLL_Y)
port.flush()
r3 = read_until([HPOLL_ACK, HPOLL_Y], timeout=2.0)

if HPOLL_ACK in r3:
    print("OK")
else:
    print("FAIL:" + r3.hex())
port.close()