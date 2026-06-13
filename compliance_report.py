"""Generador de informe de cumplimiento (MVP monetizable).

Toma un log de auditoría firmado (el que produce ``signed_audit.py``) y la clave
pública Ed25519, **verifica su integridad** y emite un **informe de cumplimiento**
que cruza cada tipo de decisión registrada con el requisito regulatorio que
satisface (mapeo de SPEC-V2 §3: Colorado HB1058, CCPA, Montana SB163, UNESCO).

Es la "prueba auditable de consentimiento granular, revocable y trazable" que las
leyes de datos neuronales exigen: un entregable que un responsable de cumplimiento
(DPO) o un comité de ética (IRB) puede enseñar a un regulador. El informe va él
mismo con el veredicto de verificación y el hash final del log, de modo que es
citable como evidencia.

Uso:
    python compliance_report.py <log.jsonl> <public_key.pem>
    python compliance_report.py audit_service.jsonl keys/audit_ed25519_public.pem \
        --html informe.html --json informe.json --org "Lab de Neurociencia X"

Código de salida: 0 si el log es íntegro, 1 si está alterado (o error de uso).
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path

from neurogate.signed_audit import load_public_key, verify_log

# Mapeo decisión registrada → requisito regulatorio que evidencia (SPEC-V2 §3).
# Es el guion del informe: convierte cada evento del log en prueba de una cláusula.
LEGAL_MAPPING = {
    "allow": ("Consentimiento específico y minimización de datos",
              "La app recibió solo el scope autorizado (Colorado HB1058 opt-in; "
              "Montana SB163 consentimiento expreso; CCPA dato sensible)."),
    "deny": ("Cumplimiento del límite de consentimiento",
             "Acceso fuera del scope concedido, bloqueado y registrado "
             "(minimización de datos; deber de no exceder lo consentido)."),
    "approve": ("Consentimiento informado y explícito (modo confirmación)",
                "El usuario aprobó una entrega sensible antes de que saliera el dato."),
    "quarantine": ("Deber de protección activa / minimización del daño",
                   "Comportamiento anómalo detectado y contenido automáticamente "
                   "(Montana SB163; principios de neuroderechos)."),
}

# Requisito que satisface la propia cadena firmada, independientemente de eventos.
CHAIN_REQUIREMENT = (
    "Trazabilidad y evidencia auditable por terceros",
    "Log encadenado (SHA-256) y firmado (Ed25519): un tercero verifica integridad "
    "y autenticidad solo con la clave pública, sin acceso al sistema "
    "(accountability; evidencia de cumplimiento).")


def load_events(path: Path) -> list[dict]:
    """Carga los eventos del log JSONL (campo ``event`` de cada línea)."""
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line)["event"])
    return events


def aggregate(events: list[dict]) -> dict:
    """Resume los eventos: por decisión, por app, scopes, y ventana temporal."""
    by_decision: dict[str, int] = {}
    by_app: dict[str, dict] = {}
    scopes_seen: set[str] = set()
    timestamps = []
    for ev in events:
        decision = ev.get("decision", "?")
        app = ev.get("client_id", "?")
        scope = ev.get("scope", "?")
        ts = ev.get("timestamp")
        by_decision[decision] = by_decision.get(decision, 0) + 1
        app_row = by_app.setdefault(
            app, {"allow": 0, "deny": 0, "quarantine": 0, "approve": 0, "scopes": set()})
        app_row[decision] = app_row.get(decision, 0) + 1
        app_row["scopes"].add(scope)
        scopes_seen.add(scope)
        if isinstance(ts, (int, float)):
            timestamps.append(ts)
    # Convierte los sets de scopes a listas ordenadas (serializable).
    for row in by_app.values():
        row["scopes"] = sorted(row["scopes"])
    period = None
    if timestamps:
        period = {"desde": min(timestamps), "hasta": max(timestamps)}
    return {"total_events": len(events), "by_decision": by_decision,
            "by_app": by_app, "scopes": sorted(scopes_seen), "period": period}


def build_report(log_path: Path, public_key, org: str = "") -> dict:
    """Construye el informe: verificación de integridad + agregados + mapeo legal."""
    ok, bad_line, reason = verify_log(log_path, public_key)
    events = load_events(log_path) if log_path.exists() else []
    summary = aggregate(events)
    last_hash = ""
    if events and log_path.exists():
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines:
            last_hash = json.loads(lines[-1]).get("hash", "")
    # Mapeo legal solo de las decisiones realmente presentes en el log.
    mapping = {d: LEGAL_MAPPING[d] for d in summary["by_decision"] if d in LEGAL_MAPPING}
    return {
        "org": org,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "log_path": str(log_path),
        "integrity": {"ok": ok, "first_bad_line": bad_line, "reason": reason},
        "last_hash": last_hash,
        "summary": summary,
        "legal_mapping": mapping,
        "chain_requirement": CHAIN_REQUIREMENT,
    }


def _fmt_ts(ts) -> str:
    """Formatea un timestamp epoch a fecha legible (o '—')."""
    if not isinstance(ts, (int, float)):
        return "—"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def render_text(report: dict) -> str:
    """Render del informe en texto plano (consola / .txt)."""
    s = report["summary"]
    intg = report["integrity"]
    verdict = ("INTEGRO" if intg["ok"]
               else f"ALTERADO (linea {intg['first_bad_line']})")
    hash_line = (f"  Hash final de la cadena: {report['last_hash'][:32]}..."
                 if report["last_hash"] else "  (log vacio)")
    lines = [
        "INFORME DE CUMPLIMIENTO — NeuroGate",
        "=" * 60,
        f"Organización : {report['org'] or '(sin especificar)'}",
        f"Generado     : {report['generated_at']}",
        f"Log          : {report['log_path']}",
        "",
        "INTEGRIDAD DEL REGISTRO (verificación criptográfica de terceros)",
        "-" * 60,
        f"  Resultado: {verdict} — {intg['reason']}",
        hash_line,
        "",
        f"RESUMEN ({s['total_events']} eventos registrados)",
        "-" * 60,
    ]
    if s["period"]:
        lines.append(f"  Periodo: {_fmt_ts(s['period']['desde'])}  ->  {_fmt_ts(s['period']['hasta'])}")
    lines.append(f"  Por decisión: " + ", ".join(f"{k}={v}" for k, v in sorted(s["by_decision"].items())))
    lines.append("")
    lines.append("ACCESO POR APLICACIÓN")
    lines.append("-" * 60)
    for app, row in sorted(s["by_app"].items()):
        lines.append(f"  {app}: permitido={row.get('allow',0)} denegado={row.get('deny',0)} "
                     f"cuarentena={row.get('quarantine',0)} aprobado={row.get('approve',0)}")
        lines.append(f"      scopes: {', '.join(row['scopes']) or '—'}")
    lines.append("")
    lines.append("EVIDENCIA REGULATORIA (qué cláusula satisface cada control)")
    lines.append("-" * 60)
    req, desc = report["chain_requirement"]
    lines.append(f"  [cadena firmada] {req}")
    lines.append(f"      {desc}")
    for decision, (req, desc) in report["legal_mapping"].items():
        lines.append(f"  [{decision}] {req}")
        lines.append(f"      {desc}")
    lines.append("")
    lines.append("Este informe es prueba auditable de consentimiento granular, revocable")
    lines.append("y trazable de datos neuronales. Verificable de forma independiente con")
    lines.append("verify_audit.py y la clave pública del emisor.")
    return "\n".join(lines) + "\n"


def render_json(report: dict) -> str:
    """Render estructurado (para integraciones / archivo)."""
    return json.dumps(report, ensure_ascii=False, indent=2)


def render_html(report: dict) -> str:
    """Render del informe en HTML (el entregable que se enseña a un regulador)."""
    s = report["summary"]
    intg = report["integrity"]
    ok = intg["ok"]
    badge = ("<span style='color:#0a0;font-weight:bold'>ÍNTEGRO ✓</span>" if ok
             else f"<span style='color:#c00;font-weight:bold'>ALTERADO ✗ (línea {intg['first_bad_line']})</span>")
    rows_app = "".join(
        f"<tr><td>{html.escape(app)}</td><td>{r.get('allow',0)}</td><td>{r.get('deny',0)}</td>"
        f"<td>{r.get('quarantine',0)}</td><td>{r.get('approve',0)}</td>"
        f"<td>{html.escape(', '.join(r['scopes']))}</td></tr>"
        for app, r in sorted(s["by_app"].items()))
    req_rows = ""
    req, desc = report["chain_requirement"]
    req_rows += f"<tr><td><b>cadena firmada</b></td><td>{html.escape(req)}</td><td>{html.escape(desc)}</td></tr>"
    for decision, (req, desc) in report["legal_mapping"].items():
        req_rows += f"<tr><td>{html.escape(decision)}</td><td>{html.escape(req)}</td><td>{html.escape(desc)}</td></tr>"
    period = ""
    if s["period"]:
        period = f"<p><b>Periodo:</b> {_fmt_ts(s['period']['desde'])} → {_fmt_ts(s['period']['hasta'])}</p>"
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Informe de cumplimiento — NeuroGate</title>
<style>
 body{{font-family:system-ui,Arial,sans-serif;max-width:900px;margin:2rem auto;color:#222;padding:0 1rem}}
 h1{{font-size:1.4rem}} table{{border-collapse:collapse;width:100%;margin:.5rem 0}}
 th,td{{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;font-size:.9rem;vertical-align:top}}
 th{{background:#f3f4f6}} .box{{background:#f8fafc;border:1px solid #e2e8f0;padding:.8rem;border-radius:6px}}
 code{{font-size:.8rem;word-break:break-all}}
</style></head><body>
<h1>🧠🛡️ Informe de cumplimiento — NeuroGate</h1>
<p><b>Organización:</b> {html.escape(report['org'] or '(sin especificar)')} ·
   <b>Generado:</b> {report['generated_at']}</p>
<div class="box"><b>Integridad del registro:</b> {badge} — {html.escape(intg['reason'])}<br>
<b>Hash final de la cadena:</b> <code>{html.escape(report['last_hash'])}</code></div>
<p><b>{s['total_events']}</b> eventos registrados.</p>{period}
<h2>Acceso por aplicación</h2>
<table><tr><th>App</th><th>Permitido</th><th>Denegado</th><th>Cuarentena</th><th>Aprobado</th><th>Scopes</th></tr>
{rows_app}</table>
<h2>Evidencia regulatoria</h2>
<table><tr><th>Control</th><th>Requisito que satisface</th><th>Detalle</th></tr>
{req_rows}</table>
<p style="font-size:.85rem;color:#555">Prueba auditable de consentimiento granular, revocable y
trazable de datos neuronales. Verificable de forma independiente con la clave pública del emisor.</p>
</body></html>
"""


def main(argv: list[str]) -> int:
    """CLI del generador de informe. Devuelve el código de salida."""
    parser = argparse.ArgumentParser(description="Informe de cumplimiento NeuroGate")
    parser.add_argument("log", help="ruta del log de auditoría firmado (JSONL)")
    parser.add_argument("public_key", help="clave pública Ed25519 (PEM)")
    parser.add_argument("--org", default="", help="nombre de la organización")
    parser.add_argument("--html", help="ruta de salida HTML")
    parser.add_argument("--json", dest="json_out", help="ruta de salida JSON")
    args = parser.parse_args(argv[1:])

    log_path = Path(args.log)
    key_path = Path(args.public_key)
    if not log_path.exists():
        print(f"ERROR: no existe el log: {log_path}")
        return 1
    if not key_path.exists():
        print(f"ERROR: no existe la clave pública: {key_path}")
        return 1

    public_key = load_public_key(key_path.read_bytes())
    report = build_report(log_path, public_key, org=args.org)

    print(render_text(report))
    if args.html:
        Path(args.html).write_text(render_html(report), encoding="utf-8")
        print(f"HTML escrito en {args.html}")
    if args.json_out:
        Path(args.json_out).write_text(render_json(report), encoding="utf-8")
        print(f"JSON escrito en {args.json_out}")

    return 0 if report["integrity"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
