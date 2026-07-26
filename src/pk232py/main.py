# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <https://www.gnu.org/licenses/>.

"""Application entry point."""

import sys
import os
import logging
import tempfile

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from pk232py import __version__
from pk232py.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def _close_nuitka_splash() -> None:
    """Dismiss the native Nuitka onefile splash screen (Windows only).

    Nuitka shows the splash while the onefile payload is unpacked and
    keeps it up until we delete the feedback file it created in TEMP.
    NUITKA_ONEFILE_PARENT only exists inside a compiled onefile build,
    so this is a harmless no-op when running from source or in a
    non-onefile build - same idea as the try/__compiled__ guard used
    in ui/screens/help_viewer.py.
    """
    parent = os.environ.get("NUITKA_ONEFILE_PARENT")
    if not parent:
        return  # not a onefile build -> nothing to dismiss
    splash_file = os.path.join(
        tempfile.gettempdir(),
        f"onefile_{int(parent)}_splash_feedback.tmp",
    )
    try:
        os.unlink(splash_file)
    except OSError:
        pass  # already gone or never created


def main() -> None:
    """Launch PK232PY."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    logger.info("PK232PY v%s starting", __version__)

    app = QApplication(sys.argv)
    app.setApplicationName("PK232PY")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("OE3GAS")

    window = MainWindow()
    window.show()

    # show() only schedules the paint; dismissing the splash immediately
    # can flash the still-empty window. singleShot(0) lets the paint
    # event run first, then removes the splash underneath - seamless.
    QTimer.singleShot(0, _close_nuitka_splash)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
