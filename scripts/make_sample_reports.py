"""Build the sample PDF reports in docs/sample-reports by driving the real app headlessly.

QT_QPA_PLATFORM=offscreen python scripts/make_sample_reports.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5 import QtWidgets  # noqa: E402

from signal_viewer.main_window import MainWindow  # noqa: E402
from signal_viewer.report import build_report  # noqa: E402
from signal_viewer.signal_model import load_signal  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(PROJECT_ROOT, "samples", "data")
OUTPUT = os.path.join(PROJECT_ROOT, "docs", "sample-reports")

# (report file, signals for graph 1, signals for graph 2, snapshot times in seconds)
SCENARIOS = [
    ("report_1-signal_1-snapshot.pdf", ["ecg_normal"], [], [6.0]),
    ("report_3-signals_2-snapshots.pdf", ["ecg_normal", "ecg_arrhythmia"], ["eeg_seizure"], [9.0]),
    ("report_6-signals_4-snapshots.pdf", ["ecg_normal", "ecg_arrhythmia", "emg_healthy"],
     ["eeg_normal", "eeg_seizure", "emg_myopathy"], [5.0, 12.0]),
]


def main():
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    os.makedirs(OUTPUT, exist_ok=True)
    for report_name, top_signals, bottom_signals, snapshot_times in SCENARIOS:
        window = MainWindow()
        window.resize(1400, 900)
        window.show()
        for graph, names in ((window.top_graph, top_signals), (window.bottom_graph, bottom_signals)):
            for name in names:
                graph.add_signal(load_signal(os.path.join(SAMPLES, f"{name}.csv")))
            if graph.is_playing:
                graph.toggle_play()
        for snapshot_time in snapshot_times:
            for graph in (window.top_graph, window.bottom_graph):
                if graph.signals:
                    graph.cine_time = min(snapshot_time, graph.end_time)
                    graph._render()
                    application.processEvents()
                    graph.take_snapshot()
        path = os.path.join(OUTPUT, report_name)
        build_report(path, window.snapshots, {"Graph 1": window.top_graph.signals,
                                              "Graph 2": window.bottom_graph.signals})
        print(f"wrote {path} ({len(window.snapshots)} snapshots)")
        window.close()


if __name__ == "__main__":
    main()
