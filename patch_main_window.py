"""Patch script: applies two changes to main_window.py"""
import sys

path = r'E:\PK232\pk232py_repo\src\pk232py\ui\main_window.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# --- Patch 1: ParamsUploader echo_callback ---
old1 = ('            uploader = ParamsUploader(self._serial, self._app_config)\n'
        '            n = uploader.upload()')
new1 = ('            uploader = ParamsUploader(\n'
        '                self._serial,\n'
        '                self._app_config,\n'
        '                echo_callback=self._vt_append,\n'
        '            )\n'
        '            n = uploader.upload()')

if old1 in content:
    content = content.replace(old1, new1)
    print("Patch 1 OK: ParamsUploader echo_callback")
    changes += 1
else:
    print("Patch 1 FEHLER: ParamsUploader nicht gefunden")

# --- Patch 2: _on_vt_rx_data Leerzeile vor cmd: ---
old2 = ("        self._vt_append(text, color=\"#cccccc\")\n"
        "\n"
        "    def _on_raw_data_received")
new2 = ("        # Insert blank line before cmd: to separate response blocks\n"
        "        text = text.replace('cmd:', '\\ncmd:')\n"
        "        self._vt_append(text, color=\"#cccccc\")\n"
        "\n"
        "    def _on_raw_data_received")

if old2 in content:
    content = content.replace(old2, new2)
    print("Patch 2 OK: Leerzeile vor cmd:")
    changes += 1
else:
    print("Patch 2 FEHLER: _on_vt_rx_data Ende nicht gefunden")

if changes == 0:
    print("KEINE Änderungen angewendet!")
    sys.exit(1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n{changes}/2 Patches angewendet.")
print("Verifying...")
with open(path, 'r', encoding='utf-8') as f:
    check = f.read()
print("echo_callback:", "echo_callback=self._vt_append" in check)
print("Leerzeile vor cmd::", "replace('cmd:', '\\ncmd:')" in check)