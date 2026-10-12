"""AudioAnalyzer: loudness, transients, silence and music beats (librosa)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import librosa
import numpy as np

from .ffmpeg import ffmpeg_bin

SR = 22050
HOP = 512


def decode_audio(path: Path, sr: int = SR, max_seconds: float | None = None) -> np.ndarray:
    """Decode any FFmpeg-readable audio to mono float32. Returns an empty array if there is none."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path), "-vn",
           "-ac", "1", "-ar", str(sr)]
    if max_seconds:
        cmd += ["-t", f"{max_seconds:.3f}"]
    cmd += ["-f", "f32le", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True, timeout=900)
    if proc.returncode != 0:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


@dataclass
class AudioFeatures:
    frame_rate: float  # feature frames per second
    rms_db: np.ndarray = field(default_factory=lambda: np.zeros(0))
    onset: np.ndarray = field(default_factory=lambda: np.zeros(0))  # onset strength (full band)
    hf_flux: np.ndarray = field(default_factory=lambda: np.zeros(0))  # spectral flux above ~2 kHz
    transient_times: list[float] = field(default_factory=list)
    silences: list[tuple[float, float]] = field(default_factory=list)
    duration: float = 0.0

    @property
    def empty(self) -> bool:
        return len(self.rms_db) == 0


@dataclass
class MusicAnalysis:
    duration: float
    bpm: float
    beats: list[float]
    downbeats: list[float]
    energy: list[float]  # mean energy per beat interval, 0..1
    suggested_offset: float
    loudness_db: float

    def as_dict(self) -> dict:
        return {
            "duration": round(self.duration, 3), "bpm": round(self.bpm, 2),
            "beats": [round(b, 4) for b in self.beats], "downbeats": [round(b, 4) for b in self.downbeats],
            "energy": [round(e, 3) for e in self.energy], "suggested_offset": round(self.suggested_offset, 3),
            "loudness_db": round(self.loudness_db, 2),
        }


class AudioAnalyzer:
    def __init__(self, silence_db: float = -45.0, min_silence: float = 1.0):
        self.silence_db = silence_db
        self.min_silence = min_silence

    def features(self, y: np.ndarray, sr: int = SR) -> AudioFeatures:
        fr = sr / HOP
        if y.size < sr // 4 or float(np.abs(y).max(initial=0)) < 1e-5:
            return AudioFeatures(frame_rate=fr, duration=y.size / sr)
        # Process in ~60 s chunks (aligned to the hop) so hour-long recordings don't need GBs of RAM.
        chunk = HOP * int(60 * sr / HOP)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        rms_parts, onset_parts, flux_parts = [], [], []
        prev_hf = None
        for start in range(0, y.size, chunk):
            seg = y[start:start + chunk]
            if seg.size < 2048:
                seg = np.pad(seg, (0, 2048 - seg.size))
            n_frames = int(np.ceil(min(chunk, y.size - start) / HOP))
            rms_parts.append(librosa.feature.rms(y=seg, frame_length=2048, hop_length=HOP)[0][:n_frames])
            onset_parts.append(librosa.onset.onset_strength(y=seg, sr=sr, hop_length=HOP)[:n_frames])
            hf = np.abs(librosa.stft(seg, n_fft=2048, hop_length=HOP))[freqs >= 2000][:, :n_frames]
            first = hf[:, :1] if prev_hf is None else prev_hf
            flux_parts.append(np.maximum(0.0, np.diff(hf, axis=1, prepend=first)).sum(axis=0))
            prev_hf = hf[:, -1:]
        rms_db = librosa.amplitude_to_db(np.concatenate(rms_parts), ref=1.0, top_db=None)
        onset = np.concatenate(onset_parts)
        flux = np.concatenate(flux_parts)
        flux = flux / (np.percentile(flux, 99) + 1e-9)
        peaks = librosa.util.peak_pick(flux, pre_max=3, post_max=3, pre_avg=10, post_avg=10,
                                       delta=0.25, wait=int(0.06 * fr))
        n = min(len(rms_db), len(onset), len(flux))
        feats = AudioFeatures(frame_rate=fr, rms_db=rms_db[:n], onset=onset[:n], hf_flux=flux[:n],
                              transient_times=[float(p / fr) for p in peaks if p < n], duration=y.size / sr)
        feats.silences = self.silences(feats)
        return feats

    def silences(self, f: AudioFeatures) -> list[tuple[float, float]]:
        quiet = f.rms_db < self.silence_db
        out: list[tuple[float, float]] = []
        start = None
        for i, q in enumerate(np.append(quiet, False)):
            if q and start is None:
                start = i
            elif not q and start is not None:
                a, b = start / f.frame_rate, i / f.frame_rate
                if b - a >= self.min_silence:
                    out.append((round(a, 3), round(b, 3)))
                start = None
        return out

    def analyze_music(self, path: Path) -> MusicAnalysis:
        y = decode_audio(path)
        duration = y.size / SR
        if y.size < SR or float(np.abs(y).max(initial=0)) < 1e-5:
            return MusicAnalysis(duration, 120.0, [], [], [], 0.0, -90.0)
        onset = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
        tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=SR, hop_length=HOP, units="time")
        bpm = float(np.atleast_1d(tempo)[0]) if np.size(tempo) else 120.0
        beats = [float(b) for b in np.atleast_1d(beats)]
        if len(beats) < 4:  # unreliable: fall back to a fixed grid
            bpm = bpm if 60 <= bpm <= 200 else 120.0
            beats = list(np.arange(0, duration, 60.0 / bpm))
        rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=SR, hop_length=HOP)
        edges = [*beats, duration]
        energy = []
        for a, b in zip(edges, edges[1:]):
            m = (times >= a) & (times < b)
            energy.append(float(rms[m].mean()) if m.any() else 0.0)
        emax = max(energy) if energy else 1.0
        energy = [e / emax if emax else 0.0 for e in energy]
        # Downbeats: the phase (0-3) whose beats carry the most onset strength.
        on_at = np.interp(beats, librosa.frames_to_time(np.arange(len(onset)), sr=SR, hop_length=HOP), onset)
        phase = int(np.argmax([on_at[p::4].sum() for p in range(4)])) if len(beats) >= 8 else 0
        downbeats = beats[phase::4]
        offset = self._suggest_offset(downbeats, beats, energy, duration)
        loud = float(20 * np.log10(np.sqrt(np.mean(y.astype(np.float64) ** 2)) + 1e-12))
        return MusicAnalysis(duration, bpm, beats, downbeats, energy, offset, loud)

    @staticmethod
    def _suggest_offset(downbeats: list[float], beats: list[float], energy: list[float], duration: float) -> float:
        """Start the montage on a downbeat just before the energy first gets high (the 'drop')."""
        if not energy or duration < 20:
            return 0.0
        hi = np.percentile(energy, 70)
        limit = duration * 0.5
        for i, e in enumerate(energy):
            if beats[i] > limit:
                break
            if e >= hi:
                t = beats[i]
                prior = [d for d in downbeats if d <= t]
                return float(prior[-1]) if prior else 0.0
        return float(downbeats[0]) if downbeats else 0.0
