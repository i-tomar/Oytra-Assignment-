"""Plain-numpy evaluation metrics + a dependency-free calibration chart (SVG; PNG rendered by headless Chrome if present)."""
import os, shutil, subprocess
import numpy as np

BUCKETS = [0.0, 0.2, 0.4, 0.6, 0.875, 1.0001]

def average_precision(y, p):
    """PR-AUC as average precision (sklearn's definition: sum over positives of precision at that rank)."""
    y, p = np.asarray(y), np.asarray(p)
    o = np.argsort(-p, kind="mergesort"); y = y[o]
    tp = np.cumsum(y); prec = tp / np.arange(1, len(y) + 1)
    return float((prec * y).sum() / max(y.sum(), 1))

def brier(y, p): return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))

def ece(y, p, bins=10):
    """Expected calibration error, equal-width bins."""
    y, p = np.asarray(y, float), np.asarray(p, float); b = np.minimum((p * bins).astype(int), bins - 1)
    return float(sum(abs(p[b == k].mean() - y[b == k].mean()) * (b == k).sum() for k in range(bins) if (b == k).any()) / len(y))

def majority_accuracy(y):
    y = np.asarray(y); return float(max(y.mean(), 1 - y.mean()))

def risk_buckets(y, p, edges=BUCKETS):
    y, p = np.asarray(y), np.asarray(p); out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi)
        out.append({"bucket": f"{lo:.0%}–{min(hi, 1):.1%}".replace(".0%", "%") if hi < 1 else f"{lo:.1%}+".replace(".0%", "%"),
                    "orders": int(m.sum()), "rto": int(y[m].sum()),
                    "mean_predicted": round(float(p[m].mean()), 3) if m.any() else None,
                    "actual_rto_rate": round(float(y[m].mean()), 3) if m.any() else None})
    return out

def summary(y, p):
    y = np.asarray(y)
    return {"pr_auc_average_precision": round(average_precision(y, p), 3), "base_rate": round(float(y.mean()), 3),
            "brier": round(brier(y, p), 4), "ece_10bin": round(ece(y, p), 3), "brier_if_always_base_rate": round(brier(y, np.full(len(y), y.mean())), 4),
            "majority_class_accuracy": round(majority_accuracy(y), 4),
            "majority_class_note": "Context only: always predicting 'delivered' is this accurate, so accuracy is not used to judge the model."}

def calibration_svg(rows, path, title="September calibration: predicted vs actual RTO (329 orders)"):
    """rows: list of {mean_predicted, actual_rto_rate, orders}. Writes a small self-contained SVG."""
    W, H, L, B, T, Rm = 520, 420, 60, 50, 40, 20
    pw, ph = W - L - Rm, H - B - T
    X = lambda v: L + v * pw; Y = lambda v: T + (1 - v) * ph
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="Arial, sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="white"/>', f'<text x="{W/2}" y="22" text-anchor="middle" font-size="15" font-weight="bold">{title}</text>']
    for v in [0, .2, .4, .6, .8, 1]:
        s += [f'<line x1="{X(v)}" y1="{Y(0)}" x2="{X(v)}" y2="{Y(1)}" stroke="#eee"/>', f'<line x1="{X(0)}" y1="{Y(v)}" x2="{X(1)}" y2="{Y(v)}" stroke="#eee"/>',
              f'<text x="{X(v)}" y="{Y(0)+16}" text-anchor="middle">{v:.0%}</text>', f'<text x="{X(0)-6}" y="{Y(v)+4}" text-anchor="end">{v:.0%}</text>']
    s += [f'<line x1="{X(0)}" y1="{Y(0)}" x2="{X(1)}" y2="{Y(1)}" stroke="#999" stroke-dasharray="5,4"/>',
          f'<text x="{X(.62)}" y="{Y(.7)}" fill="#777" transform="rotate(-38 {X(.62)} {Y(.7)})">perfect calibration</text>',
          f'<rect x="{X(0)}" y="{Y(1)}" width="{pw}" height="{ph}" fill="none" stroke="#333"/>',
          f'<text x="{L+pw/2}" y="{H-12}" text-anchor="middle">Predicted RTO risk (bucket mean)</text>',
          f'<text x="16" y="{T+ph/2}" text-anchor="middle" transform="rotate(-90 16 {T+ph/2})">Actual RTO rate</text>']
    pts = [r for r in rows if r["orders"]]
    s.append('<polyline fill="none" stroke="#c0392b" stroke-width="2" points="' + " ".join(f'{X(r["mean_predicted"])},{Y(r["actual_rto_rate"])}' for r in pts) + '"/>')
    for r in pts:
        rad = 4 + 10 * (r["orders"] / max(q["orders"] for q in pts)) ** .5
        s += [f'<circle cx="{X(r["mean_predicted"])}" cy="{Y(r["actual_rto_rate"])}" r="{rad:.1f}" fill="#c0392b" fill-opacity=".6"/>',
              (f'<text x="{X(r["mean_predicted"])-rad-3}" y="{Y(r["actual_rto_rate"])+14}" text-anchor="end" font-size="11">' if r["mean_predicted"] > .8 else
               f'<text x="{X(r["mean_predicted"])+rad+3}" y="{Y(r["actual_rto_rate"])+4}" font-size="11">') + f'{r["bucket"]}: {r["rto"]}/{r["orders"]} RTO</text>']
    s.append("</svg>")
    open(path, "w").write("\n".join(s)); return path

def svg_to_png(svg_path, png_path, size=(520, 420)):
    """Render with headless Chrome if installed; returns png path or None (SVG is always kept)."""
    exe = next((shutil.which(x) for x in ("google-chrome", "chromium", "chromium-browser") if shutil.which(x)), None)
    if not exe: return None
    try:
        subprocess.run([exe, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", f"--window-size={size[0]},{size[1]}",
                        f"--screenshot={os.path.abspath(png_path)}", "file://" + os.path.abspath(svg_path)], check=True, capture_output=True, timeout=60)
        return png_path
    except Exception: return None
