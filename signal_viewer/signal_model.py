"""Signal loading and statistics.

Supported inputs
----------------
* CSV / TXT with two numeric columns: time (s) and amplitude
* CSV / TXT with a single amplitude column (sampling rate taken from ``default_sampling_rate``)
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
        return {
            "Signal": self.label,
            "Mean": float(np.mean(self.amplitude)),
            "Std": float(np.std(self.amplitude)),
            "Min": float(np.min(self.amplitude)),
            "Max": float(np.max(self.amplitude)),
            "Duration (s)": self.duration,
            "Fs (Hz)": self.sampling_rate,
        }


def load_signal(path: str, default_sampling_rate: float = 250.0) -> Signal:
    """Read a signal file into a :class:`Signal`."""
    extension = os.path.splitext(path)[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{extension}'. Use {', '.join(SUPPORTED_EXTENSIONS)}.")

    separator = "," if extension == ".csv" else r"[\s,;]+"
    samples = pd.read_csv(path, sep=separator, engine="python", header=None, comment="#")
    samples = samples.apply(pd.to_numeric, errors="coerce")
    # Drop a header row (or any non-numeric rows) and fully empty columns
    samples = samples.dropna(how="all", axis=1).dropna(how="any", axis=0)
    if samples.empty:
        raise ValueError("The file does not contain numeric samples.")

    if samples.shape[1] >= 2:
        time = samples.iloc[:, 0].to_numpy(dtype=float)
        amplitude = samples.iloc[:, 1].to_numpy(dtype=float)
        if not np.all(np.diff(time) > 0):  # the first column is not a time axis
            amplitude = samples.iloc[:, 0].to_numpy(dtype=float)
            time = np.arange(len(amplitude)) / default_sampling_rate
    else:
        amplitude = samples.iloc[:, 0].to_numpy(dtype=float)
        time = np.arange(len(amplitude)) / default_sampling_rate

    name = os.path.splitext(os.path.basename(path))[0]
    return Signal(name=name, time=time - time[0], amplitude=amplitude, source=path)
