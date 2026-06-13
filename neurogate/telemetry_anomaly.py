"""Detección de anomalías sobre telemetría real del gateway (Fase D).

Mismo Isolation Forest de la v1, pero las features ya no son una solicitud
abstracta: son **telemetría real del gateway** por app. Por cada request se
observan, en una ventana deslizante por app:

- tasa por ventana (peticiones en los últimos ``rate_window_seconds``, en rpm),
- diversidad de scopes vistos,
- hora del día,
- tamaño del payload,
- ratio de errores 4xx,
- novedad del endpoint/scope (¿pidió algo que nunca antes pidió?).

Fase de *baseline learning* configurable: durante los primeros N requests por app
solo aprende; luego pasa a modo vigilancia. Ante una anomalía marca la app para
cuarentena (el servicio aplica el bloqueo temporal + alerta + auditoría).

**Afinado (robustez):** la detección de flood se basa en una **ventana deslizante**
(cuántas peticiones caen en los últimos N segundos), no en el intervalo desde la
última petición. Así un par de peticiones legítimas muy seguidas no se confunde
con un flood; solo una ráfaga *sostenida* dispara la cuarentena. El Isolation
Forest, que se alimenta de esa tasa por ventana, deja también de reaccionar a un
único intervalo corto.

Construye AL LADO de ``anomaly.py`` (v1 intacta); el servicio v2 usa esta.
"""

from __future__ import annotations

import statistics
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
    recent_ts: deque = field(default_factory=lambda: deque(maxlen=512))  # ventana de tasa
    recent_errors: deque = field(default_factory=lambda: deque(maxlen=20))
    observed: int = 0  # requests vistos (para la fase de baseline)


class TelemetryAnomalyDetector:
    """Isolation Forest sobre telemetría real, con baseline learning por app.

    La regla de flood mira una **ventana deslizante**: cuántas peticiones hizo la
    app en los últimos ``rate_window_seconds``. Se marca flood cuando esa cuenta
    supera a la vez (a) un mínimo de ráfaga (``min_flood_burst``) y (b) la tasa
    típica del baseline multiplicada por ``rate_spike_factor``.
    """

    def __init__(self, *, baseline_requests: int = 30,
                 contamination: float = 0.05, seed: int = 0,
                 rate_spike_factor: float = 10.0,
                 rate_window_seconds: float = 1.0,
                 min_flood_burst: int = 5) -> None:
        # baseline_requests: cuántos requests por app aprende antes de vigilar.
        self._baseline_requests = baseline_requests
        self._model = IsolationForest(contamination=contamination, random_state=seed)
        self._profiles: dict[str, _AppProfile] = {}
        self._baseline_features: list[list[float]] = []
        # rate_spike_factor: una tasa por ventana que supera ×factor la típica del
        # baseline se marca como flood (sin depender del iForest).
        self._rate_spike_factor = rate_spike_factor
        # rate_window_seconds: ventana deslizante para contar la tasa de peticiones.
        self._rate_window = max(1e-3, rate_window_seconds)
        # min_flood_burst: mínimo de peticiones en la ventana para considerar flood
        # (evita falsos positivos con 2-3 peticiones legítimas muy seguidas).
        self._min_flood_burst = max(2, min_flood_burst)
        self._baseline_rate = 60.0  # rpm típico por ventana del baseline (mediana)
        self._trained = False

    @property
    def is_trained(self) -> bool:
        return self._trained

    def warm_up(self, client_id: str, scopes: set[str]) -> None:
        """Siembra los scopes que una app puede pedir (no caen en la regla de novedad)."""
        prof = self._profiles.setdefault(client_id, _AppProfile())
        prof.seen_scopes.update(scopes)

    def reset_app(self, client_id: str) -> None:
        """Olvida la actividad reciente de una app (tras liberarla de cuarentena).

        Sin esto, una app recién liberada se re-marcaría por la ráfaga ya pasada que
        sigue en su ventana; el operador espera que liberar surta efecto al instante.
        """
        prof = self._profiles.get(client_id)
        if prof is not None:
            prof.recent_ts.clear()
            prof.recent_errors.clear()

    def clear_timing(self) -> None:
        """Olvida los timestamps del baseline tras entrenar.

        El baseline puede aprenderse con timestamps simulados; sin esto, la
        ventana deslizante arrastraría ese reloj y la primera petición real podría
        contar mal. Mismo criterio que la v1 (``AnomalyDetector.clear_timing``).
        """
        for prof in self._profiles.values():
            prof.recent_ts.clear()

    def _profile(self, client_id: str) -> _AppProfile:
        return self._profiles.setdefault(client_id, _AppProfile())

    def _window_count(self, prof: _AppProfile, now: float) -> int:
        """Peticiones de la app en la ventana de tasa, incluyendo la actual."""
        w = self._rate_window
        recent = sum(1 for ts in prof.recent_ts if 0.0 <= now - ts <= w)
        return recent + 1  # +1 por la petición que se está observando

    def _features(self, rec: TelemetryRecord, prof: _AppProfile,
                  count: int) -> list[float]:
        """Deriva el vector de features de telemetría para un request."""
        windowed_rpm = count * 60.0 / self._rate_window
        hour = float(time.localtime(rec.timestamp).tm_hour)
        n_scopes = float(len(prof.seen_scopes) + 1)  # diversidad de scopes
        err_ratio = (sum(prof.recent_errors) / len(prof.recent_errors)
                     if prof.recent_errors else 0.0)
        return [windowed_rpm, hour, n_scopes, float(rec.payload_size), err_ratio]

    def observe(self, rec: TelemetryRecord, *, learning: bool | None = None) -> TelemetryResult:
        """Observa un request y dictamina si es anómalo.

        Durante el baseline (o si ``learning=True``) solo aprende y devuelve no
        anómalo. En vigilancia aplica: regla de novedad de scope, flood por
        ventana deslizante, y el Isolation Forest sobre las features continuas.
        """
        prof = self._profile(rec.client_id)
        count = self._window_count(prof, rec.timestamp)
        feats = self._features(rec, prof, count)

        in_baseline = prof.observed < self._baseline_requests
        is_learning = learning if learning is not None else in_baseline

        result = TelemetryResult(False, 0.0, "comportamiento normal")
        if not is_learning:
            result = self._judge(rec, prof, feats, count)
        elif self._trained is False:
            # Acumula features de baseline para entrenar al cerrar la fase.
            self._baseline_features.append(feats)

        # Actualiza el perfil DESPUÉS de juzgar (la novedad mira el pasado).
        self._update_profile(rec, prof)
        return result

    def _judge(self, rec: TelemetryRecord, prof: _AppProfile,
               feats: list[float], count: int) -> TelemetryResult:
        """Aplica las reglas de vigilancia sobre un request ya fuera de baseline."""
        # 1. Novedad de scope: un scope que esta app jamás pidió antes.
        if rec.scope not in prof.seen_scopes:
            return TelemetryResult(True, -1.0,
                                   f"scope nunca usado por esta app: {rec.scope}")
        windowed_rpm = feats[0]
        # 2. Flood sostenido: muchas peticiones en la ventana Y muy por encima de
        # la tasa típica. Las dos condiciones evitan marcar una ráfaga corta legítima.
        if (count >= self._min_flood_burst
                and windowed_rpm > self._baseline_rate * self._rate_spike_factor):
            return TelemetryResult(
                True, -1.0,
                f"flood: {count} peticiones en {self._rate_window:.0f}s "
                f"(~{windowed_rpm:.0f} rpm, típico ~{self._baseline_rate:.0f})")
        # 3. Isolation Forest sobre las features continuas. Se consulta solo si ya
        # hay una ráfaga mínima: así nunca marca 1-2 peticiones normales, pero
        # vigila patrones sostenidos raros (tamaño de payload, errores, scopes).
        if self._trained and count >= self._min_flood_burst:
            is_anom = self._model.predict([feats])[0] == -1
            raw = float(self._model.decision_function([feats])[0])
            if is_anom:
                return TelemetryResult(
                    True, raw, f"patrón de telemetría anómalo (~{windowed_rpm:.0f} rpm)")
        return TelemetryResult(False, 0.0, "comportamiento normal")

    def _update_profile(self, rec: TelemetryRecord, prof: _AppProfile) -> None:
        """Actualiza historial de la app tras observar un request."""
        prof.observed += 1
        prof.seen_scopes.add(rec.scope)
        prof.recent_ts.append(rec.timestamp)
        prof.recent_errors.append(1 if rec.is_error_4xx else 0)

    def finalize_baseline(self) -> None:
        """Cierra la fase de baseline: entrena el Isolation Forest y la tasa típica.

        Llamar cuando se ha acumulado suficiente telemetría normal. A partir de
        aquí el detector está en modo vigilancia con el iForest activo.
        """
        if not self._baseline_features:
            raise RuntimeError("no hay telemetría de baseline para entrenar")
        self._model.fit(self._baseline_features)
        self._baseline_rate = max(1.0, statistics.median(f[0] for f in self._baseline_features))
        self._trained = True


def _demo() -> None:
    """Aprende un baseline normal y detecta un flood sostenido y un scope nunca usado."""
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
    det.clear_timing()

    lines = [f"baseline aprendido (tasa típica ~{det._baseline_rate:.0f} rpm por ventana)"]

    # Caso normal.
    t += 1.0
    r = det.observe(TelemetryRecord("cursor_app", "read:intent", t, payload_size=16))
    lines.append(f"[{'ALERTA' if r.is_anomalous else 'OK'}] request normal           -> {r.reason}")

    # Ráfaga corta legítima (3 peticiones): NO debe ser flood.
    short = 0
    for _ in range(3):
        t += 0.02
        short += det.observe(TelemetryRecord("cursor_app", "read:intent", t, payload_size=16)).is_anomalous
    lines.append(f"[{'ALERTA' if short else 'OK'}] ráfaga corta (3 peticiones) -> "
                 f"{short}/3 marcadas (esperado 0)")

    # Flood sostenido: 40 peticiones a ~50/s.
    flagged = 0
    for _ in range(40):
        t += 0.02  # ~3000 rpm vs ~60 típico
        flagged += det.observe(TelemetryRecord("cursor_app", "read:intent", t, payload_size=16)).is_anomalous
    lines.append(f"[{'ALERTA' if flagged else 'OK'}] flood sostenido (40 peticiones) -> "
                 f"{flagged}/40 marcadas anómalas")

    # Scope nunca usado.
    t += 5.0
    r = det.observe(TelemetryRecord("cursor_app", "read:raw_signal", t, payload_size=4096))
    lines.append(f"[{'ALERTA' if r.is_anomalous else 'OK'}] scope nunca usado          -> {r.reason}")

    report = "Fase D — telemetry_anomaly (Isolation Forest sobre telemetría real)\n" + \
             "=" * 60 + "\n" + "\n".join(lines) + "\n"
    (demos / "phaseD_telemetry.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    _demo()
