"""HTML/CSS/JS template for the founder dashboard. Design spec: docs/DESIGN.md.
Static single file: inline CSS custom properties (light + dark tokens), inline JS for the theme
toggle and table filter/sort. No external requests, works offline. All numbers are passed in by
oytra/dashboard.py; nothing here computes or invents figures."""
import os, html, datetime as dt
from .config import ROOT
from .economics import LABEL

ORDER = ["SHIP", "CONFIRM", "NUDGE", "HOLD"]
KEY = {"SHIP": "ship", "CONFIRM": "confirm", "NUDGE": "nudge", "HOLD": "hold"}
HELP = {"SHIP": "Low risk. Ships straight away, no message sent.",
        "CONFIRM": "Medium risk. WhatsApp asks the customer to confirm before it ships.",
        "NUDGE": "High risk. WhatsApp offers a small discount to pay online first.",
        "HOLD": "Very high risk. Held for ops to call or cancel. First-time buyers are never auto-cancelled."}
ICON = {"SHIP": "✓", "CONFIRM": "?", "NUDGE": "₹", "HOLD": "■"}

def pct(x): return f"{x*100:.1f}".rstrip('0').rstrip('.') + '%'
def rs(x): return ("−" if x < 0 else "") + "₹" + f"{abs(x):,.0f}"
def e(x): return html.escape(str(x))
def sign(x): return "pos" if x >= 0 else "neg"
def tip(text): return f'<span class="tip" tabindex="0" role="note" aria-label="{e(text)}" data-tip="{e(text)}">i</span>'

CSS = """
:root{--font:system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans",sans-serif;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
--fs-xs:12px;--fs-sm:13px;--fs-md:15px;--fs-lg:18px;--fs-xl:24px;--fs-2xl:32px;--fs-3xl:44px;
--sp-1:4px;--sp-2:8px;--sp-3:12px;--sp-4:16px;--sp-5:24px;--sp-6:32px;--radius:12px;--radius-sm:6px}
:root,[data-theme=light]{color-scheme:light;--bg:#f5f6f8;--surface:#ffffff;--surface-2:#f0f2f5;--border:#dfe3e8;--text:#14171c;--text-2:#4a5260;--text-3:#5f6876;
--accent:#3b4fd8;--pos:#17732f;--neg:#c4291c;--shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.08);
--ship:#17732f;--ship-bg:#e6f4ea;--confirm:#1f5fbf;--confirm-bg:#e5effc;--nudge:#a64d00;--nudge-bg:#fdf0e1;--hold:#c4291c;--hold-bg:#fde8e6;--chart-bg:#ffffff}
[data-theme=dark]{color-scheme:dark;--bg:#0e1116;--surface:#161b22;--surface-2:#1f2630;--border:#2d3640;--text:#e8ecf1;--text-2:#b3bcc8;--text-3:#9aa4b1;
--accent:#8c9bff;--pos:#4cc76a;--neg:#ff7b70;--shadow:0 1px 2px rgba(0,0,0,.4);
--ship:#4cc76a;--ship-bg:#12301c;--confirm:#6aa8ff;--confirm-bg:#132640;--nudge:#ffa94d;--nudge-bg:#3a2511;--hold:#ff7b70;--hold-bg:#3d1714;--chart-bg:#f3f5f8}
*{box-sizing:border-box}html{background:var(--bg)}body{margin:0;font-family:var(--font);font-size:var(--fs-md);line-height:1.5;color:var(--text);background:var(--bg)}
a{color:var(--accent)}.wrap{max-width:1200px;margin:0 auto;padding:0 var(--sp-5)}
.skip{position:absolute;left:-999px}.skip:focus{left:var(--sp-4);top:var(--sp-2);background:var(--surface);padding:var(--sp-2);z-index:9}
header.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--border)}
header.top .wrap{display:flex;align-items:center;gap:var(--sp-4);height:60px}
.logo{font-weight:800;letter-spacing:.04em;font-size:var(--fs-lg)}.logo span{color:var(--accent)}
.hdr-meta{color:var(--text-2);font-size:var(--fs-sm);flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav.jump{display:flex;gap:var(--sp-3);font-size:var(--fs-sm)}nav.jump a{color:var(--text-2);text-decoration:none}nav.jump a:hover{color:var(--text)}
.toggle{display:inline-flex;border:1px solid var(--border);border-radius:999px;padding:2px;background:var(--surface)}
.toggle button{font:inherit;font-size:var(--fs-sm);border:0;background:transparent;color:var(--text-2);padding:4px 12px;border-radius:999px;cursor:pointer;min-height:32px}
.toggle button[aria-pressed=true]{background:var(--text);color:var(--bg);font-weight:600}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
h1{font-size:var(--fs-xl);margin:var(--sp-5) 0 var(--sp-1)}h2{font-size:var(--fs-lg);margin:0}
.lede{color:var(--text-2);margin:0 0 var(--sp-5)}
section{margin:0 0 var(--sp-6)}.sec-h{display:flex;align-items:baseline;gap:var(--sp-3);flex-wrap:wrap;margin-bottom:var(--sp-3)}.sec-h p{margin:0;color:var(--text-3);font-size:var(--fs-sm)}
.grid{display:grid;gap:var(--sp-4)}.g-hero{grid-template-columns:1.4fr 1fr 1fr 1fr}.g-3{grid-template-columns:repeat(3,1fr)}.g-2{grid-template-columns:repeat(2,1fr)}.g-q{grid-template-columns:1fr 1fr 320px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:var(--sp-4) var(--sp-5);box-shadow:var(--shadow);min-width:0}
.kpi .l{font-size:var(--fs-sm);color:var(--text-2);display:flex;gap:var(--sp-2);align-items:center}
.kpi .v{font-size:var(--fs-2xl);font-weight:750;letter-spacing:-.01em;font-variant-numeric:tabular-nums;margin:var(--sp-1) 0}
.kpi .h{font-size:var(--fs-xs);color:var(--text-3)}.kpi.hero{border-top:4px solid var(--pos)}.kpi.hero.neg{border-top-color:var(--neg)}.kpi.hero .v{font-size:var(--fs-3xl)}
.pos{color:var(--pos)}.neg{color:var(--neg)}
.pill{display:inline-block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;padding:2px 8px;border-radius:999px;background:var(--surface-2);color:var(--text-2)}
.tip{position:relative;display:inline-grid;place-items:center;width:16px;height:16px;border-radius:50%;border:1px solid var(--text-3);color:var(--text-3);font-size:10px;font-weight:700;cursor:help;font-style:normal}
.tip:hover::after,.tip:focus::after{content:attr(data-tip);position:absolute;left:50%;top:22px;transform:translateX(-50%);width:max-content;max-width:260px;background:var(--text);color:var(--bg);padding:8px 10px;border-radius:var(--radius-sm);font-size:var(--fs-xs);font-weight:400;line-height:1.4;z-index:10;white-space:normal;text-align:left}
.buckets{display:grid;grid-template-columns:repeat(4,1fr);gap:var(--sp-3)}
.bk{border-radius:var(--radius);padding:var(--sp-3) var(--sp-4);background:var(--bk-bg);border:1px solid var(--border);color:var(--text)}
.bk .n{font-size:var(--fs-2xl);font-weight:750;color:var(--bk);font-variant-numeric:tabular-nums;line-height:1.1}.bk .t{font-weight:600;font-size:var(--fs-sm)}.bk .d{font-size:var(--fs-xs);color:var(--text-2);margin-top:2px}
.bk.empty .n{opacity:.55}
.ship{--bk:var(--ship);--bk-bg:var(--ship-bg)}.confirm{--bk:var(--confirm);--bk-bg:var(--confirm-bg)}.nudge{--bk:var(--nudge);--bk-bg:var(--nudge-bg)}.hold{--bk:var(--hold);--bk-bg:var(--hold-bg)}
.stack{display:flex;height:14px;border-radius:999px;overflow:hidden;background:var(--surface-2);margin:var(--sp-3) 0 var(--sp-2)}.stack i{display:block;background:var(--bk);min-width:0}
.legend{display:flex;flex-wrap:wrap;gap:var(--sp-3);font-size:var(--fs-xs);color:var(--text-2)}.legend b{display:inline-block;width:10px;height:10px;border-radius:3px;background:var(--bk);margin-right:4px;vertical-align:-1px}
.badge{display:inline-flex;align-items:center;gap:4px;white-space:nowrap;font-size:var(--fs-xs);font-weight:650;padding:2px 9px;border-radius:999px;color:var(--bk);background:var(--bk-bg);border:1px solid color-mix(in srgb,var(--bk) 35%,transparent)}
.mini th,.mini td{padding:4px 6px;font-size:var(--fs-xs)}
table{width:100%;border-collapse:collapse;font-size:var(--fs-sm);font-variant-numeric:tabular-nums}
th,td{padding:var(--sp-2) var(--sp-3);text-align:left;border-bottom:1px solid var(--border);vertical-align:top}th{color:var(--text-2);font-weight:600}
td.num,th.num{text-align:right}
.cmp tr.ours td{font-weight:650;background:var(--surface-2)}
.trend svg{width:100%;height:120px;display:block}.trend .axis{stroke:var(--border)}.trend .p{fill:var(--pos)}.trend .n{fill:var(--neg)}
.cal{background:var(--chart-bg);border-radius:var(--radius-sm);padding:4px}.cal svg{width:100%;height:auto;display:block}
.tools{display:flex;flex-wrap:wrap;gap:var(--sp-2);align-items:center;margin-bottom:var(--sp-3)}
.tools input{font:inherit;font-size:var(--fs-sm);padding:6px 10px;min-height:36px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--text);flex:1;min-width:180px}
.chip{font:inherit;font-size:var(--fs-xs);font-weight:600;min-height:32px;padding:4px 12px;border-radius:999px;border:1px solid var(--border);background:var(--surface);color:var(--text-2);cursor:pointer}
.chip[aria-pressed=true]{background:var(--text);color:var(--bg);border-color:var(--text)}
.tbl{max-height:560px;overflow:auto;border:1px solid var(--border);border-radius:var(--radius);background:var(--surface)}
.tbl thead th{position:sticky;top:0;background:var(--surface-2);z-index:1}
.tbl th button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer;font-weight:600}.tbl th button::after{content:" ↕";opacity:.4}
.tbl th[aria-sort=ascending] button::after{content:" ↑";opacity:1}.tbl th[aria-sort=descending] button::after{content:" ↓";opacity:1}
.tbl tbody tr:hover{background:var(--surface-2)}.why{color:var(--text-2);min-width:260px}.mono{font-family:var(--mono);font-size:var(--fs-xs)}
.riskbar{display:inline-block;width:42px;height:6px;border-radius:3px;background:var(--surface-2);margin-left:6px;vertical-align:middle;overflow:hidden}.riskbar i{display:block;height:100%;background:var(--bk)}
.empty-state{padding:var(--sp-6);text-align:center;color:var(--text-3)}.count{font-size:var(--fs-xs);color:var(--text-3)}
footer{border-top:1px solid var(--border);padding:var(--sp-5) 0 var(--sp-6);font-size:var(--fs-xs);color:var(--text-3)}footer p{margin:0 0 var(--sp-2);max-width:900px}
@media (max-width:980px){.g-hero{grid-template-columns:1fr 1fr}.g-q{grid-template-columns:1fr 1fr}.g-q .cal-card{grid-column:1/-1}nav.jump{display:none}}
@media (max-width:640px){.wrap{padding:0 var(--sp-3)}.g-hero,.g-3,.g-2,.g-q{grid-template-columns:1fr}.buckets{grid-template-columns:1fr 1fr}.hdr-meta{display:none}.kpi.hero .v{font-size:var(--fs-2xl)}.card{padding:var(--sp-3) var(--sp-4)}.cmp{font-size:var(--fs-xs)}}
@media print{header.top{position:static}.toggle,.tools,nav.jump,.skip{display:none}.tbl{max-height:none;overflow:visible}body{background:#fff}.card{box-shadow:none;break-inside:avoid}}
@media (prefers-reduced-motion:no-preference){.chip,.toggle button{transition:background .15s,color .15s}}
"""

JS = r"""
(function(){var K='oytra-theme',root=document.documentElement,btns=document.querySelectorAll('[data-set-theme]');
function apply(t){var eff=t==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):t;root.setAttribute('data-theme',eff);
btns.forEach(function(b){b.setAttribute('aria-pressed',b.dataset.setTheme===t?'true':'false')});}
var saved;try{saved=localStorage.getItem(K)}catch(e){}apply(saved||'system');
btns.forEach(function(b){b.addEventListener('click',function(){var t=b.dataset.setTheme;try{t==='system'?localStorage.removeItem(K):localStorage.setItem(K,t)}catch(e){}apply(t)})});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',function(){var s;try{s=localStorage.getItem(K)}catch(e){}if(!s)apply('system')});
var tb=document.querySelector('#orders tbody');if(!tb)return;var rows=[].slice.call(tb.rows),q=document.getElementById('q'),act='ALL',chips=document.querySelectorAll('[data-filter]'),
cnt=document.getElementById('count'),emp=document.getElementById('empty');
function filt(){var s=(q.value||'').toLowerCase().trim(),n=0;rows.forEach(function(r){var ok=(act==='ALL'||r.dataset.action===act)&&(!s||r.dataset.search.indexOf(s)>=0);r.hidden=!ok;if(ok)n++});
cnt.textContent=n+' of '+rows.length+' orders';emp.hidden=n>0;}
q.addEventListener('input',filt);chips.forEach(function(c){c.addEventListener('click',function(){act=c.dataset.filter;chips.forEach(function(x){x.setAttribute('aria-pressed',x===c?'true':'false')});filt()})});
document.querySelectorAll('#orders th[data-key]').forEach(function(th){th.querySelector('button').addEventListener('click',function(){var k=th.dataset.key,num=th.dataset.type==='num',
dir=th.getAttribute('aria-sort')==='ascending'?'descending':'ascending';document.querySelectorAll('#orders th[data-key]').forEach(function(x){x.removeAttribute('aria-sort')});th.setAttribute('aria-sort',dir);
rows.sort(function(a,b){var x=a.dataset[k],y=b.dataset[k];if(num){x=+x;y=+y}var c=x<y?-1:x>y?1:0;return dir==='ascending'?c:-c});rows.forEach(function(r){tb.appendChild(r)})})});filt();})();
"""

def bucket_cards(counts, total):
    out = []
    for a in ORDER:
        n = int(counts[a]); share = f"{n/total:.0%} of the day" if total else "no orders"
        out.append(f'<div class="bk {KEY[a]}{" empty" if n == 0 else ""}"><div class="n">{n}</div><div class="t">{ICON[a]} {LABEL[a]} {tip(HELP[a])}</div><div class="d">{share}</div></div>')
    return "".join(out)

def stack(counts, total, rto=None):
    segs = "".join(f'<i class="{KEY[a]}" style="width:{counts[a]/total*100:.2f}%" title="{LABEL[a]}: {counts[a]}"></i>' for a in ORDER if total and counts[a])
    leg = "".join(f'<span class="{KEY[a]}"><b></b>{LABEL[a]} {counts[a]}{(" · " + rto[LABEL[a]] + " RTO") if rto and LABEL[a] in rto else ""}</span>' for a in ORDER)
    return f'<div class="stack" role="img" aria-label="Orders by action">{segs}</div><div class="legend">{leg}</div>'

def trend_svg(trend):
    if not trend: return '<div class="empty-state">No September days to show.</div>'
    W, H, mid = 600, 120, 60; mx = max(abs(t[1]) for t in trend) or 1; bw = W / len(trend)
    bars = []
    for i, (d, n, k) in enumerate(trend):
        h = max(1.5, abs(n) / mx * (mid - 6)); y = mid - h if n >= 0 else mid
        bars.append(f'<rect class="{"p" if n >= 0 else "n"}" x="{i*bw+1.5:.1f}" y="{y:.1f}" width="{bw-3:.1f}" height="{h:.1f}" rx="1.5"><title>{d:%d %b}: {rs(n)} on {k} orders</title></rect>')
    return f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-label="Estimated net rupees per day in September"><line class="axis" x1="0" x2="{W}" y1="{mid}" y2="{mid}"/>{"".join(bars)}</svg>'

def render(day, yd, ydec, sep, R, econ, counts, meas, est, west, m_est, scen, trend, bt, sm, rb, wf):
    total = len(yd)
    sept = bt["september"]; ours, ship_all = sept["our_rules"], sept["ship_everything (Marketing)"]; ops = sept["ops_cancel_risky (Operations)"]
    inv = {v: k for k, v in LABEL.items()}
    scounts = {a: ours["counts"].get(LABEL[a], 0) for a in ORDER}; stotal = sum(scounts.values())
    svgp = os.path.join(ROOT, "reports", "calibration.svg")
    svg = open(svgp).read() if os.path.exists(svgp) else ""
    if svg:
        import re
        svg = re.sub(r'<\?xml[^>]*\?>', '', svg)
        svg = re.sub(r'<svg([^>]*?)\swidth="[^"]*"\s+height="[^"]*"', r'<svg\1', svg, count=1)
        if "viewBox" not in svg[:300]: svg = svg.replace("<svg", '<svg viewBox="0 0 520 420"', 1)
    btab = "".join(f"<tr><td>{r['bucket']}</td><td class=num>{r['orders']}</td><td class=num>{r['mean_predicted']:.0%}</td><td class=num>{r['actual_rto_rate']:.0%}</td></tr>" for r in rb if r["orders"])
    rows = []
    for o, r in zip(yd.itertuples(), ydec.itertuples()):
        why = r.reason.split(": ", 1)[1] if ": " in r.reason else r.reason
        srch = " ".join(map(str, [o.order_id, o.customer_name, o.city, why, LABEL[r.action]])).lower()
        rows.append(f'<tr data-action="{r.action}" data-search="{e(srch)}" data-id="{e(o.order_id)}" data-city="{e(str(o.city).lower())}" data-value="{o.order_value}" data-risk="{r.risk:.4f}" data-act="{ORDER.index(r.action)}">'
                    f'<td class="mono">{e(o.order_id)}</td><td>{e(o.customer_name)}</td><td>{e(o.city)}</td><td class="num">₹{o.order_value:,}</td>'
                    f'<td class="num {KEY[r.action]}">{r.risk:.0%}<span class="riskbar"><i style="width:{r.risk*100:.0f}%"></i></span></td>'
                    f'<td><span class="badge {KEY[r.action]}">{ICON[r.action]} {LABEL[r.action]}</span></td><td class="why">{e(why)}</td></tr>')
    chips = '<button class="chip" data-filter="ALL" aria-pressed="true">All</button>' + "".join(
        f'<button class="chip" data-filter="{a}" aria-pressed="false">{LABEL[a]} ({int(counts[a])})</button>' for a in ORDER)
    cmp_rows = "".join(f'<tr class="{c}"><td>{n}</td><td class=num>{rs(s["rto_cost_avoided"])}</td><td class=num>{rs(s["prepaid_delivered_contribution"])}</td><td class=num>{rs(s["lost_genuine"])}</td><td class=num>{rs(s["flow_costs"])}</td><td class="num {sign(s["net"])}"><b>{rs(s["net"])}</b></td><td class=num>{s["first_time_labelled_held_or_cancelled"]}</td><td class=num>{rs(s["marketing_metric_acquisition_spend_on_held_first_time_rupees"])}</td></tr>'
                       for c, n, s in [("ours", "Our engine (base case)", ours), ("", "Ship everything (Marketing)", ship_all), ("", "Cancel risky orders (Ops rule)", ops)])
    sc = bt["september_estimated_scenarios"]
    scen_cards = "".join(f'<div class="card kpi"><div class="l"><span class="pill">{k}</span></div><div class="v {sign(scen[k])}">{rs(scen[k])}</div>'
                         f'<div class="h">Confirmation stops {sc[k]["assumptions"]["confirm_catches_rto_share"]:.0%} of RTOs, loses {sc[k]["assumptions"]["confirm_genuine_loss_share"]:.0%} of genuine buyers; {sc[k]["assumptions"]["prepaid_takeup_if_baseline_delivered"]:.0%} of would-be-delivered and {sc[k]["assumptions"]["prepaid_takeup_if_baseline_rto"]:.0%} of would-be-RTO buyers take the prepaid offer.</div></div>'
                         for k in ["conservative", "base", "optimistic"])
    table_body = "".join(rows) if rows else ""
    wf_rows = "".join(f'<tr><td>{r["month"]}</td><td class=num>{r["train_orders"]:,}</td><td class=num>{r["roc_auc"]:.3f}</td><td class=num>{r["flagged"]} of {r["test_orders"]}</td>'
                      + "".join(f'<td class="num {sign(r["net_HYPOTHETICAL"][k])}">{rs(r["net_HYPOTHETICAL"][k])}</td>' for k in ("conservative", "base", "optimistic")) + "</tr>"
                      for r in wf["A_fixed_policy_stability"])
    return f"""<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><title>OYTRA COD — morning dashboard · {day:%d %b %Y}</title>
<script>(function(){{try{{var t=localStorage.getItem('oytra-theme');if(!t)t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';document.documentElement.setAttribute('data-theme',t)}}catch(e){{}}}})();</script>
<style>{CSS}</style></head><body>
<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="wrap"><div class="logo">OYTRA<span>·</span>COD</div>
<div class="hdr-meta">Morning dashboard · {day:%a %d %b %Y}</div>
<nav class="jump" aria-label="Sections"><a href="#yesterday">Latest day</a><a href="#september">September</a><a href="#walkforward">By month</a><a href="#quality">Model</a><a href="#orders-sec">Orders</a></nav>
<div class="toggle" role="group" aria-label="Colour theme"><button data-set-theme="light" aria-pressed="false" title="Day theme">☀ Day</button><button data-set-theme="dark" aria-pressed="false" title="Night theme">☾ Night</button><button data-set-theme="system" aria-pressed="true" title="Follow device setting">Auto</button></div>
</div></header>
<main id="main" class="wrap">
<h1>Latest day in data ({day:%d %b %Y}): COD orders</h1>
<p class="lede">{total} COD orders on {day:%a %d %b %Y} were checked by the risk engine. Thresholds from <code>config/rules.csv</code>: ship under {pct(R['ship_below_risk'])} risk · confirm under {pct(R['confirm_below_risk'])} · nudge under {pct(R['nudge_below_risk'])} · hold above.</p>

<section id="yesterday" aria-labelledby="h-y">
<div class="grid g-hero">
 <div class="card kpi hero {sign(est['net'])}"><div class="l">Net ₹ impact, latest day <span class="pill">estimated</span> {tip("Saved minus lost minus WhatsApp and discount costs. Uses each order's risk score and the base-case assumptions, because the real WhatsApp/prepaid effect is not measured yet.")}</div>
  <div class="v {sign(est['net'])}">{rs(est['net'])}</div><div class="h">Last 7 days: {rs(west['net'])} · September total from risk scores: {rs(m_est['net'])} on {len(sep)} orders (hindsight backtest: see below)</div></div>
 <div class="card kpi"><div class="l">₹ RTO cost avoided + prepaid contribution {tip("Simulated, not prevented: return-to-origin costs we expect to avoid because risky orders were confirmed, nudged to prepaid or held, plus margin from would-be RTOs that pay online and are delivered.")}</div><div class="v pos">{rs(est['saved'] + est['prepaid'])}</div><div class="h">estimated, base case</div></div>
 <div class="card kpi"><div class="l">₹ lost from genuine orders {tip("Margin we expect to lose from real buyers who drop off at confirmation or were held, No future value or CAC is added (CAC is spend already made).")}</div><div class="v neg">{rs(est['lost'])}</div><div class="h">estimated, base case</div></div>
 <div class="card kpi"><div class="l">Messages &amp; discounts {tip("WhatsApp message cost plus the prepaid discount for customers who take it.")}</div><div class="v">{rs(est['costs'])}</div><div class="h">estimated cost of the flows</div></div>
</div>
<div class="card" style="margin-top:var(--sp-4)"><div class="sec-h"><h2 id="h-y">Orders by action, latest day in data ({day:%d %b %Y})</h2><p>{meas['yflag']} of {total} flagged (not shipped as-is); {meas['yrto_flag']} of those later came back RTO.</p></div>
<div class="buckets">{bucket_cards(counts, total)}</div>{stack(counts, total) if total else '<div class="empty-state">No orders on this day.</div>'}</div>
</section>

<section id="september" aria-labelledby="h-s">
<div class="sec-h"><h2 id="h-s">September backtest</h2><p>Trained on April–August only. September is a retrospective temporal holdout (looked at during development), not an untouched test set.</p></div>
<div class="grid g-3">
 <div class="card kpi"><div class="l">RTOs in a flagged bucket <span class="pill">measured</span> {tip("Flagged, not prevented: these orders were not actually confirmed or nudged in September, so we cannot know how many RTOs the flows would have stopped.")}</div><div class="v">{meas['rto_flagged']} of {meas['rto_all']}</div><div class="h">{meas['flagged']} orders flagged; {meas['flagged_delivered']} of them were delivered fine</div></div>
 <div class="card kpi"><div class="l">RTO cost sitting in flagged orders <span class="pill">measured</span> {tip("The most the WhatsApp and prepaid flows could ever save in September.")}</div><div class="v">{rs(meas['rto_rs_flagged'])}</div><div class="h">at ₹{econ['rto_loss']:.0f} per RTO</div></div>
 <div class="card kpi"><div class="l">Orders by action, September</div>{stack(scounts, stotal, ours.get('rto_in_bucket'))}</div>
</div>
<h3 style="font-size:var(--fs-md);margin:var(--sp-5) 0 var(--sp-3)">Net ₹ for September under three sets of assumptions <span class="pill">estimated</span></h3>
<div class="grid g-3">{scen_cards}</div>
<div class="grid" style="margin-top:var(--sp-4);grid-template-columns:1fr">
 <div class="card"><div class="sec-h"><h2 style="font-size:var(--fs-md)">Compared with the other options</h2><p>September, actual outcomes, base case (simulated; RTOs avoided are flagged, not prevented)</p></div>
 <div style="overflow-x:auto"><table class="cmp"><thead><tr><th>Approach</th><th class=num>RTO cost avoided</th><th class=num>Prepaid contrib.</th><th class=num>Genuine lost</th><th class=num>Flow costs</th><th class=num>Net</th><th class=num>1st-time held</th><th class=num>Marketing metric {tip("First-time-labelled orders held × ₹" + str(econ['cac']) + " CAC: acquisition spend already made on customers we turned away. Sunk spend for Marketing, NOT part of net ₹.")}</th></tr></thead><tbody>{cmp_rows}</tbody></table></div></div>
 <div class="card trend"><div class="sec-h"><h2 style="font-size:var(--fs-md)">Estimated net ₹ per day</h2><p>September, base case, from risk scores. Hover a bar for the day.</p></div>{trend_svg(trend)}</div>
</div>
</section>

<section id="walkforward" aria-labelledby="h-w">
<div class="sec-h"><h2 id="h-w">Month by month (walk-forward)</h2><p>Each month scored by a model trained only on earlier months, same 40/60/87.5% policy. Negative months are shown, not hidden. ₹ is HYPOTHETICAL (depends on assumed confirmation and prepaid effects).</p></div>
<div class="card"><div style="overflow-x:auto"><table class="cmp"><thead><tr><th>Month</th><th class=num>Trained on</th><th class=num>ROC-AUC</th><th class=num>Flagged</th><th class=num>Conservative</th><th class=num>Base</th><th class=num>Optimistic</th></tr></thead><tbody>{wf_rows}</tbody></table></div>
<p class="h" style="margin-top:var(--sp-3)">{e(wf['C_verdict'])}</p></div>
</section>

<section id="quality" aria-labelledby="h-q">
<div class="sec-h"><h2 id="h-q">Model quality</h2><p>September, measured: {bt['test']['orders']} orders, {bt['test']['rto_orders']} RTO.</p></div>
<div class="grid g-q">
 <div class="card kpi"><div class="l">ROC-AUC · PR-AUC {tip("ROC-AUC: how often a returned order scores higher than a delivered one (0.5 = coin flip). PR-AUC: precision across cut-offs; compare it with the base rate.")}</div><div class="v">{bt['model']['test_auc']:.3f} · {sm['pr_auc_average_precision']:.3f}</div>
 <div class="h">PR-AUC vs {sm['base_rate']:.3f} for a random ranking. Brier {sm['brier']:.3f} (vs {sm['brier_if_always_base_rate']:.3f} always-average). Majority-class accuracy {sm['majority_class_accuracy']:.1%} is context only.</div></div>
 <div class="card"><div class="l" style="font-size:var(--fs-sm);color:var(--text-2);margin-bottom:var(--sp-2)">Predicted vs actual RTO by risk bucket</div><table class="mini"><thead><tr><th>Risk</th><th class=num>Orders</th><th class=num>Pred.</th><th class=num>Actual</th></tr></thead><tbody>{btab}</tbody></table></div>
 <div class="card cal-card"><div class="cal" aria-label="Calibration chart">{svg or '<div class="empty-state">Calibration chart not generated yet.</div>'}</div></div>
</div>
</section>

<section id="orders-sec" aria-labelledby="h-o">
<div class="sec-h"><h2 id="h-o">Orders on the latest day in data ({day:%d %b %Y}) and why</h2><p>Click a column to sort. Filter by action or search order ID, customer, city or reason.</p></div>
<div class="tools"><input id="q" type="search" placeholder="Search order ID, city, reason…" aria-label="Search orders">{chips}<span id="count" class="count" aria-live="polite"></span></div>
<div class="tbl"><table id="orders"><thead><tr>
<th data-key="id"><button>Order</button></th><th>Customer</th><th data-key="city"><button>City</button></th><th class=num data-key="value" data-type="num"><button>Value</button></th>
<th class=num data-key="risk" data-type="num"><button>Risk</button></th><th data-key="act" data-type="num"><button>Action</button></th><th>Why</th></tr></thead>
<tbody>{table_body}</tbody></table><div id="empty" class="empty-state" hidden>No orders match this filter.</div></div>
</section>
</main>
<footer><div class="wrap">
<p><b>Measured</b> = counted from the CSV. <b>Estimated</b> = needs an assumption about what WhatsApp/prepaid would have changed, which the historical data cannot show; a 2–4 week pilot replaces these.</p>
<p>Base assumptions (config/rules.csv): WhatsApp confirmation stops {R['confirm_catches_rto_share']:.0%} of would-be RTOs and loses {R['confirm_genuine_loss_share']:.0%} of genuine buyers; {R['prepaid_takeup_if_baseline_delivered']:.0%} of would-be-delivered and {R['prepaid_takeup_if_baseline_rto']:.0%} of would-be-RTO buyers take the ₹{R['prepaid_discount_rupees']} prepaid offer; no future value is added for first-time customers (₹{R['assumed_future_contribution_first_time_rupees']}). No reply after reminder + 24h → manual ops review (call, then ship or cancel), never auto-cancel ({R['no_reply_action_confirm']} in rules.csv).</p>
<p>Data is a ~2,000-order sample, so the latest day in data has {total} orders, not the ~55 a real day has. Generated {dt.datetime.now():%d %b %Y %H:%M} IST · design spec: docs/DESIGN.md</p>
</div></footer>
<script>{JS}</script></body></html>"""
