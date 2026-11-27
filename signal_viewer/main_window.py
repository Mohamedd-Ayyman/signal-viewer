"""Main window: two identical graph panels, graph linking and PDF reporting."""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets

from .graph_panel import GraphPanel
from .report import Snapshot, build_report
from .signal_model import Signal


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Signal Viewer: Multi-Channel Biomedical Monitor")
        self.resize(1400, 900)
        self.snapshots: list[Snapshot] = []
        self.is_linked = False

        self.top_graph = GraphPanel("Graph 1")
        self.bottom_graph = GraphPanel("Graph 2")
        for source_graph, other_graph in ((self.top_graph, self.bottom_graph), (self.bottom_graph, self.top_graph)):
            source_graph.moveRequested.connect(
                lambda signal, source=source_graph, target=other_graph: target.add_signal(source.take_signal(signal)))
            source_graph.viewStateChanged.connect(lambda state, target=other_graph: self._mirror_view(state, target))
            source_graph.statusMessage.connect(self.statusBar().showMessage)
        self.top_graph.cineTimeAdvanced.connect(
            lambda leader_time: self.is_linked and self.bottom_graph.follow(leader_time))

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        splitter.addWidget(self.top_graph)
        splitter.addWidget(self.bottom_graph)
        self.setCentralWidget(splitter)

        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        self.link_action = toolbar.addAction("Link graphs")
        self.link_action.setCheckable(True)
        self.link_action.toggled.connect(self.set_linked)
        toolbar.addSeparator()
        toolbar.addAction("Snapshot both", self.snapshot_both)
        toolbar.addAction("Export PDF report", self.export_report)
        toolbar.addAction("Clear snapshots", self.clear_snapshots)
        self.snapshot_count_label = QtWidgets.QLabel("  Snapshots: 0")
        toolbar.addWidget(self.snapshot_count_label)
        self.statusBar().showMessage("Open signals in either graph with its folder button. Any number of signals per graph.")

    # ---------------------------------------------------------------- link
    def set_linked(self, linked: bool):
        self.is_linked = linked
        self.bottom_graph.is_follower = linked      # Graph 1's clock drives Graph 2 while linked
        if linked:
            self.bottom_graph.frame_timer.stop()
            self.bottom_graph.apply_view_state(self.top_graph.view_state())
        elif self.bottom_graph.is_playing:
            self.bottom_graph.frame_timer.start()
        self.statusBar().showMessage("Graphs linked: time frame, speed, zoom and pan are shared." if linked
                                     else "Graphs unlinked: each graph runs independently.")

    def _mirror_view(self, state: dict, target_graph: GraphPanel):
        if self.is_linked:
            target_graph.apply_view_state(state)

    # ------------------------------------------------------------- report
    def add_snapshot(self, caption: str, image_path: str, signals: list[Signal]):
        shown_signals = [signal for signal in signals if signal.visible]
        self.snapshots.append(Snapshot(caption, image_path, [signal.statistics() for signal in shown_signals]))
        self.snapshot_count_label.setText(f"  Snapshots: {len(self.snapshots)}")
        self.statusBar().showMessage(f"Snapshot saved: {caption}")

    def snapshot_both(self):
        for graph in (self.top_graph, self.bottom_graph):
            if graph.signals:
                graph.take_snapshot()

    def clear_snapshots(self):
        self.snapshots.clear()
        self.snapshot_count_label.setText("  Snapshots: 0")

    def export_report(self):
        if not (self.top_graph.signals or self.bottom_graph.signals):
            QtWidgets.QMessageBox.information(self, "Nothing to report", "Open at least one signal first.")
            return
        report_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save report", "signal_report.pdf", "PDF (*.pdf)")
        if not report_path:
            return
        build_report(report_path, self.snapshots,
                     {"Graph 1": self.top_graph.signals, "Graph 2": self.bottom_graph.signals})
        QtWidgets.QMessageBox.information(self, "Report saved",
                                          f"Report with {len(self.snapshots)} snapshot(s) saved to:\n{report_path}")
