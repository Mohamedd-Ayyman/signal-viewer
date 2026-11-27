"""Generate the sample recordings: a normal and an abnormal file for ECG, EMG and EEG.

python samples/generate_samples.py  ->  samples/data/*.csv  (columns: time, amplitude)
The generated files are committed in samples/data so the app works straight after cloning.
"""
import os

import numpy as np

OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), "data")
random_generator = np.random.default_rng(42)

# Gaussian waves that make up one heartbeat: (amplitude, offset from the R peak in s, width in s)
P_WAVE, Q_WAVE, R_WAVE, S_WAVE, T_WAVE = (0.12, -0.20, 0.025), (-0.12, -0.03, 0.01), (1.0, 0.0, 0.012), \
    (-0.25, 0.04, 0.012), (0.3, 0.25, 0.05)


def ecg(duration_s=20, sampling_rate=360, heart_rate_bpm=72, arrhythmia=False):
    time = np.arange(0, duration_s, 1 / sampling_rate)
    voltage = np.zeros_like(time)
    beat_time, normal_interval = 0.3, 60 / heart_rate_bpm
    while beat_time < duration_s:
        is_premature = arrhythmia and random_generator.random() < 0.2
        interval = normal_interval * (random_generator.uniform(0.55, 0.75) if is_premature
                                      else random_generator.uniform(0.97, 1.03))
        is_wide_beat = arrhythmia and interval < normal_interval * 0.8     # premature, wide complex (PVC-like)
        waves = [P_WAVE, Q_WAVE, (1.6, 0.0, 0.03) if is_wide_beat else R_WAVE, S_WAVE,
                 (-0.35, 0.25, 0.05) if is_wide_beat else T_WAVE]
        for wave_amplitude, wave_offset, wave_width in waves:
            voltage += wave_amplitude * np.exp(-((time - beat_time - wave_offset) ** 2) / (2 * wave_width ** 2))
        beat_time += interval
    baseline_wander = 0.05 * np.sin(2 * np.pi * 0.3 * time)
    return time, voltage + 0.03 * random_generator.standard_normal(len(time)) + baseline_wander


def emg(duration_s=10, sampling_rate=1000, myopathy=False):
    time = np.arange(0, duration_s, 1 / sampling_rate)
    contraction_envelope = (np.sin(2 * np.pi * 0.25 * time) > 0).astype(float) * 0.9 + 0.1
    if myopathy:  # short, low-amplitude, polyphasic potentials
        activity = random_generator.standard_normal(len(time)) * 0.35 * contraction_envelope
        polyphasic_spikes = np.sign(np.sin(2 * np.pi * 120 * time)) * (random_generator.random(len(time)) > 0.7)
        activity += 0.25 * polyphasic_spikes * contraction_envelope
    else:
        activity = random_generator.standard_normal(len(time)) * contraction_envelope
    return time, activity


def eeg(duration_s=20, sampling_rate=256, seizure=False):
    time = np.arange(0, duration_s, 1 / sampling_rate)
    background = (20 * np.sin(2 * np.pi * 10 * time) + 8 * np.sin(2 * np.pi * 6 * time + 1)
                  + 6 * random_generator.standard_normal(len(time)))
    if seizure:  # rhythmic 3 Hz spike-and-wave discharge in the middle third
        seizure_period = (time > duration_s / 3) & (time < 2 * duration_s / 3)
        spike_and_wave = 80 * np.sin(2 * np.pi * 3 * time) ** 15 - 40 * np.sin(2 * np.pi * 3 * time + np.pi / 2)
        background = np.where(seizure_period, background + spike_and_wave, background)
    return time, background


def save(file_name, time, amplitude):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    np.savetxt(os.path.join(OUTPUT_FOLDER, f"{file_name}.csv"), np.column_stack([time, amplitude]), delimiter=",",
               header="time,amplitude", comments="", fmt="%.5f")
    print("wrote", file_name)


if __name__ == "__main__":
    save("ecg_normal", *ecg())
    save("ecg_arrhythmia", *ecg(arrhythmia=True))
    save("emg_healthy", *emg())
    save("emg_myopathy", *emg(myopathy=True))
    save("eeg_normal", *eeg())
    save("eeg_seizure", *eeg(seizure=True))
