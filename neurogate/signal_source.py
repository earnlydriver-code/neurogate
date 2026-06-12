"""Fuentes de señal de NeuroGate.

Contiene tres fuentes conmutables por configuración:

- ``SignalSource`` (v1): cerebro simulado en proceso, con firmas espectrales por
  intención. Cada "intención" domina una banda de frecuencia distinta para que el
  decoder pueda distinguirlas.
- ``BrainFlowSource`` (v2, Fase A): adquisición sobre BrainFlow; por defecto la
  placa sintética, pero hardware real cambiando una variable de entorno.
- ``DatasetSource`` (v2, Fase A): reproduce un dataset público local (EDF de
  PhysioNet) como si fuera streaming en vivo, a velocidad real.

El contrato v1 se preserva: ``get_chunk() -> np.ndarray`` 1-D. La riqueza
multicanal/metadatos se expone aparte (``get_chunk_2d``, ``sampling_rate``,
``channel_names``, timestamps).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np

# Intenciones que el cerebro simulado puede "pensar" (strings, no el Enum del
# decoder, para evitar import circular). Coinciden con Intent.value del decoder.
INTENTS = ("idle", "move_cursor", "type_text")

# Frecuencia representativa de cada banda EEG (Hz).
_BAND_HZ = {"theta": 6.0, "alpha": 10.0, "beta": 20.0}

# Firma espectral por intención: amplitud (microvoltios) de cada banda.
# - idle: alfa dominante (cerebro relajado).
# - move_cursor: beta dominante (actividad motora).
# - type_text: theta + beta (concentración + actividad).
_SIGNATURES = {
    "idle": {"theta": 5.0, "alpha": 25.0, "beta": 5.0},
    "move_cursor": {"theta": 5.0, "alpha": 8.0, "beta": 22.0},
    "type_text": {"theta": 18.0, "alpha": 8.0, "beta": 16.0},
}

_NOISE_UV = 5.0  # desviación del ruido gaussiano de fondo


def _synthesize(intent_label: str, n: int, sampling_rate: int,
                sample_offset: float, rng: np.random.Generator) -> np.ndarray:
    """Sintetiza n muestras para una intención, con offset de fase para continuidad."""
    if intent_label not in _SIGNATURES:
        raise ValueError(f"Intención desconocida: {intent_label}")
    t = (sample_offset + np.arange(n)) / sampling_rate
    signal = np.zeros(n)
    for band, freq in _BAND_HZ.items():
        signal += _SIGNATURES[intent_label][band] * np.sin(2 * np.pi * freq * t)
    signal += rng.normal(0.0, _NOISE_UV, n)
    return signal


class SignalSource:
    """Fuente de señal EEG simulada, entregada en bloques como un stream."""

    def __init__(self, sampling_rate: int = 250, chunk_size: int = 250,
                 seed: int | None = None) -> None:
        self.sampling_rate = sampling_rate
        self.chunk_size = chunk_size
        self._rng = np.random.default_rng(seed)
        self._sample_index = 0  # avanza para mantener fase continua entre bloques
        self._intent = "idle"   # "estado mental" actual del cerebro simulado

    def set_intent(self, intent_label: str) -> None:
        """Cambia la intención que el cerebro está 'pensando' (el decoder no la ve)."""
        if intent_label not in _SIGNATURES:
            raise ValueError(f"Intención desconocida: {intent_label}")
        self._intent = intent_label

    def get_chunk(self) -> np.ndarray:
        """Devuelve el siguiente bloque del stream (array 1-D de chunk_size muestras)."""
        chunk = _synthesize(self._intent, self.chunk_size, self.sampling_rate,
                            self._sample_index, self._rng)
        self._sample_index += self.chunk_size
        return chunk

    def sample(self, intent_label: str, n_samples: int | None = None) -> np.ndarray:
        """Bloque etiquetado independiente para entrenar el decoder (no toca el stream)."""
        n = n_samples or self.chunk_size
        offset = self._rng.uniform(0, 10_000)  # fase aleatoria -> variedad
        return _synthesize(intent_label, n, self.sampling_rate, offset, self._rng)


# Valor por defecto del board: SyntheticBoard (no requiere hardware).
# Cambiar a hardware real = exportar NEUROGATE_BOARD_ID con otro id de BrainFlow.
_DEFAULT_BOARD_ID = -1  # BoardIds.SYNTHETIC_BOARD

# Ruta por defecto al dataset EDF local (copia en el repo, PhysioNet EEGBCI).
_DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parent.parent
    / "eeg_data" / "MNE-eegbci-data" / "files" / "eegmmidb" / "1.0.0"
    / "S001" / "S001R04.edf"
)


class BrainFlowSource:
    """Fuente de señal sobre BrainFlow (placa sintética por defecto, hardware-ready).

    El id de placa se configura por la env var ``NEUROGATE_BOARD_ID``; conectar
    hardware real (OpenBCI, Muse, ...) es cambiar esa variable, sin tocar código.
    """

    def __init__(self, board_id: int | None = None, chunk_size: int = 250,
                 channel_index: int = 0) -> None:
        from brainflow.board_shim import (BoardShim, BoardIds,
                                          BrainFlowInputParams)

        if board_id is None:
            board_id = int(os.environ.get("NEUROGATE_BOARD_ID", _DEFAULT_BOARD_ID))
        self.board_id = board_id
        self.chunk_size = chunk_size
        self.channel_index = channel_index  # canal EEG 1-D representativo

        self.sampling_rate = BoardShim.get_sampling_rate(board_id)
        self.eeg_channels = BoardShim.get_eeg_channels(board_id)
        self.timestamp_channel = BoardShim.get_timestamp_channel(board_id)
        try:
            self.channel_names = BoardShim.get_eeg_names(board_id)
        except Exception:  # algunas placas no exponen nombres
            self.channel_names = [f"ch{i}" for i in range(len(self.eeg_channels))]

        params = BrainFlowInputParams()
        self._board = BoardShim(board_id, params)
        self._started = False
        self._chunk_seconds = chunk_size / self.sampling_rate

    def start(self) -> "BrainFlowSource":
        """Prepara la sesión y arranca el stream de la placa."""
        if not self._started:
            self._board.prepare_session()
            self._board.start_stream()
            self._started = True
        return self

    def _ensure_started(self) -> None:
        if not self._started:
            self.start()

    def get_chunk_2d(self) -> np.ndarray:
        """Siguiente bloque multicanal EEG, forma (n_canales, chunk_size)."""
        self._ensure_started()
        # Esperar a que la placa acumule el bloque completo (velocidad real). Se
        # reintenta brevemente porque el primer get tras arrancar puede quedar corto.
        deadline = time.time() + self._chunk_seconds + 1.0
        while True:
            if self._board.get_board_data_count() >= self.chunk_size:
                break
            if time.time() >= deadline:
                break
            time.sleep(self._chunk_seconds / 5)
        data = self._board.get_current_board_data(self.chunk_size)
        return data[self.eeg_channels, :]

    def get_chunk(self) -> np.ndarray:
        """Contrato v1: bloque 1-D de un canal EEG representativo."""
        return self.get_chunk_2d()[self.channel_index]

    def get_timestamps(self) -> np.ndarray:
        """Timestamps (segundos epoch) del último bloque leído de la placa."""
        self._ensure_started()
        data = self._board.get_current_board_data(self.chunk_size)
        return data[self.timestamp_channel, :]

    def close(self) -> None:
        """Detiene el stream y libera la sesión de BrainFlow."""
        if self._started:
            try:
                self._board.stop_stream()
            finally:
                self._board.release_session()
                self._started = False

    def __enter__(self) -> "BrainFlowSource":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()


class DatasetSource:
    """Reproduce un dataset público local (EDF de PhysioNet) como streaming en vivo.

    Misma interfaz que las demás fuentes. La ruta se configura por la env var
    ``NEUROGATE_DATASET_PATH``; por defecto apunta a la copia local del repo.
    """

    def __init__(self, dataset_path: str | os.PathLike | None = None,
                 chunk_size: int = 250, channel_index: int = 0,
                 real_time: bool = False) -> None:
        import mne

        mne.set_log_level("WARNING")  # silencia el ruido de logging de MNE

        if dataset_path is None:
            dataset_path = os.environ.get("NEUROGATE_DATASET_PATH",
                                          str(_DEFAULT_DATASET_PATH))
        self.dataset_path = Path(dataset_path)
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset EDF no encontrado: {self.dataset_path}")

        self.chunk_size = chunk_size
        self.channel_index = channel_index
        self.real_time = real_time  # si True, espera el tiempo real de cada bloque

        raw = mne.io.read_raw_edf(self.dataset_path, preload=True)
        self.sampling_rate = int(round(raw.info["sfreq"]))
        self.channel_names = list(raw.ch_names)
        self.eeg_channels = list(range(len(self.channel_names)))
        self._data = raw.get_data()  # (n_canales, n_muestras)
        self._times = raw.times      # segundos desde el inicio
        self._cursor = 0
        self._chunk_seconds = chunk_size / self.sampling_rate

    def get_chunk_2d(self) -> np.ndarray:
        """Siguiente bloque multicanal, forma (n_canales, chunk_size). Reinicia al final."""
        n_total = self._data.shape[1]
        if self._cursor + self.chunk_size > n_total:
            self._cursor = 0  # bucle: reproduce el dataset en loop
        start = self._cursor
        end = start + self.chunk_size
        self._cursor = end
        if self.real_time:
            time.sleep(self._chunk_seconds)
        return self._data[:, start:end]

    def get_chunk(self) -> np.ndarray:
        """Contrato v1: bloque 1-D de un canal EEG representativo."""
        return self.get_chunk_2d()[self.channel_index]

    def get_timestamps(self) -> np.ndarray:
        """Timestamps (segundos desde el inicio del registro) del último bloque."""
        end = self._cursor
        start = max(0, end - self.chunk_size)
        return self._times[start:end]

    def close(self) -> None:
        """No mantiene recursos abiertos; presente por simetría de interfaz."""
        pass

    def __enter__(self) -> "DatasetSource":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def make_source(kind: str | None = None, **kwargs):
    """Devuelve la fuente de señal según ``kind`` o la env var NEUROGATE_SIGNAL_SOURCE.

    Valores: ``synthetic`` (default, BrainFlowSource SyntheticBoard),
    ``dataset`` (DatasetSource), ``simulated`` (SignalSource de la v1).
    """
    if kind is None:
        kind = os.environ.get("NEUROGATE_SIGNAL_SOURCE", "synthetic")
    kind = kind.lower()
    if kind == "synthetic":
        return BrainFlowSource(**kwargs)
    if kind == "dataset":
        return DatasetSource(**kwargs)
    if kind == "simulated":
        return SignalSource(**kwargs)
    raise ValueError(f"Fuente de señal desconocida: {kind!r}")


def _demo_v1() -> None:
    """v1: grafica ~2 s de señal por cada intención y guarda PNG + resumen (Paso 2)."""
    from pathlib import Path

    import matplotlib
    matplotlib.use("Agg")  # backend sin ventana, para guardar a archivo
    import matplotlib.pyplot as plt

    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)

    src = SignalSource(seed=42)
    fig, axes = plt.subplots(len(INTENTS), 1, figsize=(10, 7), sharex=True)
    lines = []
    for ax, intent in zip(axes, INTENTS):
        chunk = src.sample(intent, n_samples=500)  # 2 s a 250 Hz
        t = np.arange(chunk.size) / src.sampling_rate
        ax.plot(t, chunk, linewidth=0.8)
        ax.set_title(f"Intención: {intent}", loc="left", fontsize=10)
        ax.set_ylabel("µV")
        lines.append(f"{intent:12s} -> media={chunk.mean():6.2f}  "
                     f"std={chunk.std():6.2f}  pico={np.abs(chunk).max():6.2f}")
    axes[-1].set_xlabel("tiempo (s)")
    fig.suptitle("NeuroGate · Señal EEG simulada por intención (Paso 2)")
    fig.tight_layout()
    png = demos / "step2_signal.png"
    fig.savefig(png, dpi=110)

    report = "Paso 2 — signal_source\n" + "=" * 40 + "\n" + "\n".join(lines) + "\n"
    (demos / "step2_signal.txt").write_text(report, encoding="utf-8")
    print(report)
    print(f"Gráfica guardada en {png}")


def _demo() -> None:
    """Fase A: grafica BrainFlow (synthetic) vs dataset EDF y guarda artefactos nuevos."""
    import matplotlib
    matplotlib.use("Agg")  # backend sin ventana, para guardar a archivo
    import matplotlib.pyplot as plt

    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)

    lines = ["Fase A — signal_source v2 (BrainFlow + DatasetSource)",
             "=" * 52]

    # Fuente 1: BrainFlow Synthetic Board (no requiere hardware).
    with BrainFlowSource(chunk_size=250) as bf:
        bf_chunk = bf.get_chunk()
        bf_2d = bf.get_chunk_2d()
        bf_rate = bf.sampling_rate
        bf_names = bf.channel_names
    lines.append(
        f"BrainFlow (SyntheticBoard)  sr={bf_rate} Hz  canales={len(bf_names)}  "
        f"chunk1D={bf_chunk.shape}  chunk2D={bf_2d.shape}")

    # Fuente 2: dataset EDF local de PhysioNet.
    with DatasetSource(chunk_size=250) as ds:
        ds_chunk = ds.get_chunk()
        ds_2d = ds.get_chunk_2d()
        ds_rate = ds.sampling_rate
        ds_names = ds.channel_names
    lines.append(
        f"Dataset EDF ({Path(ds.dataset_path).name})  sr={ds_rate} Hz  "
        f"canales={len(ds_names)}  chunk1D={ds_chunk.shape}  chunk2D={ds_2d.shape}")

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=False)
    t_bf = np.arange(bf_chunk.size) / bf_rate
    axes[0].plot(t_bf, bf_chunk, linewidth=0.8, color="tab:blue")
    axes[0].set_title(f"BrainFlow SyntheticBoard · canal {bf_names[0]} ({bf_rate} Hz)",
                      loc="left", fontsize=10)
    axes[0].set_ylabel("µV (escala placa)")

    t_ds = np.arange(ds_chunk.size) / ds_rate
    axes[1].plot(t_ds, ds_chunk * 1e6, linewidth=0.8, color="tab:green")
    axes[1].set_title(f"Dataset EDF PhysioNet · canal {ds_names[0]} ({ds_rate} Hz)",
                      loc="left", fontsize=10)
    axes[1].set_ylabel("µV")
    axes[1].set_xlabel("tiempo (s)")

    fig.suptitle("NeuroGate v2 · Fase A: dos fuentes conmutables por configuración")
    fig.tight_layout()
    png = demos / "phaseA_sources.png"
    fig.savefig(png, dpi=110)

    lines.append("")
    lines.append("Conmutación por entorno:")
    lines.append("  NEUROGATE_SIGNAL_SOURCE = synthetic | dataset | simulated")
    lines.append("  NEUROGATE_BOARD_ID      = id de placa BrainFlow (default -1, synthetic)")
    lines.append("  NEUROGATE_DATASET_PATH  = ruta a un EDF (default: copia local del repo)")

    report = "\n".join(lines) + "\n"
    (demos / "phaseA_sources.txt").write_text(report, encoding="utf-8")
    print(report)
    print(f"Gráfica guardada en {png}")


if __name__ == "__main__":
    _demo()
