"""Patch script: adds write_verbose_wait() to serial_manager.py"""
import sys

path = r'E:\PK232\pk232py_repo\src\pk232py\comm\serial_manager.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

if 'write_verbose_wait' in content:
    print("Already patched.")
    sys.exit(0)

new_method = '''
    def write_verbose_wait(self, data: bytes, timeout: float = 5.0) -> bool:
        """Send a verbose-mode command and wait for TNC cmd: prompt.

        Sends the command, then accumulates incoming bytes until
        'cmd:' is detected (preceded by newline, or at chunk start).

        Args:
            data:    ASCII command e.g. b'MYCALL OE3GAS\\r\\n'
            timeout: Max seconds to wait (default 5.0)

        Returns:
            True if cmd: received, False on timeout.
        """
        if not self.is_connected:
            return False
        if not self._write_raw(data):
            return False
        import time as _t
        local_buf = bytearray()
        deadline = _t.monotonic() + timeout
        _t.sleep(0.05)  # give TNC time to start responding
        while _t.monotonic() < deadline:
            with self._rx_buf_lock:
                chunk = bytes(self._rx_buf)
                self._rx_buf.clear()
            self._rx_buf_event.clear()
            if chunk:
                local_buf.extend(chunk)
                if b'\\ncmd:' in local_buf or local_buf.startswith(b'cmd:'):
                    return True
            remaining = deadline - _t.monotonic()
            if remaining <= 0:
                break
            self._rx_buf_event.wait(timeout=min(0.1, remaining))
        return False

'''

marker = '    def _read_raw_until'
if marker not in content:
    print("ERROR: marker '    def _read_raw_until' not found in file!")
    sys.exit(1)

content = content.replace(marker, new_method + marker, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied successfully.")
print("Verifying...")
with open(path, 'r', encoding='utf-8') as f:
    patched = f.read()
if 'write_verbose_wait' in patched:
    print("OK: write_verbose_wait found in file.")
else:
    print("ERROR: method not found after patch!")