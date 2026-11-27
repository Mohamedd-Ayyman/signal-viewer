"""Headless checks of the Task 1 requirements.  QT_QPA_PLATFORM=offscreen python -m pytest tests"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
from PyQt5 import QtCore, QtWidgets  # noqa: E402

from signal_viewer.main_window import MainWindow  # noqa: E402
from signal_viewer.report import build_report  # noqa: E402
from signal_viewer.signal_model import load_signal  # noqa: E402

SAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "data")
application = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)


def sample(name):
    return load_signal(os.path.join(SAMPLES, f"{name}.csv"))


def new_window():
    window = MainWindow()
    window.show()
    return window


def advance(graph, frames=10):
    for _ in range(frames):
        graph._advance_frame()


def test_samples_cover_three_modalities_normal_and_abnormal():
    names = {file.rsplit(".", 1)[0] for file in os.listdir(SAMPLES)}
    assert {"ecg_normal", "ecg_arrhythmia", "emg_healthy", "emg_myopathy", "eeg_normal", "eeg_seizure"} <= names


def test_opening_a_signal_starts_cine_mode():
    window = new_window()
    window.top_graph.add_signal(sample("ecg_normal"))
    assert window.top_graph.is_playing
    advance(window.top_graph, 5)
    assert window.top_graph.cine_time > 0


def test_any_number_of_signals_per_graph():
    window = new_window()
    names = ["ecg_normal", "ecg_arrhythmia", "emg_healthy", "emg_myopathy", "eeg_normal", "eeg_seizure"]
    for repeat in range(3):
        for name in names:
            window.top_graph.add_signal(sample(name))
    assert len(window.top_graph.signals) == 18
    assert window.top_graph.signal_list.count() == 18


def test_graphs_run_independently_when_unlinked():
    window = new_window()
    window.top_graph.add_signal(sample("ecg_normal"))
    window.bottom_graph.add_signal(sample("eeg_normal"))
    window.bottom_graph.toggle_play()     # pause graph 2 only
    advance(window.top_graph, 20)
    assert window.top_graph.is_playing and not window.bottom_graph.is_playing
    assert window.top_graph.cine_time != window.bottom_graph.cine_time


def test_linked_graphs_share_time_speed_and_viewport():
    window = new_window()
    window.top_graph.add_signal(sample("ecg_normal"))
    window.bottom_graph.add_signal(sample("ecg_arrhythmia"))
    window.link_action.setChecked(True)
    window.top_graph.speed_spinbox.setValue(2.0)
    window.top_graph.zoom(0.7)
    advance(window.top_graph, 15)
    for attribute in ("speed", "time_window"):
        assert getattr(window.bottom_graph, attribute) == getattr(window.top_graph, attribute)
    assert np.isclose(window.bottom_graph.cine_time, window.top_graph.cine_time)
    assert np.allclose(window.bottom_graph.amplitude_view, window.top_graph.amplitude_view)
    window.bottom_graph.zoom(0.7)         # zooming the other graph is mirrored back
    assert window.top_graph.time_window == window.bottom_graph.time_window


def test_rewind_and_end_of_signal_options():
    window = new_window()
    graph = window.top_graph
    graph.add_signal(sample("ecg_normal"))
    graph.speed_spinbox.setValue(5.0)
    graph.loop_checkbox.setChecked(False)
    advance(graph, 200)
    assert not graph.is_playing and graph.cine_time == graph.end_time     # stops at the end
    graph.rewind()
    assert graph.cine_time == 0.0
    graph.loop_checkbox.setChecked(True)
    graph.toggle_play()
    advance(graph, 200)
    assert graph.is_playing and graph.cine_time < graph.end_time          # starts again


def test_colour_label_show_hide_and_move():
    window = new_window()
    graph = window.top_graph
    first, second = sample("ecg_normal"), sample("emg_healthy")
    graph.add_signal(first)
    graph.add_signal(second)
    graph.signal_list.item(0).setCheckState(QtCore.Qt.Unchecked)                          # hide
    assert not first.visible and not graph.curves_by_signal_id[id(first)].isVisible()
    graph.signal_list.setCurrentRow(1)
    graph.request_move()
    assert second in window.bottom_graph.signals and second not in graph.signals


def test_scroll_and_pan_never_leave_the_data():
    window = new_window()
    graph = window.top_graph
    graph.add_signal(sample("eeg_seizure"))
    graph.toggle_play()
    for _ in range(6):
        graph.zoom(0.7)
    bottom_bound, top_bound = graph.amplitude_bounds
    for slider_value in (0, 1000):
        graph.amplitude_slider.setValue(slider_value)
        view_bottom, view_top = graph.amplitude_view
        assert bottom_bound - 1e-9 <= view_bottom and view_top <= top_bound + 1e-9
    graph.time_slider.setValue(1000)
    assert graph.cine_time <= graph.end_time
    graph._on_mouse_view_change()
    graph.plot.setYRange(top_bound + 100, top_bound + 200, padding=0)      # try to drag above the signal
    view_bottom, view_top = graph.plot.viewRange()[1]
    assert view_top <= top_bound + 1e-6


def test_report_is_built_in_code_with_statistics(tmp_path):
    window = new_window()
    window.top_graph.add_signal(sample("ecg_normal"))
    window.bottom_graph.add_signal(sample("eeg_seizure"))
    window.snapshot_both()
    report = build_report(str(tmp_path / "report.pdf"), window.snapshots,
                          {"Graph 1": window.top_graph.signals, "Graph 2": window.bottom_graph.signals})
    with open(report, "rb") as pdf:
        assert pdf.read(4) == b"%PDF"
    assert len(window.snapshots) == 2 and window.snapshots[0].statistics[0]["Duration (s)"] > 0
