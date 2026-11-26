"""A single cine-mode graph with its own transport controls and signal list."""
from __future__ import annotations

import os
import tempfile
import uuid

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PyQt5 import QtCore, QtGui, QtWidgets

from .signal_model import Signal, load_signal

PALETTE = ["#00c2ff", "#ff5c8a", "#7CFC9A", "#ffb347", "#c792ea", "#f7f76d", "#4dd0e1", "#ff8a65"]
SPEEDS = {"0.5×": 0.5, "1×": 1.0, "1.5×": 1.5, "2×": 2.0, "3×": 3.0}
TICK_MS = 40


class GraphPanel(QtWidgets.QGroupBox):
    """One viewport: plot, transport bar, scroll sliders and a signal manager."""

    stateChanged = QtCore.pyqtSignal(dict)       # emitted on any user change of time/speed/zoom
    moveRequested = QtCore.pyqtSignal(object)    # Signal to move to the other panel
    status = QtCore.pyqtSignal(str)
    ticked = QtCore.pyqtSignal(float)             # cine time after each frame

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.signals: list[Signal] = []
        self.curves: dict[int, pg.PlotDataItem] = {}
        self.t = 0.0                # current cine time (right edge of the window)
        self.window = 4.0           # seconds visible
        self.speed = 1.0
        self.playing = False
        self._quiet = False         # suppress stateChanged while applying a linked state
        self.follower = False       # when linked, the follower's clock is driven by the leader

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        st = self.style()
        self.plot = pg.PlotWidget()
        self.plot.setBackground("#0b1220")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "Amplitude")
        self.plot.addLegend(offset=(10, 10))
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.sigRangeChanged.connect(self._on_mouse_range)

        def btn(icon, tip, slot, checkable=False):
            b = QtWidgets.QToolButton()
            b.setIcon(st.standardIcon(icon))
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.clicked.connect(slot)
            return b

        self.open_btn = btn(QtWidgets.QStyle.SP_DialogOpenButton, "Open signal file", self.open_file)
        self.play_btn = btn(QtWidgets.QStyle.SP_MediaPlay, "Play / pause", self.toggle_play)
        self.rewind_btn = btn(QtWidgets.QStyle.SP_MediaSkipBackward, "Rewind to start", self.rewind)
        self.loop_box = QtWidgets.QCheckBox("Loop")
        self.loop_box.setToolTip("Restart automatically when the signal ends")
        self.loop_box.setChecked(True)
        self.speed_box = QtWidgets.QComboBox()
        self.speed_box.addItems(SPEEDS.keys())
        self.speed_box.setCurrentText("1×")
        self.speed_box.currentTextChanged.connect(self._on_speed)
        zin = QtWidgets.QPushButton("Zoom +")
        zin.clicked.connect(lambda: self.zoom(0.7))
        zout = QtWidgets.QPushButton("Zoom −")
        zout.clicked.connect(lambda: self.zoom(1 / 0.7))
        snap = QtWidgets.QPushButton("Snapshot")
        snap.clicked.connect(self.take_snapshot)

        bar = QtWidgets.QHBoxLayout()
        for w in (self.open_btn, self.play_btn, self.rewind_btn, self.loop_box,
                  QtWidgets.QLabel("Speed"), self.speed_box, zin, zout, snap):
            bar.addWidget(w)
        bar.addStretch()

        # Scroll sliders: horizontal = time position, vertical = amplitude offset
        self.h_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.h_slider.setRange(0, 1000)
        self.h_slider.sliderMoved.connect(self._on_h_slider)
        self.v_slider = QtWidgets.QSlider(QtCore.Qt.Vertical)
        self.v_slider.setRange(-500, 500)
        self.v_slider.setValue(0)
        self.v_slider.sliderMoved.connect(self._on_v_slider)

        plot_row = QtWidgets.QHBoxLayout()
        plot_row.addWidget(self.plot, 1)
        plot_row.addWidget(self.v_slider)

        # Signal manager
        self.list = QtWidgets.QListWidget()
        self.list.setMaximumWidth(220)
        self.list.itemChanged.connect(self._on_item_changed)
        manage = QtWidgets.QVBoxLayout()
        manage.addWidget(QtWidgets.QLabel("Signals (tick to show)"))
        manage.addWidget(self.list, 1)
        for text, slot in (("Colour…", self.change_color), ("Rename…", self.rename),
                           ("Move to other graph", self.request_move), ("Remove", self.remove_selected)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(slot)
            manage.addWidget(b)

        left = QtWidgets.QVBoxLayout()
        left.addLayout(bar)
        left.addLayout(plot_row, 1)
        left.addWidget(self.h_slider)

        root = QtWidgets.QHBoxLayout(self)
        root.addLayout(left, 1)
        root.addLayout(manage)

    # ------------------------------------------------------------ signals
    @property
    def max_time(self) -> float:
        return max((s.time[-1] for s in self.signals), default=0.0)

    def open_file(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Open signal", os.path.join(os.getcwd(), "samples", "data"), "Signals (*.csv *.txt)")
        for p in paths:
            try:
                self.add_signal(load_signal(p))
            except Exception as exc:  # show the reason instead of crashing
                QtWidgets.QMessageBox.warning(self, "Cannot open file", f"{os.path.basename(p)}\n\n{exc}")

    def add_signal(self, sig: Signal):
        if sig.color == "#00c2ff":
            sig.color = PALETTE[len(self.signals) % len(PALETTE)]
        self.signals.append(sig)
        curve = self.plot.plot([], [], pen=pg.mkPen(sig.color, width=1.6), name=sig.label)
        self.curves[id(sig)] = curve
        item = QtWidgets.QListWidgetItem(sig.label)
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setCheckState(QtCore.Qt.Checked if sig.visible else QtCore.Qt.Unchecked)
        item.setForeground(QtGui.QBrush(QtGui.QColor(sig.color)))
        item.setData(QtCore.Qt.UserRole, id(sig))
        self.list.addItem(item)
        self._update_limits()
        self.status.emit(f"{self.title()}: loaded {sig.label} ({sig.duration:.1f} s @ {sig.sampling_rate:.0f} Hz)")
        if not self.playing:
            self.toggle_play()  # signals always open in cine mode
        self._render()

    def take_signal(self, sig: Signal):
        """Remove *sig* from this panel and return it (used when moving)."""
        curve = self.curves.pop(id(sig))
        self.plot.removeItem(curve)
        self.signals.remove(sig)
        for i in range(self.list.count()):
            if self.list.item(i).data(QtCore.Qt.UserRole) == id(sig):
                self.list.takeItem(i)
                break
        self._update_limits()
        self._render()
        return sig

    def _selected(self) -> Signal | None:
        item = self.list.currentItem()
        if item is None:
            QtWidgets.QMessageBox.information(self, "No signal selected", "Select a signal in the list first.")
            return None
        sid = item.data(QtCore.Qt.UserRole)
        return next((s for s in self.signals if id(s) == sid), None)

    def change_color(self):
        sig = self._selected()
        if not sig:
            return
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(sig.color), self, "Signal colour")
        if c.isValid():
            sig.color = c.name()
            self.curves[id(sig)].setPen(pg.mkPen(sig.color, width=1.6))
            self.list.currentItem().setForeground(QtGui.QBrush(c))

    def rename(self):
        sig = self._selected()
        if not sig:
            return
        text, ok = QtWidgets.QInputDialog.getText(self, "Signal label", "Label:", text=sig.label)
        if ok and text.strip():
            sig.label = text.strip()
            self.list.currentItem().setText(sig.label)
            self.curves[id(sig)].opts["name"] = sig.label
            self._refresh_legend()

    def request_move(self):
        sig = self._selected()
        if sig:
            self.moveRequested.emit(sig)

    def remove_selected(self):
        sig = self._selected()
        if sig:
            self.take_signal(sig)

    def _on_item_changed(self, item):
        sid = item.data(QtCore.Qt.UserRole)
        for s in self.signals:
            if id(s) == sid:
                s.visible = item.checkState() == QtCore.Qt.Checked
                self.curves[sid].setVisible(s.visible)
        self._refresh_legend()

    def _refresh_legend(self):
        legend = self.plot.plotItem.legend
        if legend is None:
            return
        legend.clear()
        for s in self.signals:
            if s.visible:
                legend.addItem(self.curves[id(s)], s.label)

    # -------------------------------------------------------------- cine
    def toggle_play(self):
        self.playing = not self.playing
        icon = QtWidgets.QStyle.SP_MediaPause if self.playing else QtWidgets.QStyle.SP_MediaPlay
        self.play_btn.setIcon(self.style().standardIcon(icon))
        if self.playing and not self.follower:
            self.timer.start()
        else:
            self.timer.stop()
        self._emit_state()

    def rewind(self):
        self.t = 0.0
        self._render()
        self._emit_state()

    def _on_speed(self, text):
        self.speed = SPEEDS[text]
        self._emit_state()

    def _tick(self):
        if not self.signals:
            return
        self.t += self.speed * TICK_MS / 1000.0
        if self.t >= self.max_time:
            if self.loop_box.isChecked():
                self.t = 0.0
            else:
                self.t = self.max_time
                self.toggle_play()
        self._render()
        self.ticked.emit(self.t)

    def follow(self, t: float):
        """Jump to the leader's cine time (used while graphs are linked)."""
        self.t = min(t, self.max_time) if self.signals else t
        self._render()

    def _render(self):
        """Draw every signal up to the current cine time and move the viewport."""
        for s in self.signals:
            idx = int(np.searchsorted(s.time, self.t, side="right"))
            self.curves[id(s)].setData(s.time[:idx], s.amplitude[:idx])
        left = max(0.0, self.t - self.window)
        self._quiet = True
        self.plot.setXRange(left, max(self.window, self.t), padding=0)
        self._quiet = False
        if self.max_time > 0:
            self.h_slider.blockSignals(True)
            self.h_slider.setValue(int(1000 * self.t / self.max_time))
            self.h_slider.blockSignals(False)

    def _update_limits(self):
        """Never allow panning/zooming outside the data (no empty viewports)."""
        if not self.signals:
            self.plot.setLimits(xMin=None, xMax=None, yMin=None, yMax=None)
            return
        ymin = min(float(np.min(s.amplitude)) for s in self.signals)
        ymax = max(float(np.max(s.amplitude)) for s in self.signals)
        pad = 0.1 * (ymax - ymin or 1.0)
        self._ybounds = (ymin - pad, ymax + pad)
        self._quiet = True
        self.plot.setLimits(xMin=0, xMax=max(self.max_time, self.window), yMin=self._ybounds[0], yMax=self._ybounds[1])
        self.plot.setYRange(*self._ybounds, padding=0)
        self._quiet = False

    def zoom(self, factor: float):
        self.window = float(np.clip(self.window * factor, 0.25, max(self.max_time, 1.0)))
        self._render()
        self._emit_state()

    def _on_h_slider(self, value):
        if self.max_time > 0:
            self.t = value / 1000.0 * self.max_time
            self._render()
            self._emit_state()

    def _on_v_slider(self, value):
        if not self.signals:
            return
        lo, hi = self._ybounds
        span = (hi - lo) / 2
        shift = value / 500.0 * span / 2
        self._quiet = True
        self.plot.setYRange(lo + span / 2 + shift, hi - span / 2 + shift, padding=0)
        self._quiet = False
        self._emit_state()

    def _on_mouse_range(self, *_):
        if self._quiet or self.playing:
            return
        (x0, x1), _ = self.plot.viewRange()
        self.window = max(0.25, x1 - x0)
        self.t = x1
        self._emit_state()

    # ------------------------------------------------------------ linking
    def state(self) -> dict:
        (x0, x1), (y0, y1) = self.plot.viewRange()
        return {"t": self.t, "window": self.window, "speed": self.speed, "playing": self.playing, "y": (y0, y1)}

    def _emit_state(self):
        if not self._quiet:
            self.stateChanged.emit(self.state())

    def apply_state(self, st: dict):
        self._quiet = True
        try:
            self.t, self.window = st["t"], st["window"]
            if self.speed != st["speed"]:
                label = next(k for k, v in SPEEDS.items() if v == st["speed"])
                self.speed_box.setCurrentText(label)
            if self.playing != st["playing"]:
                self.toggle_play()
            self._render()
            self.plot.setYRange(*st["y"], padding=0)
        finally:
            self._quiet = False

    # ----------------------------------------------------------- reporting
    def take_snapshot(self) -> str | None:
        if not self.signals:
            QtWidgets.QMessageBox.information(self, "Nothing to capture", "Open a signal first.")
            return None
        path = os.path.join(tempfile.gettempdir(), f"signal_viewer_{uuid.uuid4().hex[:8]}.png")
        exporter = pg.exporters.ImageExporter(self.plot.plotItem)
        exporter.parameters()["width"] = 1400
        exporter.export(path)
        self.window_parent().add_snapshot(f"{self.title()} at t = {self.t:.2f} s", path)
        return path

    def window_parent(self):
        w = self.parent()
        while w is not None and not hasattr(w, "add_snapshot"):
            w = w.parent()
        return w
