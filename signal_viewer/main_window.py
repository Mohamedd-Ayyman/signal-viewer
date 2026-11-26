"""Main window: two graph panels, graph linking and PDF reporting."""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets

from .graph_panel import GraphPanel
from .report import build_report


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Signal Viewer: Multi-Channel Biomedical Monitor")
        self.resize(1400, 900)
        self.snapshots: list[tuple[str, str]] = []
        self.linked = False

        self.g1 = GraphPanel("Graph 1")
        self.g2 = GraphPanel("Graph 2")
        for g, other in ((self.g1, self.g2), (self.g2, self.g1)):
            g.moveRequested.connect(lambda sig, src=g, dst=other: dst.add_signal(src.take_signal(sig)))
            g.stateChanged.connect(lambda st, dst=other: self._sync(st, dst))
            g.status.connect(self.statusBar().showMessage)
        self.g1.ticked.connect(lambda t: self.linked and self.g2.follow(t))

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        splitter.addWidget(self.g1)
        splitter.addWidget(self.g2)
        self.setCentralWidget(splitter)

        tb = self.addToolBar("Main")
        tb.setMovable(False)
        self.link_action = tb.addAction("🔗 Link graphs")
        self.link_action.setCheckable(True)
        self.link_action.toggled.connect(self.set_linked)
        tb.addSeparator()
        tb.addAction("📷 Snapshot both", self.snapshot_both)
        tb.addAction("📄 Export PDF report", self.export_report)
        self.snap_label = QtWidgets.QLabel("  Snapshots: 0")
        tb.addWidget(self.snap_label)
        self.statusBar().showMessage("Open a signal in either graph to start (File icon on each graph).")

    # ---------------------------------------------------------------- link
    def set_linked(self, on: bool):
        self.linked = on
        self.g2.follower = on            # Graph 1's clock drives Graph 2 while linked
        if on:
            self.g2.timer.stop()
            self.g2.apply_state(self.g1.state())
        elif self.g2.playing:
            self.g2.timer.start()
        self.statusBar().showMessage("Graphs linked: time, speed, zoom and pan are shared." if on
                                     else "Graphs unlinked: each graph runs independently.")

    def _sync(self, state: dict, target: GraphPanel):
        if self.linked:
            target.apply_state(state)

    # ------------------------------------------------------------- report
    def add_snapshot(self, caption: str, path: str):
        self.snapshots.append((caption, path))
        self.snap_label.setText(f"  Snapshots: {len(self.snapshots)}")
        self.statusBar().showMessage(f"Snapshot saved: {caption}")

    def snapshot_both(self):
        for g in (self.g1, self.g2):
            if g.signals:
                g.take_snapshot()

    def export_report(self):
        if not (self.g1.signals or self.g2.signals):
            QtWidgets.QMessageBox.information(self, "Nothing to report", "Open at least one signal first.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save report", "signal_report.pdf", "PDF (*.pdf)")
        if not path:
            return
        build_report(path, self.snapshots, {"Graph 1": self.g1.signals, "Graph 2": self.g2.signals})
        QtWidgets.QMessageBox.information(self, "Report saved",
                                          f"Report with {len(self.snapshots)} snapshot(s) saved to:\n{path}")
