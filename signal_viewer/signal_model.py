"""Signal loading and statistics.

Supported inputs
----------------
* CSV / TXT with two numeric columns: time (s) and amplitude
* CSV / TXT with a single amplitude column (sampling rate taken from ``default_fs``)
A header row is detected automatically and ignored.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

SUPPORTED_EXTENSIONS = (".csv", ".txt")


@dataclass
class Signal:
    name: str
    time: np.ndarray
    amplitude: np.ndarray
    color: str = "#00c2ff"
    visible: bool = True
    source: str = ""
    label: str = field(default="")

    def __post_init__(self):
        if not self.label:
            self.label = self.name

    # ---- derived properties -------------------------------------------------
    @property
    def duration(self) -> float:
        return float(self.time[-1] - self.time[0]) if len(self.time) > 1 else 0.0

    @property
    def sampling_rate(self) -> float:
        if len(self.time) < 2:
            return 0.0
        return float(1.0 / np.median(np.diff(self.time)))

    def statistics(self) -> dict:
        a = self.amplitude
        return {
            "Signal": self.label,
            "Mean": float(np.mean(a)),
            "Std": float(np.std(a)),
            "Min": float(np.min(a)),
            "Max": float(np.max(a)),
            "Duration (s)": self.duration,
            "Fs (Hz)": self.sampling_rate,
        }


def load_signal(path: str, default_fs: float = 250.0) -> Signal:
    """Read a signal file into a :class:`Signal`."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext}'. Use {', '.join(SUPPORTED_EXTENSIONS)}.")

    sep = "," if ext == ".csv" else r"[\s,;]+"
    df = pd.read_csv(path, sep=sep, engine="python", header=None, comment="#")
    df = df.apply(pd.to_numeric, errors="coerce")
    # Drop a header row (or any non-numeric rows) and fully empty columns
    df = df.dropna(how="all", axis=1).dropna(how="any", axis=0)
    if df.empty:
        raise ValueError("The file does not contain numeric samples.")

    if df.shape[1] >= 2:
        time = df.iloc[:, 0].to_numpy(dtype=float)
        amp = df.iloc[:, 1].to_numpy(dtype=float)
        if not np.all(np.diff(time) > 0):  # first column is not a time axis
            amp = df.iloc[:, 0].to_numpy(dtype=float)
            time = np.arange(len(amp)) / default_fs
    else:
        amp = df.iloc[:, 0].to_numpy(dtype=float)
        time = np.arange(len(amp)) / default_fs

    name = os.path.splitext(os.path.basename(path))[0]
    return Signal(name=name, time=time - time[0], amplitude=amp, source=path)
