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
import logging

from PyQt6.QtWidgets import QApplication

from pk232py import __version__
from pk232py.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


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

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
