"""A single cine-mode graph with its own transport controls and signal list.

Every panel holds any number of signals (the list grows as files are opened),
plays them like an ICU monitor, and exposes a small view state so two panels
can be linked.
"""
from __future__ import annotations

import os
import tempfile
import uuid

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PyQt5 import QtCore, QtGui, QtWidgets

from .signal_model import SUPPORTED_EXTENSIONS, Signal, load_signal

SIGNAL_COLORS = ["#00c2ff", "#ff5c8a", "#7CFC9A", "#ffb347", "#c792ea", "#f7f76d", "#4dd0e1", "#ff8a65"]
DEFAULT_SIGNAL_COLOR = SIGNAL_COLORS[0]
FRAME_INTERVAL_MS = 40            # cine refresh period (25 frames per second)
ZOOM_STEP = 0.7                   # each Zoom + shows 70% of the previous view
MIN_TIME_WINDOW_S = 0.25          # narrowest visible time span
DEFAULT_TIME_WINDOW_S = 4.0
SLIDER_RESOLUTION = 1000          # slider steps across the scrollable range
AMPLITUDE_MARGIN = 0.1            # 10% head-room above and below the signals


class GraphPanel(QtWidgets.QGroupBox):
    """One viewport: plot, transport bar, scroll sliders and a signal manager."""

    viewStateChanged = QtCore.pyqtSignal(dict)    # emitted on any user change of time, speed or zoom
    moveRequested = QtCore.pyqtSignal(object)     # a Signal the user wants in the other panel
    statusMessage = QtCore.pyqtSignal(str)
    cineTimeAdvanced = QtCore.pyqtSignal(float)   # cine time after each frame (drives a linked panel)

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.signals: list[Signal] = []                    # unlimited: one entry per opened file
        self.curves_by_signal_id: dict[int, pg.PlotDataItem] = {}
        self.cine_time = 0.0                               # right edge of the visible time window (s)
        self.time_window = DEFAULT_TIME_WINDOW_S           # visible time span (s)
        self.amplitude_view: tuple[float, float] | None = None   # visible amplitude range
        self.amplitude_bounds = (-1.0, 1.0)                # full amplitude range of every opened signal
        self.speed = 1.0
        self.is_playing = False
        self.is_follower = False          # when linked, the leader's clock drives this panel
        self._applying_view = False       # suppress feedback while the code itself moves the view

        self.frame_timer = QtCore.QTimer(self)
        self.frame_timer.setInterval(FRAME_INTERVAL_MS)
        self.frame_timer.timeout.connect(self._advance_frame)
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        style = self.style()
        self.plot = pg.PlotWidget()
        self.plot.setBackground("#0b1220")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "Amplitude")
        self.plot.addLegend(offset=(10, 10))
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.sigRangeChanged.connect(self._on_mouse_view_change)

        def tool_button(icon, tooltip, handler):
            button = QtWidgets.QToolButton()
            button.setIcon(style.standardIcon(icon))
            button.setToolTip(tooltip)
            button.clicked.connect(handler)
            return button

        self.open_button = tool_button(QtWidgets.QStyle.SP_DialogOpenButton, "Open signal files", self.open_files)
        self.play_button = tool_button(QtWidgets.QStyle.SP_MediaPlay, "Play / pause", self.toggle_play)
        self.rewind_button = tool_button(QtWidgets.QStyle.SP_MediaSkipBackward, "Rewind to the start", self.rewind)
        self.loop_checkbox = QtWidgets.QCheckBox("Rewind at end")
        self.loop_checkbox.setToolTip("On: start again from the beginning when the signal ends. Off: stop at the end.")
        self.loop_checkbox.setChecked(True)

        self.speed_spinbox = QtWidgets.QDoubleSpinBox()
        self.speed_spinbox.setRange(0.25, 5.0)
        self.speed_spinbox.setSingleStep(0.25)
        self.speed_spinbox.setDecimals(2)
        self.speed_spinbox.setSuffix(" ×")
        self.speed_spinbox.setValue(1.0)
        self.speed_spinbox.setToolTip("Cine speed")
        self.speed_spinbox.valueChanged.connect(self._on_speed_changed)

        zoom_in_button = QtWidgets.QPushButton("Zoom +")
        zoom_in_button.clicked.connect(lambda: self.zoom(ZOOM_STEP))
        zoom_out_button = QtWidgets.QPushButton("Zoom −")
        zoom_out_button.clicked.connect(lambda: self.zoom(1 / ZOOM_STEP))
        reset_view_button = QtWidgets.QPushButton("Fit")
        reset_view_button.setToolTip("Show the full amplitude range and the default time window")
        reset_view_button.clicked.connect(self.reset_view)
        snapshot_button = QtWidgets.QPushButton("Snapshot")
        snapshot_button.clicked.connect(self.take_snapshot)

        transport_bar = QtWidgets.QHBoxLayout()
        for widget in (self.open_button, self.play_button, self.rewind_button, self.loop_checkbox,
                       QtWidgets.QLabel("Speed"), self.speed_spinbox, zoom_in_button, zoom_out_button,
                       reset_view_button, snapshot_button):
            transport_bar.addWidget(widget)
        transport_bar.addStretch()

        # Scroll sliders: horizontal moves through time, vertical moves through amplitude.
        self.time_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.time_slider.setRange(0, SLIDER_RESOLUTION)
        self.time_slider.setToolTip("Scroll through time")
        self.time_slider.valueChanged.connect(self._on_time_slider)
        self.amplitude_slider = QtWidgets.QSlider(QtCore.Qt.Vertical)
        self.amplitude_slider.setRange(0, SLIDER_RESOLUTION)
        self.amplitude_slider.setValue(SLIDER_RESOLUTION // 2)
        self.amplitude_slider.setToolTip("Scroll up and down (zoom in first)")
        self.amplitude_slider.valueChanged.connect(self._on_amplitude_slider)

        plot_row = QtWidgets.QHBoxLayout()
        plot_row.addWidget(self.plot, 1)
        plot_row.addWidget(self.amplitude_slider)

        # Signal manager: one row per opened signal, however many there are.
        self.signal_list = QtWidgets.QListWidget()
        self.signal_list.setMaximumWidth(230)
        self.signal_list.itemChanged.connect(self._on_signal_item_changed)
        manager = QtWidgets.QVBoxLayout()
        manager.addWidget(QtWidgets.QLabel("Signals (tick to show)"))
        manager.addWidget(self.signal_list, 1)
        for text, handler in (("Colour…", self.change_color), ("Rename…", self.rename),
                              ("Move to other graph", self.request_move), ("Remove", self.remove_selected)):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(handler)
            manager.addWidget(button)

        plot_column = QtWidgets.QVBoxLayout()
        plot_column.addLayout(transport_bar)
        plot_column.addLayout(plot_row, 1)
        plot_column.addWidget(self.time_slider)

        root = QtWidgets.QHBoxLayout(self)
        root.addLayout(plot_column, 1)
        root.addLayout(manager)

    # ------------------------------------------------------------ signals
    @property
    def end_time(self) -> float:
        return max((signal.time[-1] for signal in self.signals), default=0.0)

    def open_files(self):
        patterns = " ".join(f"*{extension}" for extension in SUPPORTED_EXTENSIONS)
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Open signal", os.path.join(os.getcwd(), "samples", "data"), f"Signals ({patterns})")
        for path in paths:
            try:
                self.add_signal(load_signal(path))
            except Exception as error:  # show the reason instead of crashing
                QtWidgets.QMessageBox.warning(self, "Cannot open file", f"{os.path.basename(path)}\n\n{error}")

    def add_signal(self, signal: Signal):
        if signal.color == DEFAULT_SIGNAL_COLOR and self.signals:
            signal.color = SIGNAL_COLORS[len(self.signals) % len(SIGNAL_COLORS)]
        self.signals.append(signal)
        curve = self.plot.plot([], [], pen=pg.mkPen(signal.color, width=1.6), name=signal.label)
        curve.setVisible(signal.visible)
        self.curves_by_signal_id[id(signal)] = curve
        list_item = QtWidgets.QListWidgetItem(signal.label)
        list_item.setFlags(list_item.flags() | QtCore.Qt.ItemIsUserCheckable)
        list_item.setCheckState(QtCore.Qt.Checked if signal.visible else QtCore.Qt.Unchecked)
        list_item.setForeground(QtGui.QBrush(QtGui.QColor(signal.color)))
        list_item.setData(QtCore.Qt.UserRole, id(signal))
        self.signal_list.addItem(list_item)
        self._update_bounds()
        self.statusMessage.emit(
            f"{self.title()}: loaded {signal.label} ({signal.duration:.1f} s @ {signal.sampling_rate:.0f} Hz)")
        if not self.is_playing:
            self.toggle_play()  # a newly opened signal always starts in cine mode, never static
        self._render()

    def take_signal(self, signal: Signal) -> Signal:
        """Remove *signal* from this panel and return it (used when moving it to the other panel)."""
        self.plot.removeItem(self.curves_by_signal_id.pop(id(signal)))
        self.signals.remove(signal)
        for row in range(self.signal_list.count()):
            if self.signal_list.item(row).data(QtCore.Qt.UserRole) == id(signal):
                self.signal_list.takeItem(row)
                break
        self._update_bounds()
        self._refresh_legend()
        self._render()
        return signal

    def _selected_signal(self) -> Signal | None:
        list_item = self.signal_list.currentItem()
        if list_item is None:
            QtWidgets.QMessageBox.information(self, "No signal selected", "Select a signal in the list first.")
            return None
        signal_id = list_item.data(QtCore.Qt.UserRole)
        return next((signal for signal in self.signals if id(signal) == signal_id), None)

    def change_color(self):
        signal = self._selected_signal()
        if not signal:
            return
        chosen_color = QtWidgets.QColorDialog.getColor(QtGui.QColor(signal.color), self, "Signal colour")
        if chosen_color.isValid():
            signal.color = chosen_color.name()
            self.curves_by_signal_id[id(signal)].setPen(pg.mkPen(signal.color, width=1.6))
            self.signal_list.currentItem().setForeground(QtGui.QBrush(chosen_color))
            self._refresh_legend()

    def rename(self):
        signal = self._selected_signal()
        if not signal:
            return
        new_label, accepted = QtWidgets.QInputDialog.getText(self, "Signal label", "Label:", text=signal.label)
        if accepted and new_label.strip():
            signal.label = new_label.strip()
            self.signal_list.currentItem().setText(signal.label)
            self.curves_by_signal_id[id(signal)].opts["name"] = signal.label
            self._refresh_legend()

    def request_move(self):
        signal = self._selected_signal()
        if signal:
            self.moveRequested.emit(signal)

    def remove_selected(self):
        signal = self._selected_signal()
        if signal:
            self.take_signal(signal)

    def _on_signal_item_changed(self, list_item):
        signal_id = list_item.data(QtCore.Qt.UserRole)
        for signal in self.signals:
            if id(signal) == signal_id:
                signal.visible = list_item.checkState() == QtCore.Qt.Checked
                self.curves_by_signal_id[signal_id].setVisible(signal.visible)
        self._refresh_legend()

    def _refresh_legend(self):
        legend = self.plot.plotItem.legend
        if legend is None:
            return
        legend.clear()
        for signal in self.signals:
            if signal.visible:
                legend.addItem(self.curves_by_signal_id[id(signal)], signal.label)

    # -------------------------------------------------------------- cine
    def toggle_play(self):
        self.is_playing = not self.is_playing
        icon = QtWidgets.QStyle.SP_MediaPause if self.is_playing else QtWidgets.QStyle.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(icon))
        if self.is_playing and not self.is_follower:
            if self.signals and self.cine_time >= self.end_time:
                self.cine_time = 0.0  # pressing play at the end starts over, like a media player
            self.frame_timer.start()
        else:
            self.frame_timer.stop()
        self._emit_view_state()

    def rewind(self):
        self.cine_time = 0.0
        self._render()
        self._emit_view_state()

    def _on_speed_changed(self, speed: float):
        self.speed = float(speed)
        self._emit_view_state()

    def _advance_frame(self):
        if not self.signals or not self.is_playing:
            return
        self.cine_time += self.speed * FRAME_INTERVAL_MS / 1000.0
        if self.cine_time >= self.end_time:
            if self.loop_checkbox.isChecked():
                self.cine_time = 0.0
            else:
                self.cine_time = self.end_time
                self.toggle_play()
        self._render()
        self.cineTimeAdvanced.emit(self.cine_time)

    def follow(self, leader_time: float):
        """Jump to the leader's cine time (used while the graphs are linked)."""
        self.cine_time = min(leader_time, self.end_time) if self.signals else leader_time
        self._render()

    # ----------------------------------------------------------- viewport
    def _render(self):
        """Draw every signal (shown or hidden) up to the cine time and move the viewport."""
        for signal in self.signals:
            last_sample = int(np.searchsorted(signal.time, self.cine_time, side="right"))
            self.curves_by_signal_id[id(signal)].setData(signal.time[:last_sample], signal.amplitude[:last_sample])
        window_start = max(0.0, self.cine_time - self.time_window)
        window_end = max(self.time_window, self.cine_time)
        self._applying_view = True
        self.plot.setXRange(window_start, window_end, padding=0)
        if self.amplitude_view is not None:
            self.plot.setYRange(*self.amplitude_view, padding=0)
        self._applying_view = False
        self._sync_sliders()

    def _update_bounds(self):
        """Limit pan, zoom and scroll to the data so the view can never go empty."""
        if not self.signals:
            self.plot.setLimits(xMin=None, xMax=None, yMin=None, yMax=None)
            self.amplitude_view = None
            return
        lowest = min(float(np.min(signal.amplitude)) for signal in self.signals)
        highest = max(float(np.max(signal.amplitude)) for signal in self.signals)
        margin = AMPLITUDE_MARGIN * (highest - lowest or 1.0)
        self.amplitude_bounds = (lowest - margin, highest + margin)
        self.time_window = float(np.clip(self.time_window, MIN_TIME_WINDOW_S, max(self.end_time, MIN_TIME_WINDOW_S)))
        self._applying_view = True
        self.plot.setLimits(xMin=0, xMax=max(self.end_time, self.time_window),
                            yMin=self.amplitude_bounds[0], yMax=self.amplitude_bounds[1])
        self._applying_view = False
        self.amplitude_view = self._clamp_amplitude_view(*(self.amplitude_view or self.amplitude_bounds))

    def _clamp_amplitude_view(self, view_bottom: float, view_top: float) -> tuple[float, float]:
        bound_bottom, bound_top = self.amplitude_bounds
        view_height = min(view_top - view_bottom, bound_top - bound_bottom)
        view_bottom = float(np.clip(view_bottom, bound_bottom, bound_top - view_height))
        return view_bottom, view_bottom + view_height

    def zoom(self, factor: float):
        """Zoom time and amplitude together around the centre of the current view."""
        if not self.signals:
            return
        self.time_window = float(np.clip(self.time_window * factor, MIN_TIME_WINDOW_S, max(self.end_time, 1.0)))
        view_bottom, view_top = self.amplitude_view or self.amplitude_bounds
        centre = (view_bottom + view_top) / 2
        half_height = (view_top - view_bottom) * factor / 2
        self.amplitude_view = self._clamp_amplitude_view(centre - half_height, centre + half_height)
        self._render()
        self._emit_view_state()

    def reset_view(self):
        self.time_window = DEFAULT_TIME_WINDOW_S
        self.amplitude_view = self.amplitude_bounds if self.signals else None
        self._update_bounds()
        self._render()
        self._emit_view_state()

    def _sync_sliders(self):
        """Keep both sliders in step with the view without triggering their handlers."""
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(int(SLIDER_RESOLUTION * self.cine_time / self.end_time) if self.end_time else 0)
        self.time_slider.blockSignals(False)
        self.amplitude_slider.blockSignals(True)
        if self.amplitude_view is not None:
            bound_bottom, bound_top = self.amplitude_bounds
            view_bottom, view_top = self.amplitude_view
            scrollable = (bound_top - bound_bottom) - (view_top - view_bottom)
            position = (view_bottom - bound_bottom) / scrollable if scrollable > 1e-12 else 0.5
            self.amplitude_slider.setValue(int(SLIDER_RESOLUTION * position))
        self.amplitude_slider.setEnabled(self._can_scroll_amplitude())
        self.amplitude_slider.blockSignals(False)

    def _can_scroll_amplitude(self) -> bool:
        if self.amplitude_view is None:
            return False
        return (self.amplitude_view[1] - self.amplitude_view[0]) < (self.amplitude_bounds[1] - self.amplitude_bounds[0]) - 1e-9

    def _on_time_slider(self, value: int):
        if self.end_time > 0:
            self.cine_time = value / SLIDER_RESOLUTION * self.end_time
            self._render()
            self._emit_view_state()

    def _on_amplitude_slider(self, value: int):
        if not self._can_scroll_amplitude():
            return
        bound_bottom, bound_top = self.amplitude_bounds
        view_height = self.amplitude_view[1] - self.amplitude_view[0]
        view_bottom = bound_bottom + value / SLIDER_RESOLUTION * ((bound_top - bound_bottom) - view_height)
        self.amplitude_view = (view_bottom, view_bottom + view_height)
        self._render()
        self._emit_view_state()

    def _on_mouse_view_change(self, *_):
        """Mouse wheel zoom and drag pan, during playback or while paused."""
        if self._applying_view or not self.signals:
            return
        (time_start, time_end), (view_bottom, view_top) = self.plot.viewRange()
        self.time_window = max(MIN_TIME_WINDOW_S, time_end - time_start)
        if not self.is_playing:
            self.cine_time = min(time_end, self.end_time)  # dragging while paused scrubs through time
        self.amplitude_view = self._clamp_amplitude_view(view_bottom, view_top)
        self._sync_sliders()
        self._emit_view_state()

    # ------------------------------------------------------------ linking
    def view_state(self) -> dict:
        return {"cine_time": self.cine_time, "time_window": self.time_window, "speed": self.speed,
                "is_playing": self.is_playing, "amplitude_view": self.amplitude_view}

    def _emit_view_state(self):
        if not self._applying_view:
            self.viewStateChanged.emit(self.view_state())

    def apply_view_state(self, state: dict):
        """Copy the other panel's time frame, speed, zoom and pan (linked mode)."""
        self._applying_view = True
        try:
            self.cine_time = min(state["cine_time"], self.end_time) if self.signals else state["cine_time"]
            self.time_window = state["time_window"]
            self.speed_spinbox.blockSignals(True)
            self.speed_spinbox.setValue(state["speed"])
            self.speed_spinbox.blockSignals(False)
            self.speed = state["speed"]
            if self.is_playing != state["is_playing"]:
                self.toggle_play()
            if state["amplitude_view"] is not None and self.signals:
                self.amplitude_view = self._clamp_amplitude_view(*state["amplitude_view"])
            self._render()
        finally:
            self._applying_view = False

    # ----------------------------------------------------------- reporting
    def take_snapshot(self) -> str | None:
        if not self.signals:
            QtWidgets.QMessageBox.information(self, "Nothing to capture", "Open a signal first.")
            return None
        image_path = os.path.join(tempfile.gettempdir(), f"signal_viewer_{uuid.uuid4().hex[:8]}.png")
        exporter = pg.exporters.ImageExporter(self.plot.plotItem)
        exporter.parameters()["width"] = 1400
        exporter.export(image_path)
        main_window = self.main_window()
        if main_window is not None:
            main_window.add_snapshot(f"{self.title()} at t = {self.cine_time:.2f} s", image_path, self.signals)
        return image_path

    def main_window(self):
        ancestor = self.parent()
        while ancestor is not None and not hasattr(ancestor, "add_snapshot"):
            ancestor = ancestor.parent()
        return ancestor
