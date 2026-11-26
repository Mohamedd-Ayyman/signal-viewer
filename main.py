"""Entry point: python main.py"""
import sys

import pyqtgraph as pg
from PyQt5 import QtWidgets

from signal_viewer.main_window import MainWindow


def main():
    pg.setConfigOptions(antialias=True)
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
