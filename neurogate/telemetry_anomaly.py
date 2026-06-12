"""Detección de anomalías sobre telemetría real del gateway (Fase D).

Mismo Isolation Forest de la v1, pero las features ya no son una solicitud
abstracta: son **telemetría real del gateway** por app. Por cada request se
observan, en una ventana deslizante por app:

- requests por minuto (tasa instantánea desde el último request),
- distribución de scopes (entropía / nº de scopes distintos vistos),
- hora del día,
- tamaño del payload,
- ratio de errores 4xx,
- novedad del endpoint/scope (¿pidió algo que nunca antes pidió?).

Fase de *baseline learning* configurable: durante los primeros N requests por app
solo aprende; luego pasa a modo vigilancia. Ante una anomalía marca la app para
cuarentena (el servicio aplica el bloqueo temporal + alerta + auditoría).

Construye AL LADO de ``anomaly.py`` (v1 intacta); el servicio v2 usa esta.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from sklearn.ensemble import IsolationForest


@dataclass(frozen=True)
class TelemetryRecord:
    """Telemetría de un request observado por el gateway."""

    client_id: str
    scope: str
    timestamp: float
    payload_size: int = 0
    is_error_4xx: bool = False


@dataclass(frozen=True)
class TelemetryResult:
    """Veredicto del detector sobre un request."""

    is_anomalous: bool
    score: float
    reason: str


@dataclass
class _AppProfile:
    """Estado por app: historial reciente para derivar features y novedad."""

    seen_scopes: set[str] = field(default_factory=set)
    last_ts: float | None = None
    recent_ts: deque = field(default_factory=lambda: deque(maxlen=60))  # para rpm
    recent_errors: deque = field(default_factory=lambda: deque(maxlen=20))
    observed: int = 0  # requests vistos (para la fase de baseline)


class TelemetryAnomalyDetector:
    """Isolation Forest sobre telemetría real, con baseline learning por app."""

    def __init__(self, *, baseline_requests: int = 30,
                 contamination: float = 0.05, seed: int = 0,
                 rate_spike_factor: float = 10.0) -> None:
        # baseline_requests: cuántos requests por app aprende antes de vigilar.
        self._baseline_requests = baseline_requests
        self._model = IsolationForest(contamination=contamination, random_state=seed)
        self._profiles: dict[str, _AppProfile] = {}
        self._baseline_features: list[list[float]] = []
        # rate_spike_factor: una tasa que supera ×factor la típica del baseline
        # se marca como anomalía dura (un flood no necesita que el iForest "lo vea").
        self._rate_spike_factor = rate_spike_factor
        self._baseline_rate = 1.0  # rpm típico del baseline (mediana)
        self._trained = False

    @property
    def is_trained(self) -> bool:
        return self._trained

    def warm_up(self, client_id: str, scopes: set[str]) -> None:
        """Siembra los scopes que una app puede pedir (no caen en la regla de novedad)."""
        prof = self._profiles.setdefault(client_id, _AppProfile())
        prof.seen_scopes.update(scopes)

    def clear_timing(self) -> None:
        """Olvida los timestamps del baseline tras entrenar.

        El baseline puede aprenderse con timestamps simulados; sin esto, la
        primera petición real heredaría un intervalo enorme y se marcaría como
        anómala. Mismo criterio que la v1 (``AnomalyDetector.clear_timing``).
        """
        for prof in self._profiles.values():
            prof.last_ts = None
            prof.recent_ts.clear()

    def _profile(self, client_id: str) -> _AppProfile:
        return self._profiles.setdefault(client_id, _AppProfile())

    def _features(self, rec: TelemetryRecord, prof: _AppProfile) -> list[float]:
        """Deriva el vector de features de telemetría para un request."""
        # requests por minuto: 60 / intervalo desde el último request de la app.
        if prof.last_ts is not None:
            interval = max(1e-3, rec.timestamp - prof.last_ts)
            rpm = 60.0 / interval
        else:
            # Sin historial (primera petición, o tras clear_timing): asumimos la
            # tasa típica del baseline para no marcar una petición legítima.
            rpm = self._baseline_rate
        hour = float(time.localtime(rec.timestamp).tm_hour)
        n_scopes = float(len(prof.seen_scopes) + 1)  # diversidad de scopes
        err_ratio = (sum(prof.recent_errors) / len(prof.recent_errors)
                     if prof.recent_errors else 0.0)
        return [rpm, hour, n_scopes, float(rec.payload_size), err_ratio]

    def observe(self, rec: TelemetryRecord, *, learning: bool | None = None) -> TelemetryResult:
        """Observa un request y dictamina si es anómalo.

        Durante el baseline (o si ``learning=True``) solo aprende y devuelve no
        anómalo. En vigilancia aplica: regla de novedad de scope, pico de tasa, y
        el Isolation Forest sobre las features continuas.
        """
        prof = self._profile(rec.client_id)
        feats = self._features(rec, prof)

        in_baseline = prof.observed < self._baseline_requests
        is_learning = learning if learning is not None else in_baseline

        result = TelemetryResult(False, 0.0, "comportamiento normal")
        if not is_learning:
            result = self._judge(rec, prof, feats)
        elif self._trained is False:
            # Acumula features de baseline para entrenar al cerrar la fase.
            self._baseline_features.append(feats)

        # Actualiza el perfil DESPUÉS de juzgar (la novedad mira el pasado).
        self._update_profile(rec, prof, feats)
        return result

    def _judge(self, rec: TelemetryRecord, prof: _AppProfile,
               feats: list[float]) -> TelemetryResult:
        """Aplica las reglas de vigilancia sobre un request ya fuera de baseline."""
        # 1. Novedad de scope: un scope que esta app jamás pidió antes.
        if rec.scope not in prof.seen_scopes:
            return TelemetryResult(True, -1.0,
                                   f"scope nunca usado por esta app: {rec.scope}")
        # 2. Pico de tasa: rpm que dispara muy por encima de lo típico (flood).
        rpm = feats[0]
        if rpm > self._baseline_rate * self._rate_spike_factor:
            return TelemetryResult(True, -1.0,
                                   f"tasa anómala: {rpm:.0f} rpm (típico ~{self._baseline_rate:.0f})")
        # 3. Isolation Forest sobre las features continuas (si está entrenado).
        if self._trained:
            is_anom = self._model.predict([feats])[0] == -1
            raw = float(self._model.decision_function([feats])[0])
            if is_anom:
                return TelemetryResult(True, raw, f"patrón de telemetría anómalo (rpm={rpm:.0f})")
        return TelemetryResult(False, 0.0, "comportamiento normal")

    def _update_profile(self, rec: TelemetryRecord, prof: _AppProfile,
                        feats: list[float]) -> None:
        """Actualiza historial de la app tras observar un request."""
        prof.observed += 1
        prof.seen_scopes.add(rec.scope)
        prof.last_ts = rec.timestamp
        prof.recent_ts.append(rec.timestamp)
        prof.recent_errors.append(1 if rec.is_error_4xx else 0)

    def finalize_baseline(self) -> None:
        """Cierra la fase de baseline: entrena el Isolation Forest y la tasa típica.

        Llamar cuando se ha acumulado suficiente telemetría normal. A partir de
        aquí el detector está en modo vigilancia con el iForest activo.
        """
        if not self._baseline_features:
            raise RuntimeError("no hay telemetría de baseline para entrenar")
        import statistics

        self._model.fit(self._baseline_features)
        self._baseline_rate = max(1.0, statistics.median(f[0] for f in self._baseline_features))
        self._trained = True


def _demo() -> None:
    """Aprende un baseline normal y detecta un flood ×20 y un scope nunca usado."""
    from pathlib import Path

    demos = Path(__file__).resolve().parent.parent / "demos"
    demos.mkdir(exist_ok=True)

    det = TelemetryAnomalyDetector(baseline_requests=40, rate_spike_factor=10.0)
    det.warm_up("cursor_app", {"read:intent"})

    # Baseline: ~1 request/s, siempre read:intent.
    t = 1_000_000.0
    for _ in range(40):
        t += 1.0
        det.observe(TelemetryRecord("cursor_app", "read:intent", t, payload_size=16))
    det.finalize_baseline()

    lines = [f"baseline aprendido (tasa típica ~{det._baseline_rate:.0f} rpm)"]

    # Caso normal.
    t += 1.0
    r = det.observe(TelemetryRecord("cursor_app", "read:intent", t, payload_size=16))
    lines.append(f"[{'ALERTA' if r.is_anomalous else 'OK'}] request normal      -> {r.reason}")

    # Flood: ráfaga ×20 la tasa.
    flagged = 0
    for _ in range(10):
        t += 0.05  # 1200 rpm vs ~60 típico
        r = det.observe(TelemetryRecord("cursor_app", "read:intent", t, payload_size=16))
        flagged += r.is_anomalous
    lines.append(f"[{'ALERTA' if flagged else 'OK'}] flood ×20 tasa       -> {flagged}/10 marcados anómalos")

    # Scope nunca usado.
    t += 5.0
    r = det.observe(TelemetryRecord("cursor_app", "read:raw_signal", t, payload_size=4096))
    lines.append(f"[{'ALERTA' if r.is_anomalous else 'OK'}] scope nunca usado    -> {r.reason}")

    report = "Fase D — telemetry_anomaly (Isolation Forest sobre telemetría real)\n" + \
             "=" * 60 + "\n" + "\n".join(lines) + "\n"
    (demos / "phaseD_telemetry.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    _demo()
