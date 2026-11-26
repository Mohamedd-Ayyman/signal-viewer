<div align="center">

# 📈 Signal Viewer

**A multi-channel biomedical signal monitor for ECG, EMG and EEG, with ICU-style cine playback, two linkable graphs and one-click PDF reports.**

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PyQt5](https://img.shields.io/badge/PyQt5-41CD52?style=for-the-badge&logo=qt&logoColor=white)
![pyqtgraph](https://img.shields.io/badge/pyqtgraph-1f425f?style=for-the-badge)
![NumPy](https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![ReportLab](https://img.shields.io/badge/ReportLab-PDF-B31B1B?style=for-the-badge)

</div>

---

## 📖 Overview

Monitoring vital signals is central to every ICU. **Signal Viewer** lets you open several recordings, watch them stream like a bedside monitor, compare them in two graphs, and document what you see in a PDF report generated in code.

The idea comes from the *Digital Signal Processing* course at Cairo University's Faculty of Engineering. This repository is a ground-up rewrite with a modular architecture.

## ✨ Features

### Two graphs, independent or linked
- Each graph has its **own transport controls**, speed, zoom and signal list
- **🔗 Link graphs** to share the time frame, cine speed, zoom and pan; unlink to run them separately

### ICU-style cine mode
- Signals always open **streaming in real time**, never as a static plot
- **Play / pause**, **rewind**, and a **loop** toggle that restarts a signal when it ends
- **Cine speed** presets: 0.5×, 1×, 1.5×, 2× and 3×

### Live manipulation
- Per-signal **colour**, **label** and **show/hide**
- **Move** a signal from one graph to the other, or remove it
- **Zoom** in and out, **scroll** with the horizontal (time) and vertical (amplitude) sliders, and **pan** with the mouse
- **Bounded viewports**: pan and zoom are limited to the signal's own time and amplitude range, so you never scroll into an empty graph

### Reporting
- Take **snapshots** of either graph, or both at once
- **Export a multi-page PDF** built with ReportLab, containing snapshots and a table of statistics for every signal: **mean, std, min, max, duration and sampling rate**

## 🏗️ Architecture

```
main.py                     # entry point
signal_viewer/
├── signal_model.py         # Signal dataclass, CSV/TXT loader (auto header + time-axis detection), statistics
├── graph_panel.py          # GraphPanel: plot, cine timer, controls, signal manager, linking state
├── main_window.py          # two panels, leader/follower linking, snapshots, report export
└── report.py               # PDF report (title, statistics tables, snapshots) with ReportLab
samples/
└── generate_samples.py     # synthetic normal and abnormal ECG / EMG / EEG recordings
```

**Linking design.** Every panel exposes a small state object: cine time, window width, speed, play state and amplitude range. User actions emit it, and the other panel applies it with echo suppression. While the graphs are linked, Graph 1's clock drives Graph 2 frame by frame, so the two never drift apart.

## 🧪 Sample signals

Generate six example recordings (a normal and an abnormal one for each modality) with `python samples/generate_samples.py`:

| File | Description |
|---|---|
| `ecg_normal.csv` / `ecg_arrhythmia.csv` | 72 bpm sinus rhythm / premature wide-complex (PVC-like) beats |
| `emg_healthy.csv` / `emg_myopathy.csv` | Normal bursts / low-amplitude, polyphasic potentials |
| `eeg_normal.csv` / `eeg_seizure.csv` | Alpha/theta background / 3 Hz spike-and-wave discharge |

Your own files work too: a CSV/TXT with **time, amplitude** columns, or a single amplitude column (assumed 250 Hz).

## 🚀 Getting Started

```bash
git clone https://github.com/Mohamedd-Ayyman/signal-viewer.git
cd signal-viewer
pip install -r requirements.txt
python samples/generate_samples.py     # creates samples/data/*.csv
python main.py
```

1. Click the **folder icon** on Graph 1 and open `ecg_normal.csv` and `ecg_arrhythmia.csv`.
2. Open `eeg_seizure.csv` in Graph 2, then press **🔗 Link graphs**.
3. Take a few **snapshots**, then choose **📄 Export PDF report**.

## 👤 Author

**Mohamed Ayman** · [GitHub](https://github.com/Mohamedd-Ayyman) · [LinkedIn](https://linkedin.com/in/mohamed-ayman-8787b0269)
