"""Generate synthetic sample recordings (normal and abnormal) for three modalities.

python samples/generate_samples.py  ->  samples/data/*.csv  (columns: time, amplitude)
"""
import os

import numpy as np

OUT = os.path.join(os.path.dirname(__file__), "data")
rng = np.random.default_rng(42)


def ecg(duration=20, fs=360, hr=72, arrhythmia=False):
    t = np.arange(0, duration, 1 / fs)
    sig = np.zeros_like(t)
    beat_t, rr = 0.3, 60 / hr
    while beat_t < duration:
        interval = rr * (rng.uniform(0.55, 0.75) if arrhythmia and rng.random() < 0.2 else rng.uniform(0.97, 1.03))
        wide = arrhythmia and interval < rr * 0.8          # premature, wide-complex beat (PVC-like)
        for amp, center, width in ((0.12, -0.20, 0.025), (-0.12, -0.03, 0.01),
                                   (1.6 if wide else 1.0, 0.0, 0.03 if wide else 0.012),
                                   (-0.25, 0.04, 0.012), (0.3 if not wide else -0.35, 0.25, 0.05)):
            sig += amp * np.exp(-((t - beat_t - center) ** 2) / (2 * width ** 2))
        beat_t += interval
    return t, sig + 0.03 * rng.standard_normal(len(t)) + 0.05 * np.sin(2 * np.pi * 0.3 * t)


def emg(duration=10, fs=1000, myopathy=False):
    t = np.arange(0, duration, 1 / fs)
    envelope = (np.sin(2 * np.pi * 0.25 * t) > 0).astype(float) * 0.9 + 0.1
    if myopathy:  # short, low-amplitude, polyphasic potentials
        burst = rng.standard_normal(len(t)) * 0.35 * envelope
        burst += 0.25 * np.sign(np.sin(2 * np.pi * 120 * t)) * envelope * (rng.random(len(t)) > 0.7)
    else:
        burst = rng.standard_normal(len(t)) * envelope
    return t, burst


def eeg(duration=20, fs=256, seizure=False):
    t = np.arange(0, duration, 1 / fs)
    sig = 20 * np.sin(2 * np.pi * 10 * t) + 8 * np.sin(2 * np.pi * 6 * t + 1) + 6 * rng.standard_normal(len(t))
    if seizure:  # rhythmic 3 Hz spike-and-wave discharge in the middle third
        mask = (t > duration / 3) & (t < 2 * duration / 3)
        sw = 80 * np.sin(2 * np.pi * 3 * t) ** 15 - 40 * np.sin(2 * np.pi * 3 * t + np.pi / 2)
        sig = np.where(mask, sig + sw, sig)
    return t, sig


def save(name, t, a):
    os.makedirs(OUT, exist_ok=True)
    np.savetxt(os.path.join(OUT, f"{name}.csv"), np.column_stack([t, a]), delimiter=",",
               header="time,amplitude", comments="", fmt="%.5f")
    print("wrote", name)


if __name__ == "__main__":
    save("ecg_normal", *ecg())
    save("ecg_arrhythmia", *ecg(arrhythmia=True))
    save("emg_healthy", *emg())
    save("emg_myopathy", *emg(myopathy=True))
    save("eeg_normal", *eeg())
    save("eeg_seizure", *eeg(seizure=True))
