"""Entrenamiento offline del decoder real (v2, Fase B).

Carga BCI Competition IV 2a (BNCI2014_001) desde la copia local en disco,
construye un pipeline MNE + CSP + LDA, hace validación cruzada por sujeto,
imprime la accuracy honesta y serializa el modelo entrenado a
``models/mi_decoder.joblib``.

Camino de carga: lectura directa de los ``.mat`` con ``scipy.io.loadmat``
(fallback robusto y offline, sin depender de que MOABB resuelva rutas de caché
ni intente descargar). Cada ``.mat`` trae una struct ``data`` con runs; cada run
con motor imagery tiene ``X`` (muestras×canales), ``y`` (etiqueta por trial),
``trial`` (muestra de inicio de cada trial), ``fs``=250 Hz y ``classes``.

Uso:
    python train_decoder.py            # entrena, valida y serializa el modelo
    python train_decoder.py --demo     # reproduce la sesión E de un sujeto
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.io import loadmat

# Banda mu/beta y parámetros de época compartidos con neurogate.mi_decoder.
from neurogate.mi_decoder import BAND_HZ, DEFAULT_MODEL_PATH, LABEL_TO_INTENT

ROOT = Path(__file__).resolve().parent

# Carpeta local con los .mat de BCI IV 2a (ver ruta indicada por el orquestador).
DATA_DIR = (
    ROOT / "eeg_data" / "datasset de eeg" / "D-" / "eeg_data"
    / "MNE-bnci-data" / "~bci" / "database" / "001-2014"
)

SFREQ = 250                  # Hz, fijo en BCI IV 2a
N_EEG = 22                   # primeros 22 canales son EEG; los 3 últimos son EOG
N_SUBJECTS = 9

# Ventana de motor imagery relativa al marcador de trial (la cue aparece en t=0
# del marcador; el sujeto imagina el movimiento ~2-6 s después). Tomamos 2-6 s.
TRIAL_TMIN_S = 2.0
TRIAL_TMAX_S = 6.0

# Nombres de canal EEG (22) de BCI IV 2a, para metadatos del modelo.
CH_NAMES = [
    "Fz", "FC3", "FC1", "FCz", "FC2", "FC4", "C5", "C3", "C1", "Cz", "C2",
    "C4", "C6", "CP3", "CP1", "CPz", "CP2", "CP4", "P1", "Pz", "P2", "POz",
]


def _mat_path(subject: int, session: str) -> Path:
    """Ruta del .mat de un sujeto y sesión ('T' entreno, 'E' evaluación)."""
    return DATA_DIR / f"A{subject:02d}{session}.mat"


def load_session_epochs(subject: int, session: str
                        ) -> tuple[np.ndarray, np.ndarray]:
    """Carga las épocas de motor imagery de una sesión.

    Devuelve (epochs, labels): epochs con forma (n_trials, 22, n_muestras) en
    microvoltios, labels enteros 1..4. Usa los 22 canales EEG (descarta EOG) y
    la ventana TRIAL_TMIN_S..TRIAL_TMAX_S de cada trial.
    """
    path = _mat_path(subject, session)
    if not path.exists():
        raise FileNotFoundError(f"No encontrado: {path}")

    data = loadmat(path, struct_as_record=False, squeeze_me=True)["data"]
    runs = data if isinstance(data, np.ndarray) else [data]

    start = int(round(TRIAL_TMIN_S * SFREQ))
    stop = int(round(TRIAL_TMAX_S * SFREQ))
    win = stop - start

    epochs, labels = [], []
    for run in runs:
        trial = np.atleast_1d(getattr(run, "trial", []))
        y = np.atleast_1d(getattr(run, "y", []))
        # Runs de baseline (sin trials o sin etiquetas) se ignoran.
        if trial.size < 2 or y.size < 2:
            continue
        X = run.X[:, :N_EEG]  # (muestras, 22), descarta EOG
        n_samples = X.shape[0]
        for onset, label in zip(trial, y):
            a = int(onset) + start
            b = a + win
            if b > n_samples:
                continue
            epochs.append(X[a:b, :].T)  # -> (22, win)
            labels.append(int(label))

    if not epochs:
        raise RuntimeError(f"Sin épocas válidas en {path}")
    return np.asarray(epochs, dtype=np.float64), np.asarray(labels, dtype=int)


def filter_epochs(epochs: np.ndarray) -> np.ndarray:
    """Aplica el filtro banda 8-30 Hz a un lote de épocas (n, canales, muestras)."""
    import mne

    mne.set_log_level("WARNING")
    return mne.filter.filter_data(
        epochs, SFREQ, BAND_HZ[0], BAND_HZ[1], verbose=False)


def build_pipeline(n_components: int = 6):
    """Pipeline CSP (MNE) + LDA (scikit-learn) para 4 clases."""
    from mne.decoding import CSP
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.pipeline import Pipeline

    csp = CSP(n_components=n_components, reg=None, log=True, norm_trace=False)
    lda = LinearDiscriminantAnalysis()
    return Pipeline([("csp", csp), ("lda", lda)])


def cross_validate_subject(subject: int, n_splits: int = 5, seed: int = 42
                           ) -> tuple[float, float]:
    """Validación cruzada (k-fold) sobre la sesión de entreno de un sujeto.

    Devuelve (media, desviación) de la accuracy en los folds. Evaluamos sobre la
    sesión T (entreno) con k-fold estratificado: es la validación honesta por
    sujeto del clasificador.
    """
    from sklearn.model_selection import StratifiedKFold, cross_val_score

    epochs, labels = load_session_epochs(subject, "T")
    filtered = filter_epochs(epochs)
    pipeline = build_pipeline()
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    scores = cross_val_score(pipeline, filtered, labels, cv=cv, n_jobs=1)
    return float(scores.mean()), float(scores.std())


def evaluate_holdout(subject: int) -> float:
    """Entrena en la sesión T y evalúa en la sesión E (held-out) de un sujeto."""
    Xtr, ytr = load_session_epochs(subject, "T")
    Xte, yte = load_session_epochs(subject, "E")
    pipeline = build_pipeline()
    pipeline.fit(filter_epochs(Xtr), ytr)
    pred = pipeline.predict(filter_epochs(Xte))
    return float(np.mean(pred == yte))


def train_and_serialize(model_path: Path = DEFAULT_MODEL_PATH,
                        train_subject: int = 1) -> dict:
    """Entrena el modelo de runtime sobre un sujeto y lo serializa con joblib.

    El modelo de runtime se entrena con TODA la sesión T del sujeto elegido
    (entrenamiento intra-sujeto, el escenario realista de un BCI calibrado por
    usuario). La accuracy reportada para juzgarlo es la de validación cruzada.
    """
    import joblib

    epochs, labels = load_session_epochs(train_subject, "T")
    pipeline = build_pipeline()
    pipeline.fit(filter_epochs(epochs), labels)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "pipeline": pipeline,
        "sfreq": SFREQ,
        "band": BAND_HZ,
        "ch_names": CH_NAMES,
        "trained_on_subject": train_subject,
        "window_s": (TRIAL_TMIN_S, TRIAL_TMAX_S),
    }
    joblib.dump(bundle, model_path)
    return bundle


def run_cross_validation(report_path: Path | None = None) -> str:
    """Valida los 9 sujetos por k-fold, imprime y opcionalmente guarda el informe."""
    lines = ["Fase B — decoder real (BCI Competition IV 2a)",
             "=" * 52,
             "Camino de carga: scipy.io.loadmat (offline, copia local).",
             "Pipeline: filtro 8-30 Hz (MNE) -> CSP (6 comp.) -> LDA.",
             "Clases: left_hand, right_hand, feet, tongue (4 clases).",
             "Validación: k-fold estratificado (k=5) sobre la sesión T por sujeto.",
             ""]
    cv_accs, ho_accs = [], []
    for s in range(1, N_SUBJECTS + 1):
        mean, std = cross_validate_subject(s)
        ho = evaluate_holdout(s)
        cv_accs.append(mean)
        ho_accs.append(ho)
        lines.append(
            f"  Sujeto A{s:02d}:  CV k-fold = {mean:5.1%} ± {std:4.1%}   "
            f"|  T->E held-out = {ho:5.1%}")
    lines.append("")
    lines.append(
        f"  Media CV (9 sujetos):        {np.mean(cv_accs):.1%} "
        f"± {np.std(cv_accs):.1%}")
    lines.append(
        f"  Media held-out T->E:         {np.mean(ho_accs):.1%} "
        f"± {np.std(ho_accs):.1%}")
    lines.append("")
    lines.append("Nota: en motor imagery de 4 clases, 60-80% por sujeto es lo")
    lines.append("normal. El azar es 25%. Cifras reales, sin inflar.")

    report = "\n".join(lines) + "\n"
    print(report)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
    return report


def run_demo(subject: int = 1, n_show: int = 20,
             report_path: Path | None = None) -> str:
    """Reproduce la sesión E (held-out) de un sujeto y decodifica con confianza.

    Carga el modelo serializado, toma las primeras épocas de la sesión de
    evaluación y muestra intención decodificada + confianza vs etiqueta real.
    """
    from neurogate.mi_decoder import MotorImageryDecoder

    if report_path is None:
        report_path = ROOT / "demos" / "phaseB_decoder.txt"

    decoder = MotorImageryDecoder()
    epochs, labels = load_session_epochs(subject, "E")

    lines = [f"Fase B — demo decoder real · sesión E (held-out) sujeto A{subject:02d}",
             "=" * 60,
             f"Modelo: {decoder.model_path.name}  (entrenado en sesión T)",
             f"Épocas de evaluación: {len(epochs)}  ·  mostrando las primeras {n_show}",
             ""]

    correct_all = 0
    for ep, true_label in zip(epochs, labels):
        decision = decoder.decode(ep)
        true_intent = LABEL_TO_INTENT[int(true_label)].value
        correct_all += (decision.intent.value == true_intent)

    shown = 0
    for ep, true_label in zip(epochs, labels):
        if shown >= n_show:
            break
        decision = decoder.decode(ep)
        true_intent = LABEL_TO_INTENT[int(true_label)].value
        ok = decision.intent.value == true_intent
        lines.append(
            f"  real {true_intent:11s} -> decoder {decision.intent.value:11s}  "
            f"conf={decision.confidence:4.0%}  {'OK' if ok else 'x'}")
        shown += 1

    acc = correct_all / len(epochs)
    lines.append("")
    lines.append(f"Accuracy sobre TODA la sesión E (held-out): {acc:.1%} "
                 f"({correct_all}/{len(epochs)})")
    lines.append("Confianza = probabilidad de la clase ganadora (CSP+LDA).")
    lines.append("Por debajo del umbral configurable, la intención se reporta idle.")

    report = "\n".join(lines) + "\n"
    print(report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrena el decoder real (Fase B).")
    parser.add_argument("--demo", action="store_true",
                        help="Reproduce la sesión E de un sujeto en vez de entrenar.")
    parser.add_argument("--subject", type=int, default=1,
                        help="Sujeto para entrenar el modelo / la demo (1..9).")
    parser.add_argument("--no-cv", action="store_true",
                        help="Omite la validación cruzada por sujeto (más rápido).")
    args = parser.parse_args()

    if args.demo:
        run_demo(subject=args.subject)
        return

    if not args.no_cv:
        run_cross_validation(report_path=ROOT / "demos" / "phaseB_crossval.txt")

    print(f"Entrenando modelo de runtime sobre el sujeto A{args.subject:02d}...")
    bundle = train_and_serialize(train_subject=args.subject)
    print(f"Modelo serializado en {DEFAULT_MODEL_PATH}  "
          f"(sujeto A{bundle['trained_on_subject']:02d}, "
          f"{len(bundle['ch_names'])} canales EEG).")


if __name__ == "__main__":
    main()
