#!/usr/bin/env python3
"""
update_dashboard.py — Forecast Q2 2026 MX Sales
Fetches live data from HubSpot API and generates index.html.

Usage:
    HUBSPOT_TOKEN=pat-na1-xxx python3 update_dashboard.py
"""

import os, sys, json, math, datetime, requests

# ─── Configuration ────────────────────────────────────────────────────────────

TOKEN = os.environ.get("HUBSPOT_TOKEN", "")
if not TOKEN:
    sys.exit("ERROR: Set HUBSPOT_TOKEN environment variable")

PORTAL_ID   = "19835492"
PIPELINE_ID = "4022877"

STAGE_NAMES = {
    "213223445": "Discovery",
    "13516851":  "Qualified",
    "108155261": "Nurturing",
    "13510788":  "Negotiation",
    "13516852":  "RA&D",
    "13510790":  "Validación Interna",
    "13516853":  "Close Won",
    "13516854":  "Closed Lost",
}

NURTURING       = "108155261"
CLOSED_LOST     = "13516854"
VERBAL_WIN      = {"13516852", "13510790"}
PIPELINE_STAGES = {"213223445", "13516851", "13510788"}
CLOSE_WON       = "13516853"

QUOTAS = {
    "Agustín Merli":      {"quota": 12000, "team": "Enterprise", "initials": "AM", "id": "v-agus"},
    "Jorge Cervera":      {"quota": 15000, "team": "Enterprise", "initials": "JC", "id": "v-jorge"},
    "Fernando Mena":      {"quota": 12000, "team": "Enterprise", "initials": "FM", "id": "v-fer"},
    "Juan Monte de Oca":  {"quota": 10000, "team": "Enterprise", "initials": "JM", "id": "v-juan"},
    "Tomas Glazman":      {"quota": 10000, "team": "Enterprise", "initials": "TG", "id": "v-tomas"},
    "Florencia Lara":     {"quota":  7000, "team": "Territorio",  "initials": "FL", "id": "v-flor"},
    "Patricio Fernández": {"quota":  8000, "team": "Territorio",  "initials": "PF", "id": "v-pato"},
    "Gilberto Vázquez":   {"quota":  8000, "team": "Territorio",  "initials": "GV", "id": "v-gil"},
    "Andrea Teele Vera":  {"quota":  4000, "team": "Territorio",  "initials": "AT", "id": "v-andrea"},
    "Sergio Ruiseñor":    {"quota": 10000, "team": "Territorio",  "initials": "SR", "id": "v-sergio"},
    "Mariel Alejos":      {"quota":  6000, "team": "Territorio",  "initials": "MA", "id": "v-mariel"},
}

EXCLUDED_VENDORS = {
    "Tomás García", "Val Sánchez", "Eloy Becerril", "Ana Cuevas",
    "Kin Carrera", "Pablo Bringas", "Jessica Rosas", "Tomas Estruga", "Manon Fabre",
    "Valeria Aranda", "Tobías Savich", "Karim Flores", "Oscar Espinosa", "Cris Hernandez",
}

# Deals cerrados en Q1 que no deben contarse en Q2
EXCLUDED_DEALS = {"53886975061", "58368934155"}   # Pizza Hut, ROLEX

ENT_GOAL        = 51000
TER_GOAL        = 44000
FORECAST_TARGET = 190000

ENT_NAMES = ["Agustín Merli", "Jorge Cervera", "Fernando Mena", "Juan Monte de Oca", "Tomas Glazman"]
TER_NAMES = ["Florencia Lara", "Patricio Fernández", "Gilberto Vázquez",
             "Andrea Teele Vera", "Sergio Ruiseñor", "Mariel Alejos"]

WEEK_EPOCH = datetime.date(2025, 12, 29)

ORIGIN_MAP = {
    "Inbound":              "Inbound",
    "Ventas_Prospeccion":   "Ventas Prospección",
    "VENTAS Prospección":   "Ventas Prospección",
    "VENTAS_PROSPECCION":   "Ventas Prospección",
    "Outbound_A8":          "Outbound A8",
    "WhatsApp_Chat":        "WhatsApp Chat",
    "WhatsApp Chat":        "WhatsApp Chat",
    "Por_Definir":          "Por Definir",
    "Por Definir":          "Por Definir",
}

# ─── HubSpot API ──────────────────────────────────────────────────────────────

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def hs_get(path, params=None):
    r = requests.get(f"https://api.hubapi.com{path}", headers=HEADERS,
                     params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def hs_search_all(filters, properties):
    results, after = [], None
    while True:
        body = {
            "filterGroups": [{"filters": filters}],
            "properties": properties,
            "limit": 100,
        }
        if after:
            body["after"] = after
        r = requests.post("https://api.hubapi.com/crm/v3/objects/deals/search",
                          headers=HEADERS, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        results.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return results

# Canonical name corrections — maps exact HubSpot name → display name used in QUOTAS/EXCLUDED_VENDORS
# Verified against HubSpot owners API on 2026-04-06
NAME_CORRECTIONS = {
    # ── QUOTAS members ──────────────────────────────────────────────────────
    "Agustin Merli":              "Agustín Merli",        # HubSpot strips accent
    "Juan Monte de oca":          "Juan Monte de Oca",    # HubSpot uses lowercase 'o'
    "Gilberto Vazquez Garza":     "Gilberto Vázquez",     # HubSpot adds extra surname + no accent
    "Gilberto Vazquez":           "Gilberto Vázquez",     # fallback without accent
    "Sergio Ruiseñor Altamirano": "Sergio Ruiseñor",      # HubSpot adds extra surname
    "Sergio Ruisenor Altamirano": "Sergio Ruiseñor",      # fallback without accent
    "Sergio Ruisenor":            "Sergio Ruiseñor",      # fallback
    "Mariel Alejos Polanco":      "Mariel Alejos",        # HubSpot adds extra surname
    "Patricio Fernandez":         "Patricio Fernández",   # fallback without accent
    "Tobias Savich":              "Tobías Savich",        # fallback without accent
    # ── Excluded vendors (normalize so exclusion list matches) ────────────
    "Tomás Garcia Estebarena":    "Tomás García",         # normalize to EXCLUDED_VENDORS key
    "Tomas Garcia Estebarena":    "Tomás García",
    "Ana Cuevas García Margain":  "Ana Cuevas",
    "Ana Cuevas Garcia Margain":  "Ana Cuevas",
    "Jessica Paola Rosas Castillo": "Jessica Rosas",
    "Karim Fabian Flores Zamora": "Karim Flores",
    "Cristian Hernández":         "Cris Hernandez",
    "Cristian Hernandez":         "Cris Hernandez",
}

def normalize_name(name):
    return NAME_CORRECTIONS.get(name, name)

def fetch_owners():
    owners, after = {}, None
    while True:
        params = {"limit": 100, "archived": "false"}
        if after:
            params["after"] = after
        data = hs_get("/crm/v3/owners", params)
        for o in data.get("results", []):
            name = f"{o.get('firstName', '')} {o.get('lastName', '')}".strip()
            owners[str(o["id"])] = normalize_name(name)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return owners

# ─── Date/Week helpers ─────────────────────────────────────────────────────────

def ms_to_date(val):
    """Convert HubSpot date value to YYYY-MM-DD string.
    HubSpot returns dates as either:
      - Unix timestamp in ms: "1746057600000"
      - ISO 8601 string:      "2026-04-30T00:00:00.000Z"
    """
    if not val:
        return ""
    try:
        s = str(val).strip()
        if s.isdigit():
            # Millisecond timestamp
            return datetime.datetime.utcfromtimestamp(int(s) / 1000).strftime("%Y-%m-%d")
        # ISO date string — just take the first 10 chars (YYYY-MM-DD)
        return s[:10]
    except Exception:
        return ""

def week_of(date_str):
    if not date_str:
        return -1
    try:
        d = datetime.date.fromisoformat(date_str[:10])
        delta = (d - WEEK_EPOCH).days
        return delta // 7 if delta >= 0 else -1
    except Exception:
        return -1

def week_label(wn):
    start = WEEK_EPOCH + datetime.timedelta(weeks=wn)
    end   = start + datetime.timedelta(days=6)
    return f"Sem {wn + 1} · {start.strftime('%d/%m')}–{end.strftime('%d/%m')}"

def month_of(date_str):
    if not date_str:
        return "—"
    try:
        m = datetime.date.fromisoformat(date_str[:10]).month
        return {4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio"}.get(m, "—")
    except Exception:
        return "—"

def days_ago(date_str):
    if not date_str:
        return 9999
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(date_str[:10])).days
    except Exception:
        return 9999

def origin_label(raw):
    if not raw:
        return "Sin datos"
    return ORIGIN_MAP.get(raw, raw.replace("_", " "))

# ─── Risk scoring ──────────────────────────────────────────────────────────────

def risk_label(last_contact, next_activity, amount):
    score = 0
    d = days_ago(last_contact)
    if d > 30:
        score += 40
    elif d > 14:
        score += 20
    elif d > 7:
        score += 10
    if not next_activity:
        score += 30
    if amount > 20000:
        score += 10
    if score >= 60:
        return "high"
    if score >= 30:
        return "med"
    return "low"

# ─── Formatting helpers ────────────────────────────────────────────────────────

def usd(n):
    return f"${int(n):,}" if n else "$0"

def pct(n, d):
    if not d:
        return 0.0
    return round(n / d * 100, 1)

def bw(n, d):
    return min(100, pct(n, d))

def heat_class(n, max_v):
    if n == 0 or max_v == 0:
        return "c0"
    idx = min(9, max(1, math.ceil(n / max_v * 9)))
    return f"c{idx}"

def contact_info(date_str):
    d = days_ago(date_str)
    if d == 9999:
        return "contact-danger", "Sin contacto"
    if d > 30:
        return "contact-danger", f"{d}d"
    if d > 14:
        return "contact-warn", f"{d}d"
    return "contact-ok", f"{d}d"

RISK_CSS = {"high": "risk-high", "med": "risk-med", "low": "risk-low"}
RISK_LBL = {"high": "Alto", "med": "Medio", "low": "Bajo"}

def stage_badge_html(stage_id, stage_name):
    if stage_id in VERBAL_WIN:
        return '<span class="badge badge-vw">Verbal Win</span>'
    STAGE_COLORS = {
        "213223445": ("#0052cc20", "#0052cc", "#0052cc40"),
        "13516851":  ("#36b37e20", "#36b37e", "#36b37e40"),
        "13510788":  ("#ff991f20", "#ff991f", "#ff991f40"),
        "13516853":  ("#36b37e20", "#00875a", "#36b37e40"),
    }
    bg, fg, br = STAGE_COLORS.get(stage_id, ("#6554c020", "#6554c0", "#6554c040"))
    sn = stage_name or stage_id or "—"
    return (f'<span class="badge badge-stage" '
            f'style="background:{bg};color:{fg};border:1px solid {br}">{sn}</span>')

def month_badge_html(month):
    cls = {"Abril": "badge-abril", "Mayo": "badge-mayo", "Junio": "badge-junio", "Julio": "badge-julio"}.get(month, "")
    return f'<span class="badge {cls}">{month}</span>' if cls else month

# ─── Data processing ───────────────────────────────────────────────────────────

def process_data(owners, raw_q2, raw_new):
    # ── Q2 deals
    deals = []
    for d in raw_q2:
        if str(d.get("id", "")) in EXCLUDED_DEALS:
            continue
        p    = d.get("properties", {})
        sid  = p.get("dealstage", "")
        if sid in (NURTURING, CLOSED_LOST):
            continue
        amt     = float(p.get("amount") or 0)
        # Skip Close Won deals with $0 — they are administrative/duplicate entries
        if sid == CLOSE_WON and amt == 0:
            continue
        owner   = owners.get(str(p.get("hubspot_owner_id", "")), "Desconocido")
        cd      = ms_to_date(p.get("closedate"))
        lc      = ms_to_date(p.get("notes_last_contacted"))
        na      = ms_to_date(p.get("hs_next_activity_date"))
        deals.append({
            "id": d["id"], "name": p.get("dealname", "—"),
            "amount": amt, "close_date": cd, "month": month_of(cd),
            "stage_id": sid, "stage": STAGE_NAMES.get(sid, sid or "—"),
            "owner": owner, "last_contact": lc, "next_activity": na,
            "risk": risk_label(lc, na, amt),
            "origen": origin_label(p.get("origen") or ""),
        })
    deals.sort(key=lambda d: (d.get("amount") or 0), reverse=True)

    vw_deals   = [d for d in deals if d["stage_id"] in VERBAL_WIN]
    pipe_deals = [d for d in deals if d["stage_id"] in PIPELINE_STAGES]
    cw_deals   = [d for d in deals if d["stage_id"] == CLOSE_WON]
    vw_t       = sum(d["amount"] for d in vw_deals)
    pipe_t     = sum(d["amount"] for d in pipe_deals)
    cw_t       = sum(d["amount"] for d in cw_deals)
    forecast   = vw_t + pipe_t + cw_t

    months_data = {m: {"vw": 0, "pipe": 0, "cw": 0, "count": 0}
                   for m in ["Abril", "Mayo", "Junio", "Julio"]}
    for d in deals:
        m = d["month"]
        if m not in months_data:
            continue
        months_data[m]["count"] += 1
        if d["stage_id"] in VERBAL_WIN:
            months_data[m]["vw"] += d["amount"]
        elif d["stage_id"] in PIPELINE_STAGES:
            months_data[m]["pipe"] += d["amount"]
        elif d["stage_id"] == CLOSE_WON:
            months_data[m]["cw"] += d["amount"]

    # ── Vendor aggregates
    vendors = {name: {"vw": 0, "pipeline": 0, "cw": 0, "deals": []} for name in QUOTAS}
    for d in deals:
        owner = d["owner"]
        if owner not in vendors and owner not in EXCLUDED_VENDORS:
            vendors[owner] = {"vw": 0, "pipeline": 0, "cw": 0, "deals": []}
        if owner in vendors:
            vendors[owner]["deals"].append(d)
            if d["stage_id"] in VERBAL_WIN:
                vendors[owner]["vw"] += d["amount"]
            elif d["stage_id"] in PIPELINE_STAGES:
                vendors[owner]["pipeline"] += d["amount"]
            elif d["stage_id"] == CLOSE_WON:
                vendors[owner]["cw"] += d["amount"]

    def sort_key(n):
        q     = QUOTAS.get(n, {})
        total = vendors[n]["vw"] + vendors[n]["pipeline"] + vendors[n]["cw"]
        return (0 if q.get("team") == "Enterprise" else 1, -total)

    sorted_vendors = [n for n in sorted(vendors.keys(), key=sort_key) if n in QUOTAS]

    team_agg = lambda names, key: sum(vendors[n][key] for n in names if n in vendors)
    ent = {k: team_agg(ENT_NAMES, k) for k in ["vw", "pipeline", "cw"]}
    ter = {k: team_agg(TER_NAMES, k) for k in ["vw", "pipeline", "cw"]}

    # ── New deals
    ng_deals = []
    for d in raw_new:
        p    = d.get("properties", {})
        owner = owners.get(str(p.get("hubspot_owner_id", "")), "Desconocido")
        if owner in EXCLUDED_VENDORS:
            continue
        sid = p.get("dealstage", "")
        cd  = ms_to_date(p.get("createdate"))
        src = p.get("origen") or ""
        ng_deals.append({
            "n": p.get("dealname", "—"), "o": owner,
            "s": STAGE_NAMES.get(sid, sid or "—"),
            "src": src, "d": cd, "wn": week_of(cd),
        })
    ng_deals.sort(key=lambda d: d["d"])

    raw_wns      = sorted(set(d["wn"] for d in ng_deals if d["wn"] >= 0))
    sorted_weeks = [week_label(wn) for wn in raw_wns]
    wn_idx       = {wn: i for i, wn in enumerate(raw_wns)}
    for d in ng_deals:
        d["wn"] = wn_idx.get(d["wn"], -1)

    vendor_week = {name: {} for name in QUOTAS}
    for d in ng_deals:
        o = d["o"]
        if o in vendor_week and d["wn"] >= 0:
            vendor_week[o][d["wn"]] = vendor_week[o].get(d["wn"], 0) + 1

    week_totals = {}
    for d in ng_deals:
        if d["wn"] >= 0:
            week_totals[d["wn"]] = week_totals.get(d["wn"], 0) + 1

    max_wk = max((max(v.values()) for v in vendor_week.values() if v), default=1)

    src_counts = {}
    for d in ng_deals:
        lbl = origin_label(d["src"])
        src_counts[lbl] = src_counts.get(lbl, 0) + 1
    src_sorted = sorted(src_counts.items(), key=lambda x: -x[1])
    src_max    = max(src_counts.values()) if src_counts else 1

    return {
        "deals": deals, "vw_deals": vw_deals, "pipe_deals": pipe_deals, "cw_deals": cw_deals,
        "vw_t": vw_t, "pipe_t": pipe_t, "cw_t": cw_t, "forecast": forecast,
        "months_data": months_data,
        "vendors": vendors, "sorted_vendors": sorted_vendors,
        "ent": ent, "ter": ter,
        "ng_deals": ng_deals, "sorted_weeks": sorted_weeks,
        "vendor_week": vendor_week, "week_totals": week_totals, "max_wk": max_wk,
        "src_sorted": src_sorted, "src_max": src_max,
    }

# ─── HTML generation ──────────────────────────────────────────────────────────

CSS = """
:root {
  --blue:#0052cc; --blue-lt:#e9f0ff; --teal:#00b8d9; --green:#36b37e;
  --green-dk:#00875a; --purple:#6554c0; --purple-lt:#f3f0ff;
  --orange:#ff991f; --red:#ff5630; --red-dk:#bf2600;
  --bg:#f4f5f7; --card:#fff; --text:#172b4d; --muted:#6b778c; --border:#dfe1e6;
  --radius:10px; --shadow:0 1px 4px rgba(0,0,0,.08);
}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;}
.header{background:linear-gradient(135deg,#0052cc,#0747a6);color:#fff;padding:20px 32px;display:flex;justify-content:space-between;align-items:center;}
.header h1{font-size:1.35rem;font-weight:700;}
.header-meta{font-size:.78rem;opacity:.75;margin-top:3px;}
.header-right{text-align:right;font-size:.78rem;opacity:.8;}
.tab-bar{background:#fff;border-bottom:2px solid var(--border);padding:0 32px;display:flex;position:sticky;top:0;z-index:50;box-shadow:0 1px 4px rgba(0,0,0,.05);}
.tab-btn{padding:13px 20px;font-size:.88rem;font-weight:600;color:var(--muted);border:none;background:none;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-2px;transition:color .15s,border-color .15s;}
.tab-btn:hover{color:var(--blue);}
.tab-btn.active{color:var(--blue);border-bottom-color:var(--blue);}
.page{display:none;max-width:1300px;margin:0 auto;padding:20px 32px 40px;}
.page.active{display:block;}
.card{background:var(--card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow);}
.card-pad{padding:18px 22px;}
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px;}
.kpi{background:var(--card);border-radius:var(--radius);border:1px solid var(--border);padding:16px 20px;box-shadow:var(--shadow);}
.kpi-label{font-size:.68rem;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);font-weight:700;margin-bottom:6px;}
.kpi-value{font-size:1.65rem;font-weight:700;line-height:1.1;}
.kpi-sub{font-size:.72rem;color:var(--muted);margin-top:5px;}
.kpi.k-blue{border-top:3px solid var(--blue);}
.kpi.k-purple{border-top:3px solid var(--purple);}
.kpi.k-teal{border-top:3px solid var(--teal);}
.kpi.k-orange{border-top:3px solid var(--orange);}
.kpi.k-red{border-top:3px solid var(--red);}
.progress-card{background:var(--card);border-radius:var(--radius);border:1px solid var(--border);padding:18px 22px;margin-bottom:18px;box-shadow:var(--shadow);display:grid;grid-template-columns:1fr 1fr;gap:28px;}
.prog-label{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:6px;}
.prog-val{font-size:1rem;font-weight:700;margin-bottom:6px;}
.prog-bar{height:10px;background:#eee;border-radius:6px;overflow:hidden;margin-bottom:4px;}
.prog-fill{height:100%;border-radius:6px;}
.prog-meta{display:flex;justify-content:space-between;font-size:.68rem;color:var(--muted);}
.prog-stacked{display:flex;height:10px;border-radius:6px;overflow:hidden;background:#eee;margin-bottom:4px;gap:2px;}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px;}
.three-col{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:18px;}
.team-card{background:var(--card);border-radius:var(--radius);border:1px solid var(--border);padding:16px 20px;box-shadow:var(--shadow);}
.team-name{font-size:1rem;font-weight:700;margin-bottom:12px;}
.team-row{margin-bottom:10px;}
.team-row-header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px;}
.team-row-label{font-size:.7rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.5px;}
.team-row-val{font-size:.82rem;font-weight:700;}
.month-card{background:var(--card);border-radius:var(--radius);border:1px solid var(--border);padding:14px 18px;box-shadow:var(--shadow);}
.month-name{font-size:.9rem;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:8px;}
.month-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;}
.month-stat{display:flex;justify-content:space-between;font-size:.75rem;color:var(--muted);margin-bottom:3px;}
.month-stat strong{color:var(--text);}
.table-wrap{background:var(--card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow);overflow:hidden;}
.table-toolbar{padding:14px 18px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);gap:10px;flex-wrap:wrap;}
.table-toolbar h3{font-size:.9rem;font-weight:700;}
.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
.search-input{padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:.8rem;width:180px;}
.search-input:focus{outline:none;border-color:var(--blue);}
.filter-select{padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:.8rem;background:#fff;cursor:pointer;}
.filter-pills{display:flex;gap:6px;flex-wrap:wrap;}
.pill{padding:4px 12px;border-radius:20px;border:1px solid var(--border);background:#fff;font-size:.75rem;font-weight:600;cursor:pointer;transition:.1s;}
.pill:hover,.pill.on{background:var(--blue);color:#fff;border-color:var(--blue);}
table{width:100%;border-collapse:collapse;}
th{background:#f8f9fc;padding:9px 12px;font-size:.68rem;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:700;border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer;}
th:hover{color:var(--blue);}
td{padding:9px 12px;font-size:.82rem;border-bottom:1px solid var(--border);vertical-align:middle;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:#fafbff;}
tr.hidden{display:none;}
.deal-link{color:var(--blue);text-decoration:none;font-weight:500;}
.deal-link:hover{text-decoration:underline;}
.na{color:#bbb;font-style:italic;}
.na-cell{font-size:.78rem;color:var(--muted);}
.small-cell{font-size:.75rem;color:var(--muted);max-width:140px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.table-footer{padding:10px 14px;background:#f8f9fc;border-top:1px solid var(--border);font-size:.73rem;color:var(--muted);}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:.7rem;font-weight:600;}
.badge-stage{white-space:nowrap;}
.badge-vw{background:#f3f0ff;color:#5243aa;border:1px solid #c0b3f5;font-weight:700;}
.badge-abril{background:#e9f0ff;color:#0052cc;}
.badge-mayo{background:#e3fcef;color:#006644;}
.badge-junio{background:#fff4e5;color:#974900;}
.badge-julio{background:#f3e8ff;color:#6b21a8;}
.risk-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.72rem;font-weight:700;}
.risk-high{background:#ffe9e4;color:var(--red-dk);}
.risk-med{background:#fff4e5;color:#974900;}
.risk-low{background:#e3fcef;color:#006644;}
.contact-ok{color:var(--blue);font-size:.78rem;}
.contact-warn{color:#974900;font-weight:600;font-size:.78rem;}
.contact-danger{color:var(--red-dk);font-weight:700;font-size:.78rem;}
.sidebar-item{display:flex;align-items:center;gap:9px;width:100%;padding:10px 14px;border:none;background:none;cursor:pointer;border-bottom:1px solid var(--border);transition:.1s;color:var(--text);}
.sidebar-item:hover{background:#f4f5f7;}
.sidebar-item.active{background:var(--blue-lt);color:var(--blue);font-weight:600;}
.sidebar-item:last-child{border-bottom:none;}
.vendor-layout{display:flex;gap:16px;align-items:flex-start;}
.vendor-sidebar{width:220px;flex-shrink:0;background:var(--card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow);overflow-y:auto;max-height:calc(100vh - 140px);position:sticky;top:70px;}
.vendor-content{flex:1;min-width:0;}
.section-title{font-size:.92rem;font-weight:700;color:var(--text);margin-bottom:2px}
.section-sub{font-size:.76rem;color:var(--muted);margin-bottom:14px}
.src-chart{display:flex;flex-direction:column;gap:9px}
.src-row{display:grid;grid-template-columns:150px 1fr 72px;align-items:center;gap:10px}
.src-label{font-size:.78rem;color:var(--text)}
.src-bar-wrap{height:10px;background:var(--border);border-radius:5px;overflow:hidden}
.src-bar{height:100%;border-radius:5px}
.src-count{font-size:.8rem;font-weight:600;color:var(--text)}
.src-pct{font-size:.72rem;font-weight:400;color:var(--muted)}
.trend-chart{display:flex;align-items:flex-end;gap:3px;height:150px;padding-top:20px}
.trend-col{display:flex;flex-direction:column;align-items:center;flex:1;height:100%}
.trend-val{font-size:.65rem;font-weight:700;color:var(--blue);margin-bottom:3px}
.trend-bar-wrap{flex:1;width:100%;display:flex;align-items:flex-end}
.trend-bar{width:100%;background:var(--blue);border-radius:3px 3px 0 0;min-height:3px}
.trend-lbl{font-size:.57rem;color:var(--muted);margin-top:4px;text-align:center;line-height:1.2;white-space:nowrap}
.vendor-matrix{width:100%;border-collapse:collapse;font-size:.78rem}
.vendor-matrix thead tr{background:#f4f5f7}
.vendor-matrix th{padding:7px 5px;text-align:center;font-weight:600;color:var(--muted);border:1px solid var(--border);white-space:nowrap;font-size:.72rem}
.vendor-matrix td{padding:5px 6px;border:1px solid #eee;text-align:center}
.vendor-matrix .wk-th{min-width:52px}
.vname{text-align:left!important;font-weight:500;white-space:nowrap;padding-left:10px!important}
.vtotal{text-align:center!important;font-weight:700;color:var(--blue)}
.vrow:hover td{background:rgba(0,82,204,.04)}
.vrow-quota .vname{color:var(--blue)}
.quota-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--blue);margin-right:5px;vertical-align:middle}
.wk-cell{font-size:.75rem;font-weight:600;cursor:default}
.c0{background:#fff;color:transparent}
.c1{background:#e9f0ff;color:#0052cc}
.c2{background:#d4e2ff;color:#0052cc}
.c3{background:#b3ccff;color:#0052cc}
.c4{background:#8ab3ff;color:#0047b3}
.c5{background:#5c97ff;color:#fff}
.c6{background:#3b7eff;color:#fff}
.c7{background:#1a5fd4;color:#fff}
.c8{background:#0747a6;color:#fff}
.c9{background:#03306e;color:#fff}
.vendor-matrix tr.hidden{display:none}
.detalle-layout{display:flex;gap:0;align-items:flex-start;min-height:calc(100vh - 160px);}
.detalle-sidebar{width:190px;flex-shrink:0;background:var(--card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow);overflow-y:auto;max-height:calc(100vh - 160px);position:sticky;top:70px;margin-right:20px;}
.detalle-sidebar-title{padding:12px 14px 8px;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);border-bottom:1px solid var(--border);}
.week-sidebar-btn{display:block;width:100%;padding:10px 14px;border:none;background:none;cursor:pointer;text-align:left;font-size:.78rem;color:var(--muted);border-bottom:1px solid var(--border);transition:.12s;line-height:1.3;}
.week-sidebar-btn:last-child{border-bottom:none;}
.week-sidebar-btn:hover{background:#f4f5f7;color:var(--text);}
.week-sidebar-btn.active{background:var(--blue-lt);color:var(--blue);font-weight:700;border-left:3px solid var(--blue);}
.detalle-content{flex:1;min-width:0;}
#week-deal-table{width:100%;border-collapse:collapse;font-size:.82rem;}
#week-deal-table th{padding:9px 12px;background:#f4f5f7;border:1px solid var(--border);font-weight:600;color:var(--muted);font-size:.76rem;text-align:left;}
#week-deal-table td{padding:8px 12px;border:1px solid #eee;vertical-align:top;}
#week-deal-table tr:hover td{background:rgba(0,82,204,.03);}
.stage-pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.72rem;font-weight:600;}
.origen-tag{font-size:.75rem;color:var(--muted);}
/* === Mejoras UX: Pestaña Negocios === */
.neg-card-header{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:10px;flex-wrap:wrap}}
.neg-card-header .section-title{{margin-bottom:2px}}
.neg-card-header .section-sub{{margin-bottom:0}}
.seg-control{{display:inline-flex;background:#f4f5f7;border:1px solid var(--border);border-radius:8px;padding:2px;gap:2px}}
.seg-btn{{padding:5px 12px;font-size:.72rem;font-weight:600;color:var(--muted);background:transparent;border:none;border-radius:6px;cursor:pointer;transition:.15s;white-space:nowrap}}
.seg-btn:hover{{color:var(--blue)}}
.seg-btn.on{{background:#fff;color:var(--blue);box-shadow:0 1px 2px rgba(0,0,0,.08)}}
.chart-box{{position:relative;height:260px;width:100%}}
.chart-box.tall{{height:300px}}
.chart-summary{{display:flex;gap:14px;margin-top:10px;flex-wrap:wrap;font-size:.72rem;color:var(--muted)}}
.chart-summary strong{{color:var(--text);font-weight:700}}
.channel-legend{{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}}
.channel-chip{{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border:1px solid var(--border);background:#fff;border-radius:20px;font-size:.72rem;font-weight:600;cursor:pointer;transition:.15s;user-select:none;color:var(--text)}}
.channel-chip:hover{{border-color:#aab4c2}}
.channel-chip.off{{opacity:.35;background:#f4f5f7}}
.channel-chip .dot{{width:9px;height:9px;border-radius:50%;flex-shrink:0}}
.channel-actions{{display:flex;gap:6px}}
.mini-btn{{padding:4px 10px;font-size:.7rem;font-weight:600;color:var(--muted);background:#fff;border:1px solid var(--border);border-radius:6px;cursor:pointer;transition:.1s}}
.mini-btn:hover{{color:var(--blue);border-color:var(--blue)}}
/* Vendor matrix mejorada */
.vendor-matrix-wrap{{position:relative;max-height:70vh;overflow:auto;border-top:1px solid var(--border)}}
.vendor-matrix thead th{{position:sticky;top:0;background:#f4f5f7;z-index:3;cursor:pointer;user-select:none;transition:background .15s}}
.vendor-matrix thead th:hover{{background:#e9edf3;color:var(--blue)}}
.vendor-matrix th.vname,.vendor-matrix td.vname{{position:sticky;left:0;background:#fff;z-index:2;text-align:left}}
.vendor-matrix thead th.vname{{background:#f4f5f7;z-index:4}}
.vrow:hover td.vname{{background:#fafbff}}
.vendor-matrix th.sorted-asc::after{{content:" ▲";color:var(--blue);font-size:.68rem}}
.vendor-matrix th.sorted-desc::after{{content:" ▼";color:var(--blue);font-size:.68rem}}
.vendor-matrix tfoot td{{font-weight:700;background:#f8f9fc;border-top:2px solid var(--border);color:var(--muted);position:sticky;bottom:0;z-index:2}}
.vendor-matrix .wk-cell{{min-width:52px;transition:transform .1s}}
.vendor-matrix .wk-cell:hover{{outline:2px solid var(--blue);outline-offset:-2px}}
.heat-legend{{display:flex;align-items:center;gap:6px;font-size:.7rem;color:var(--muted)}}
.heat-scale{{display:flex;border-radius:4px;overflow:hidden;border:1px solid var(--border)}}
.heat-scale span{{display:inline-block;width:18px;height:14px}}
.vtotal-cell{{background:#f0f4ff!important;color:var(--blue);font-weight:800!important;text-align:center!important}}
.rank-badge{{display:inline-block;min-width:20px;padding:1px 6px;margin-right:6px;border-radius:10px;background:#f0f4ff;color:var(--blue);font-size:.66rem;font-weight:700;text-align:center}}
.rank-badge.top{{background:linear-gradient(135deg,#ffd24d,#ff991f);color:#fff}}
.rank-badge.top2{{background:#e8ecf5;color:#172b4d}}
.rank-badge.top3{{background:#f4e3c1;color:#974900}}
@media(max-width:900px){
  .kpi-grid{grid-template-columns:repeat(2,1fr);}
  .progress-card,.two-col,.three-col{grid-template-columns:1fr;}
  .page{padding:14px 16px 32px;}
  .header{padding:16px;}
  .tab-bar{padding:0 16px;}
}
"""

STATIC_JS = r"""
function showTab(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  document.querySelector('[onclick="showTab(\'' + id + '\')"]').classList.add('active');
}

function showVendor(vid, btn) {
  document.querySelectorAll('.vendor-section').forEach(s => s.style.display = 'none');
  document.querySelectorAll('.sidebar-item').forEach(b => b.classList.remove('active'));
  document.getElementById(vid).style.display = 'block';
  if (btn) btn.classList.add('active');
}

function filterOverview() {
  const q    = (document.getElementById('search-overview')?.value || '').toLowerCase();
  const own  = document.getElementById('filter-owner')?.value || '';
  const cat  = document.getElementById('filter-cat')?.value || '';
  const risk = document.getElementById('filter-risk')?.value || '';
  document.querySelectorAll('#overview-tbody tr').forEach(tr => {
    const owner = tr.dataset.owner || '';
    const riskD = tr.dataset.risk  || '';
    const catD  = tr.dataset.cat   || '';
    const txt   = tr.textContent.toLowerCase();
    let show = true;
    if (q   && !txt.includes(q))           show = false;
    if (own && owner !== own)               show = false;
    if (cat && !catD.includes(cat))         show = false;
    if (risk) {
      const map = {'Alto':'alto','Medio':'medio','Bajo':'bajo'};
      if (riskD !== (map[risk] || risk).toLowerCase()) show = false;
    }
    tr.classList.toggle('hidden', !show);
  });
}

function filterVendorDeals(tbodyId) {
  const q = (document.getElementById('search-vendor-' + tbodyId)?.value || '').toLowerCase();
  const cat = document.getElementById('filter-vendor-cat-' + tbodyId)?.value || '';
  document.querySelectorAll('#' + tbodyId + ' tr').forEach(tr => {
    const catD = tr.dataset.cat || '';
    const txt  = tr.textContent.toLowerCase();
    let show = true;
    if (q   && !txt.includes(q))   show = false;
    if (cat && !catD.includes(cat)) show = false;
    tr.classList.toggle('hidden', !show);
  });
}

function sortTable(col, tbodyId) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll('tr:not(.hidden)'));
  const dir  = tbody.dataset.sortDir === 'asc' ? -1 : 1;
  tbody.dataset.sortDir = dir === 1 ? 'asc' : 'desc';
  rows.sort((a, b) => {
    const at = a.cells[col]?.textContent.trim() || '';
    const bt = b.cells[col]?.textContent.trim() || '';
    const an = parseFloat(at.replace(/[$,]/g, ''));
    const bn = parseFloat(bt.replace(/[$,]/g, ''));
    if (!isNaN(an) && !isNaN(bn)) return dir * (an - bn);
    return dir * at.localeCompare(bt, 'es');
  });
  rows.forEach(r => tbody.appendChild(r));
}

function filterNegocios() {
  const q = (document.getElementById('filter-negocios-vendor')?.value || '').toLowerCase();
  document.querySelectorAll('.vendor-matrix tbody tr').forEach(tr => {
    const name = (tr.dataset.vendor || '').toLowerCase();
    tr.classList.toggle('hidden', !!q && !name.includes(q));
  });
}

function showWeek(idx, btn) {
  _currentWeekIdx = idx;
  document.querySelectorAll('.week-sidebar-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById('detalle-week-title').textContent = _WEEKS[idx] || '';
  applyDetallFilter();
}

function applyDetallFilter() {
  const vendor = document.getElementById('detalle-filter-vendor')?.value || '';
  let deals = _NG_DEALS.filter(d => d.wn === _currentWeekIdx);
  if (vendor) deals = deals.filter(d => d.o === vendor);

  const ORIGIN_LABELS = {
    "Inbound": "Inbound", "Ventas_Prospeccion": "Ventas Prospección",
    "VENTAS Prospección": "Ventas Prospección", "Outbound_A8": "Outbound A8",
    "WhatsApp_Chat": "WhatsApp Chat", "WhatsApp Chat": "WhatsApp Chat",
    "Por_Definir": "Por Definir", "Por Definir": "Por Definir",
  };
  const STAGE_COLORS = {
    "Discovery":   ["#e9f0ff","#0052cc"],
    "Qualified":   ["#e3fcef","#00875a"],
    "Negotiation": ["#fff4e5","#974900"],
    "RA&D":        ["#f3f0ff","#5243aa"],
    "Validación Interna": ["#f3f0ff","#5243aa"],
    "Close Won":   ["#e3fcef","#006644"],
    "Verbal Win":  ["#f3f0ff","#5243aa"],
    "Nurturing":   ["#f4f5f7","#6b778c"],
  };

  const tbody = document.getElementById('week-deal-tbody');
  const count = document.getElementById('detalle-deal-count');
  if (!tbody) return;

  if (!deals.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:24px">Sin negocios para esta semana</td></tr>';
    if (count) count.textContent = '0 negocios';
    return;
  }

  const srcLbl = s => ORIGIN_LABELS[s] || (s ? s.replace(/_/g,' ') : 'Sin datos');
  const stgHtml = s => {
    const [bg, fg] = STAGE_COLORS[s] || ["#f4f5f7","#6b778c"];
    return `<span class="stage-pill" style="background:${bg};color:${fg}">${s}</span>`;
  };

  tbody.innerHTML = deals.map(d => `
    <tr>
      <td><strong>${d.n}</strong></td>
      <td>${d.o}</td>
      <td>${stgHtml(d.s)}</td>
      <td class="origen-tag">${srcLbl(d.src)}</td>
    </tr>`).join('');
  if (count) count.textContent = deals.length + ' negocio' + (deals.length !== 1 ? 's' : '');
}

/* ════════ NEGOCIOS · charts + matriz ordenable ════════ */
const ORIGIN_LABEL_MAP = {{
  "Inbound":"Inbound","Ventas_Prospeccion":"Ventas Prospección",
  "VENTAS Prospección":"Ventas Prospección","SDR_Prospeccion":"SDR Prospección",
  "Outbound_A8":"Outbound A8","Outbound_ZM":"Outbound ZM",
  "WhatsApp_Chat":"WhatsApp Chat","WhatsApp Chat":"WhatsApp Chat",
  "Referidos":"Referidos","Resellers":"Resellers","Alianzas":"Alianzas",
  "Email_marketing":"Email marketing","Email marketing":"Email marketing",
  "Eventos":"Eventos","Por_Definir":"Por Definir","Por Definir":"Por Definir",
  "":"Sin datos"
}};
const CHANNEL_COLORS = ["#0052cc","#00b8d9","#36b37e","#6554c0","#ff991f","#ff5630","#00875a","#403294","#974900","#5243aa","#0747a6","#6b778c"];
function channelLabel(s){{ return ORIGIN_LABEL_MAP[s] || (s ? s.replace(/_/g,' ') : 'Sin datos'); }}

/* Aggregate _NG_DEALS by granularity. Returns {{buckets:[{{key,label,sortKey}}], byChannel:{{channel:[count...]}}, totals:[count...] }} */
function aggregateDeals(gran){{
  const ymd = d => d;  // already YYYY-MM-DD
  function bucketFor(dateStr){{
    const d = new Date(dateStr + 'T00:00:00');
    if (gran === 'day') {{
      return {{ key: ymd(dateStr), label: d.toLocaleDateString('es-MX',{{day:'2-digit',month:'short'}}), sortKey: dateStr }};
    }}
    if (gran === 'month') {{
      const y = d.getFullYear(); const m = d.getMonth();
      const key = y + '-' + String(m+1).padStart(2,'0');
      const label = d.toLocaleDateString('es-MX',{{month:'short', year:'2-digit'}});
      return {{ key, label, sortKey: key }};
    }}
    // week — ISO-ish: take Monday as start
    const tmp = new Date(d);
    const day = (tmp.getDay() + 6) % 7; // 0 = Mon
    tmp.setDate(tmp.getDate() - day);
    const key = tmp.toISOString().slice(0,10);
    const end = new Date(tmp); end.setDate(end.getDate()+6);
    const fmt = x => String(x.getDate()).padStart(2,'0')+'/'+String(x.getMonth()+1).padStart(2,'0');
    return {{ key, label: fmt(tmp)+'–'+fmt(end), sortKey: key }};
  }}
  const bucketMap = new Map(); // key → {{label, sortKey}}
  const channelBuckets = new Map(); // channel → Map(key → count)
  const totalBuckets = new Map();
  for (const dl of _NG_DEALS){{
    if (!dl.d) continue;
    const b = bucketFor(dl.d);
    if (!bucketMap.has(b.key)) bucketMap.set(b.key, b);
    totalBuckets.set(b.key, (totalBuckets.get(b.key)||0)+1);
    const ch = channelLabel(dl.src);
    if (!channelBuckets.has(ch)) channelBuckets.set(ch, new Map());
    const cm = channelBuckets.get(ch);
    cm.set(b.key, (cm.get(b.key)||0)+1);
  }}
  const buckets = [...bucketMap.values()].sort((a,b)=>a.sortKey.localeCompare(b.sortKey));
  const totals = buckets.map(b => totalBuckets.get(b.key) || 0);
  const byChannel = {{}};
  for (const [ch, cm] of channelBuckets.entries()){{
    byChannel[ch] = buckets.map(b => cm.get(b.key) || 0);
  }}
  return {{ buckets, totals, byChannel }};
}}

/* ── Gráfico: Nuevos negocios en el tiempo ── */
let _trendChart = null;
let _trendGran = 'week';
function renderTrendChart(){{
  const agg = aggregateDeals(_trendGran);
  const ctx = document.getElementById('chartTrend');
  if (!ctx) return;
  const labels = agg.buckets.map(b => b.label);
  const data = agg.totals;
  const total = data.reduce((a,b)=>a+b,0);
  const max = Math.max(...data, 0);
  const avg = data.length ? (total/data.length) : 0;
  const lastLabel = _trendGran === 'day' ? 'hoy' : (_trendGran === 'week' ? 'esta semana' : 'este mes');
  const last = data[data.length-1] || 0;
  const prev = data[data.length-2] || 0;
  const delta = prev ? ((last-prev)/prev*100) : 0;
  const summary = document.getElementById('trendSummary');
  if (summary){{
    const pill = (delta>=0?'▲':'▼') + ' ' + Math.abs(delta).toFixed(0) + '%';
    const color = delta>=0 ? '#006644' : '#bf2600';
    summary.innerHTML =
      `<span>Total período: <strong>${{total}}</strong></span>`+
      `<span>Promedio: <strong>${{avg.toFixed(1)}}</strong></span>`+
      `<span>Pico: <strong>${{max}}</strong></span>`+
      `<span>${{lastLabel}}: <strong>${{last}}</strong> <span style="color:${{color}};font-weight:700">${{prev?pill:''}}</span></span>`;
  }}
  const sub = document.getElementById('trend-sub');
  if (sub) sub.textContent = 'Total de negocios creados por ' + (_trendGran==='day'?'día':(_trendGran==='week'?'semana':'mes')) + ' · ' + total + ' negocios';

  if (_trendChart){{ _trendChart.destroy(); }}
  _trendChart = new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels,
      datasets: [{{
        label: 'Nuevos negocios',
        data,
        backgroundColor: data.map((v,i) => i === data.length-1 ? '#00b8d9' : '#0052cc'),
        borderRadius: 4,
        maxBarThickness: 40
      }}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins:{{
        legend:{{display:false}},
        tooltip:{{ callbacks:{{ label:(c)=>`${{c.parsed.y}} negocios` }} }}
      }},
      scales:{{
        x:{{ grid:{{display:false}}, ticks:{{autoSkip:true, maxRotation:45, minRotation:0, font:{{size:10}}}} }},
        y:{{ beginAtZero:true, ticks:{{precision:0, font:{{size:10}}}}, grid:{{color:'#eee'}} }}
      }}
    }}
  }});
}}
function setTrendGran(g, btn){{
  _trendGran = g;
  document.querySelectorAll('#negocios .seg-control').forEach(sc => {{
    if (sc.querySelector('[onclick^="setTrendGran"]')){{
      sc.querySelectorAll('.seg-btn').forEach(b => b.classList.toggle('on', b === btn));
    }}
  }});
  renderTrendChart();
}}

/* ── Gráfico: Evolución por canal ── */
let _channelChart = null;
let _channelGran = 'week';
let _channelVisible = {{}}; // channel → bool
function renderChannelChart(){{
  const agg = aggregateDeals(_channelGran);
  const ctx = document.getElementById('chartChannels');
  if (!ctx) return;
  const labels = agg.buckets.map(b => b.label);
  // Order channels by total desc for color stability
  const channelTotals = Object.entries(agg.byChannel)
    .map(([ch, arr]) => [ch, arr.reduce((a,b)=>a+b,0)])
    .sort((a,b)=>b[1]-a[1]);
  const channels = channelTotals.map(x => x[0]);
  // Initialize visibility for new channels: default show only top 5 to keep chart legible
  channels.forEach((ch,i) => {{
    if (_channelVisible[ch] === undefined) _channelVisible[ch] = i < 5;
  }});
  const datasets = channels.map((ch, i) => ({{
    label: ch,
    data: agg.byChannel[ch],
    borderColor: CHANNEL_COLORS[i % CHANNEL_COLORS.length],
    backgroundColor: CHANNEL_COLORS[i % CHANNEL_COLORS.length] + '22',
    borderWidth: 2,
    tension: 0.3,
    pointRadius: 2,
    pointHoverRadius: 5,
    hidden: !_channelVisible[ch],
    fill: false
  }}));
  if (_channelChart){{ _channelChart.destroy(); }}
  _channelChart = new Chart(ctx, {{
    type: 'line',
    data: {{ labels, datasets }},
    options: {{
      responsive:true, maintainAspectRatio:false, interaction:{{mode:'index', intersect:false}},
      plugins:{{
        legend:{{display:false}},
        tooltip:{{
          callbacks:{{
            title: (items) => items[0].label,
            label: (c) => c.dataset.label + ': ' + c.parsed.y
          }}
        }}
      }},
      scales:{{
        x:{{ grid:{{display:false}}, ticks:{{autoSkip:true, maxRotation:45, minRotation:0, font:{{size:10}}}} }},
        y:{{ beginAtZero:true, ticks:{{precision:0, font:{{size:10}}}}, grid:{{color:'#eee'}} }}
      }}
    }}
  }});
  // Build legend with toggles
  const legendEl = document.getElementById('channelLegend');
  if (legendEl){{
    legendEl.innerHTML = channels.map((ch, i) => {{
      const color = CHANNEL_COLORS[i % CHANNEL_COLORS.length];
      const total = channelTotals[i][1];
      const off = _channelVisible[ch] ? '' : 'off';
      return `<span class="channel-chip ${{off}}" onclick="toggleChannel('${{ch.replace(/'/g,"\\\'")}}'`, this)"><span class="dot" style="background:${{color}}"></span>${{ch}} <span style="color:var(--muted);font-weight:500">· ${{total}}</span></span>`;
    }}).join('');
  }}
  const sub = document.getElementById('channel-sub');
  if (sub) sub.textContent = 'Evolución por fuente de origen · agrupado por ' + (_channelGran==='day'?'día':(_channelGran==='week'?'semana':'mes'));
}}
function toggleChannel(ch, el){{
  _channelVisible[ch] = !_channelVisible[ch];
  if (el) el.classList.toggle('off', !_channelVisible[ch]);
  if (_channelChart){{
    _channelChart.data.datasets.forEach(ds => {{
      if (ds.label === ch) ds.hidden = !_channelVisible[ch];
    }});
    _channelChart.update();
  }}
}}
function toggleAllChannels(show){{
  Object.keys(_channelVisible).forEach(k => _channelVisible[k] = show);
  renderChannelChart();
}}
function showTopChannels(n){{
  const agg = aggregateDeals(_channelGran);
  const sorted = Object.entries(agg.byChannel)
    .map(([ch, arr]) => [ch, arr.reduce((a,b)=>a+b,0)])
    .sort((a,b)=>b[1]-a[1]);
  Object.keys(_channelVisible).forEach(k => _channelVisible[k] = false);
  sorted.slice(0, n).forEach(([ch]) => _channelVisible[ch] = true);
  renderChannelChart();
}}
function setChannelGran(g, btn){{
  _channelGran = g;
  document.querySelectorAll('#negocios .seg-control').forEach(sc => {{
    if (sc.querySelector('[onclick^="setChannelGran"]')){{
      sc.querySelectorAll('.seg-btn').forEach(b => b.classList.toggle('on', b === btn));
    }}
  }});
  renderChannelChart();
}}

/* ── Vendor matrix: compute data-* attrs, sort, add rank badges ── */
function enhanceVendorMatrix(){{
  const table = document.getElementById('vendor-matrix');
  if (!table) return;
  const rows = [...table.querySelectorAll('tbody tr.vrow')];
  rows.forEach(tr => {{
    const cells = [...tr.querySelectorAll('.wk-cell')];
    const weekly = cells.map(c => {{
      const n = parseInt((c.textContent||'').trim(), 10);
      return isNaN(n) ? 0 : n;
    }});
    const total = weekly.reduce((a,b)=>a+b,0);
    const last = weekly[weekly.length-1] || 0;
    const active = weekly.filter(v => v>0).length || 1;
    const avg = total / (weekly.length || 1);
    // tendencia = últimas 4 vs 4 previas
    const half = 4;
    const recent = weekly.slice(-half).reduce((a,b)=>a+b,0);
    const older  = weekly.slice(-half*2, -half).reduce((a,b)=>a+b,0) || 0.0001;
    const trend  = ((recent - older) / older) * 100;
    tr.dataset.total = total;
    tr.dataset.last = last;
    tr.dataset.avg = avg.toFixed(2);
    tr.dataset.trend = trend.toFixed(2);
    weekly.forEach((v, i) => {{ tr.dataset['w'+i] = v; }});
    // Enhance total cell visually
    const totalCell = tr.querySelector('.vtotal');
    if (totalCell) totalCell.classList.add('vtotal-cell');
  }});
  // Click handlers on headers
  const headers = table.querySelectorAll('thead th[data-sort]');
  headers.forEach(th => {{
    th.addEventListener('click', () => {{
      const key = th.dataset.sort;
      const currentDir = th.classList.contains('sorted-desc') ? 'desc' : (th.classList.contains('sorted-asc') ? 'asc' : null);
      const nextDir = currentDir === 'desc' ? 'asc' : 'desc';
      headers.forEach(h => h.classList.remove('sorted-asc','sorted-desc'));
      th.classList.add(nextDir === 'desc' ? 'sorted-desc' : 'sorted-asc');
      // Sync select when header matches a preset option
      const sel = document.getElementById('vendor-sort-mode');
      if (sel){{
        if (key === 'total') sel.value = 'total-' + nextDir;
        else if (key === 'name') sel.value = 'name-' + nextDir;
      }}
      applySort(key, nextDir);
    }});
  }});
  // Default sort: total desc
  applySort('total','desc');
}}
function applySort(key, dir){{
  const table = document.getElementById('vendor-matrix');
  if (!table) return;
  const tbody = table.querySelector('tbody');
  const rows = [...tbody.querySelectorAll('tr.vrow')];
  const sign = dir === 'asc' ? 1 : -1;
  const keyFn = (tr) => {{
    if (key === 'name') return (tr.dataset.vendor || '').toLowerCase();
    if (key === 'total') return +tr.dataset.total;
    if (key === 'last') return +tr.dataset.last;
    if (key === 'avg') return +tr.dataset.avg;
    if (key === 'trend') return +tr.dataset.trend;
    if (key && key.startsWith('w')) return +tr.dataset[key];
    return 0;
  }};
  rows.sort((a,b) => {{
    const av = keyFn(a), bv = keyFn(b);
    if (typeof av === 'string') return sign * av.localeCompare(bv, 'es');
    return sign * (av - bv);
  }});
  rows.forEach((r, i) => {{
    tbody.appendChild(r);
    // Rank badge
    const vn = r.querySelector('.vname');
    if (vn){{
      const existing = vn.querySelector('.rank-badge');
      if (existing) existing.remove();
      const badge = document.createElement('span');
      badge.className = 'rank-badge' + (i===0?' top':(i===1?' top2':(i===2?' top3':'')));
      badge.textContent = '#' + (i+1);
      const dot = vn.querySelector('.quota-dot');
      if (dot) vn.insertBefore(badge, dot.nextSibling);
      else vn.insertBefore(badge, vn.firstChild);
    }}
  }});
}}
function sortVendorMatrix(){{
  const sel = document.getElementById('vendor-sort-mode');
  if (!sel) return;
  const [key, dir] = sel.value.split('-');
  // Update header indicator
  const table = document.getElementById('vendor-matrix');
  table.querySelectorAll('thead th').forEach(h => h.classList.remove('sorted-asc','sorted-desc'));
  const th = table.querySelector(`thead th[data-sort="${{key}}"]`);
  if (th) th.classList.add(dir === 'asc' ? 'sorted-asc' : 'sorted-desc');
  applySort(key, dir);
}}

// Init
document.addEventListener('DOMContentLoaded', function() {{
  const lastBtn = document.querySelector('.week-sidebar-btn.active');
  showWeek(16, lastBtn);
  // Nuevos charts + matriz vendedores
  if (window.Chart){{
    try {{ renderTrendChart(); }} catch(e){{ console.error('trend', e); }}
    try {{ renderChannelChart(); }} catch(e){{ console.error('channels', e); }}
  }}
  try {{ enhanceVendorMatrix(); }} catch(e){{ console.error('matrix', e); }}
}});
"""


def build_html(data, update_time):
    d          = data
    vw_t       = d["vw_t"]
    pipe_t     = d["pipe_t"]
    cw_t       = d["cw_t"]
    fc         = d["forecast"]
    deals      = d["deals"]
    months     = d["months_data"]
    vendors    = d["vendors"]
    svend      = d["sorted_vendors"]
    ent        = d["ent"]
    ter        = d["ter"]
    ng         = d["ng_deals"]
    sw         = d["sorted_weeks"]
    vw_map     = d["vendor_week"]
    wt         = d["week_totals"]
    max_wk     = d["max_wk"]
    src_sorted = d["src_sorted"]
    src_max    = d["src_max"]

    active_count = len([x for x in deals if x["stage_id"] not in {CLOSE_WON}])

    # ── Unique owners in Q2 deals (for filter dropdown)
    q2_owners = sorted(set(d["owner"] for d in deals))

    # ── TAB 1: KPIs ──────────────────────────────────────────────────────────
    kpi_pct = pct(fc, FORECAST_TARGET)
    gap     = FORECAST_TARGET - fc

    # ── TAB 1: Teams ─────────────────────────────────────────────────────────
    ent_fc    = ent["vw"] + ent["pipeline"] + ent["cw"]
    ter_fc    = ter["vw"] + ter["pipeline"] + ter["cw"]
    ent_2x    = ENT_GOAL * 2
    ter_2x    = TER_GOAL * 2

    # ── TAB 1: Deal table rows ────────────────────────────────────────────────
    deal_rows = []
    for deal in deals:
        sid   = deal["stage_id"]
        owner = deal["owner"]
        lc_cls, lc_txt = contact_info(deal["last_contact"])
        rl    = deal["risk"]
        na    = deal["next_activity"]
        cat_attr = "Verbal Win" if sid in VERBAL_WIN else deal["stage"]
        risk_attr = RISK_LBL.get(rl, "").lower()
        deal_url  = f"https://app.hubspot.com/contacts/{PORTAL_ID}/record/0-3/{deal['id']}"
        origen_html = f'<span class="origen-tag">{deal["origen"]}</span>' if deal.get("origen") else '<span class="na">—</span>'
        row = (
            f'<tr data-owner="{owner}" data-risk="{risk_attr}" data-cat="{cat_attr}">\n'
            f'  <td><a href="{deal_url}" target="_blank" class="deal-link">{deal["name"]}</a></td>\n'
            f'  <td>{usd(deal["amount"])}</td>\n'
            f'  <td class="na-cell">{owner}</td>\n'
            f'  <td>{stage_badge_html(sid, deal["stage"])}</td>\n'
            f'  <td>{month_badge_html(deal["month"])}</td>\n'
            f'  <td><span class="origen-tag">{deal.get("origen") or "—"}</span></td>\n'
            f'  <td><span class="{lc_cls}">{lc_txt}</span></td>\n'
            f'  <td><span class="risk-badge {RISK_CSS[rl]}">{RISK_LBL[rl]}</span></td>\n'
            f'</tr>'
        )
        deal_rows.append(row)

    deal_rows_html = "\n".join(deal_rows)
    owner_opts     = "\n".join(f'<option value="{o}">{o}</option>' for o in q2_owners)

    # ── TAB 2: Vendor sections ────────────────────────────────────────────────
    vendor_sidebar_html = []
    vendor_sections_html = []

    for i, name in enumerate(svend):
        q       = QUOTAS[name]
        vid     = q["id"]
        team    = q["team"]
        quota   = q["quota"]
        vdata   = vendors[name]
        v_vw    = vdata["vw"]
        v_pipe  = vdata["pipeline"]
        v_cw    = vdata["cw"]
        v_fc    = v_vw + v_pipe + v_cw
        active_cls = "active" if i == 0 else ""
        team_clr   = "#0052cc" if team == "Enterprise" else "#00875a"

        # Sidebar item
        vendor_sidebar_html.append(
            f'<button class="sidebar-item {active_cls}" onclick="showVendor(\'{vid}\', this)">'
            f'<span style="width:26px;height:26px;border-radius:50%;background:{team_clr}15;'
            f'color:{team_clr};font-weight:700;font-size:.7rem;display:flex;align-items:center;'
            f'justify-content:center;flex-shrink:0">{q["initials"]}</span>'
            f'<span style="flex:1;text-align:left;font-size:.8rem">{name}</span>'
            f'</button>'
        )

        # Deal table for this vendor
        v_deal_rows = []
        for deal in vdata["deals"]:
            sid      = deal["stage_id"]
            lc_cls2, lc_txt2 = contact_info(deal["last_contact"])
            rl2      = deal["risk"]
            cat2     = "Verbal Win" if sid in VERBAL_WIN else deal["stage"]
            d_url    = f"https://app.hubspot.com/contacts/{PORTAL_ID}/record/0-3/{deal['id']}"
            v_deal_rows.append(
                f'<tr data-cat="{cat2}">'
                f'<td><a href="{d_url}" target="_blank" class="deal-link">{deal["name"]}</a></td>'
                f'<td>{usd(deal["amount"])}</td>'
                f'<td>{stage_badge_html(sid, deal["stage"])}</td>'
                f'<td>{month_badge_html(deal["month"])}</td>'
                f'<td><span class="origen-tag">{deal.get("origen") or "—"}</span></td>'
                f'<td><span class="{lc_cls2}">{lc_txt2}</span></td>'
                f'<td><span class="risk-badge {RISK_CSS[rl2]}">{RISK_LBL[rl2]}</span></td>'
                f'</tr>'
            )
        v_deal_rows_html = "\n".join(v_deal_rows) if v_deal_rows else (
            '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:20px">'
            'Sin negocios activos en Q2</td></tr>'
        )

        tbid = f"vtbody-{vid}"

        section_display = "block" if i == 0 else "none"
        vendor_sections_html.append(f"""
<div class="vendor-section" id="{vid}" style="display:{section_display}">
  <div class="kpi-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:14px">
    <div class="kpi k-blue">
      <div class="kpi-label">🏆 Close Won</div>
      <div class="kpi-value">{usd(v_cw)}</div>
      <div class="kpi-sub">Objetivo: {usd(quota)}</div>
    </div>
    <div class="kpi k-purple">
      <div class="kpi-label">⭐ Verbal Win</div>
      <div class="kpi-value" style="color:var(--purple)">{usd(v_vw)}</div>
      <div class="kpi-sub">RA&amp;D + Validación Interna</div>
    </div>
    <div class="kpi k-teal">
      <div class="kpi-label">📦 Pipeline</div>
      <div class="kpi-value">{usd(v_pipe)}</div>
      <div class="kpi-sub">Forecast total: {usd(v_fc)}</div>
    </div>
  </div>
  <div class="team-card" style="margin-bottom:14px">
    <div class="team-row">
      <div class="team-row-header">
        <span class="team-row-label">📊 Forecast vs 2× objetivo ({usd(quota*2)})</span>
        <span class="team-row-val">{pct(v_fc, quota*2)}%</span>
      </div>
      <div class="prog-stacked">
        <div style="width:{bw(v_cw,quota*2)}%;background:var(--green);min-width:{2 if v_cw else 0}px"></div>
        <div style="width:{bw(v_vw,quota*2)}%;background:var(--purple);min-width:{2 if v_vw else 0}px"></div>
        <div style="width:{bw(v_pipe,quota*2)}%;background:var(--teal)"></div>
      </div>
      <div class="prog-meta">
        <span><span style="color:var(--purple)">■</span> VW {usd(v_vw)} &nbsp;
        <span style="color:var(--teal)">■</span> Pipe {usd(v_pipe)}</span>
        <span>Brecha {usd(max(0, quota*2 - v_fc))}</span>
      </div>
    </div>
  </div>
  <div class="table-wrap">
    <div class="table-toolbar">
      <h3>Negocios Q2 — {len(vdata["deals"])} negocio{"s" if len(vdata["deals"]) != 1 else ""}</h3>
      <div class="toolbar-right">
        <input class="search-input" id="search-vendor-{tbid}" placeholder="Buscar…"
               oninput="filterVendorDeals('{tbid}')">
        <select class="filter-select" id="filter-vendor-cat-{tbid}"
                onchange="filterVendorDeals('{tbid}')">
          <option value="">Todas las etapas</option>
          <option value="Close Won">Close Won</option>
          <option value="Verbal Win">Verbal Win</option>
          <option value="Discovery">Discovery</option>
          <option value="Qualified">Qualified</option>
          <option value="Negotiation">Negotiation</option>
        </select>
      </div>
    </div>
    <div style="overflow-x:auto">
    <table>
      <thead><tr>
        <th onclick="sortTable(0,'{tbid}')">Negocio ↕</th>
        <th onclick="sortTable(1,'{tbid}')">Monto ↕</th>
        <th>Etapa</th>
        <th onclick="sortTable(3,'{tbid}')">Mes cierre ↕</th>
        <th>Origen</th>
        <th>Últ. Contacto</th>
        <th>Riesgo</th>
      </tr></thead>
      <tbody id="{tbid}">
{v_deal_rows_html}
      </tbody>
    </table>
    </div>
  </div>
</div>""")

    vendor_sidebar_final  = "\n".join(vendor_sidebar_html)
    vendor_sections_final = "\n".join(vendor_sections_html)

    # ── TAB 3: Negocios — matrix ──────────────────────────────────────────────
    n_weeks  = len(sw)
    wk_hdrs  = "".join(
        f'<th class="wk-th" data-sort="w{i}" title="Click para ordenar por esta semana">{sw[i].split("·")[1].strip() if "·" in sw[i] else sw[i]}</th>'
        for i in range(n_weeks)
    )
    matrix_rows = []
    for name in [n for n in svend if n in vw_map]:
        q      = QUOTAS[name]
        tot    = sum(vw_map[name].values())
        cells  = "".join(
            f'<td class="wk-cell {heat_class(vw_map[name].get(i,0), max_wk)}">'
            f'{vw_map[name].get(i,0) or ""}</td>'
            for i in range(n_weeks)
        )
        matrix_rows.append(
            f'<tr class="vrow vrow-quota" data-vendor="{name}">'
            f'<td class="vname"><span class="quota-dot"></span>{name}</td>'
            f'{cells}'
            f'<td class="vtotal vtotal-cell">{tot}</td>'
            f'</tr>'
        )

    # Week totals row
    tot_cells = "".join(
        f'<td>{wt.get(i,"")}</td>'
        for i in range(n_weeks)
    )
    totals_row = (
        f'<tr><td class="vname">TOTAL</td>'
        f'{tot_cells}'
        f'<td class="vtotal-cell">{sum(wt.values())}</td>'
        f'</tr>'
    )

    matrix_rows_html = "\n".join(matrix_rows)

    # Source chart
    src_colors = ["#0052cc","#00b8d9","#36b37e","#6554c0","#ff991f","#ff5630","#00875a","#403294"]
    src_rows = []
    total_ng = len(ng)
    for i, (lbl, cnt) in enumerate(src_sorted):
        clr  = src_colors[i % len(src_colors)]
        spct = pct(cnt, src_max) if src_max else 0
        ppct = pct(cnt, total_ng) if total_ng else 0
        src_rows.append(
            f'<div class="src-row">'
            f'<span class="src-label">{lbl}</span>'
            f'<div class="src-bar-wrap"><div class="src-bar" style="width:{spct}%;background:{clr}"></div></div>'
            f'<span class="src-count">{cnt} <span class="src-pct">({ppct}%)</span></span>'
            f'</div>'
        )
    src_chart_html = "\n".join(src_rows)

    # Trend chart (all weeks)
    trend_max = max(wt.values()) if wt else 1
    trend_cols = []
    for i, lbl in enumerate(sw):
        cnt     = wt.get(i, 0)
        bar_h   = max(3, round(cnt / trend_max * 120)) if trend_max else 3
        short   = lbl.split("·")[1].strip() if "·" in lbl else lbl
        trend_cols.append(
            f'<div class="trend-col">'
            f'<div class="trend-val">{cnt if cnt else ""}</div>'
            f'<div class="trend-bar-wrap"><div class="trend-bar" style="height:{bar_h}px"></div></div>'
            f'<div class="trend-lbl">{short}</div>'
            f'</div>'
        )
    trend_html = "\n".join(trend_cols)

    # ── TAB 4: Detalle — sidebar + vendor filter ──────────────────────────────
    week_btn_html = []
    for i, lbl in enumerate(reversed(sw)):
        real_idx = len(sw) - 1 - i
        active   = "active" if i == 0 else ""
        week_btn_html.append(
            f'<button class="week-sidebar-btn {active}" onclick="showWeek({real_idx}, this)">'
            f'{lbl}</button>'
        )
    week_btns_html = "\n".join(week_btn_html)

    # Unique vendors in new deals
    ng_vendors = sorted(set(d["o"] for d in ng if d["o"] in QUOTAS))
    ng_vendor_opts = "\n".join(f'<option value="{v}">{v}</option>' for v in ng_vendors)

    # ── Pre-compute JS data strings ───────────────────────────────────────────
    ng_json    = json.dumps(ng, ensure_ascii=False)
    weeks_json = json.dumps(sw, ensure_ascii=False)
    init_week  = len(sw) - 1 if sw else 0
    init_lbl   = sw[init_week] if sw else ""

    # ── Assemble HTML ─────────────────────────────────────────────────────────
    parts = []

    parts.append(f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Forecast Q2 2026 — MX Sales</title>
<style>{CSS}</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-adapter-date-fns/3.0.0/chartjs-adapter-date-fns.bundle.min.js"></script>
</head>
<body>

<header class="header">
  <div>
    <h1>📊 Forecast Q2 2026 — MX Sales</h1>
    <div class="header-meta">Abril · Mayo · Junio 2026 &nbsp;·&nbsp; Actualizado: {update_time}</div>
  </div>
  <div class="header-right">
    <div style="font-size:.9rem;font-weight:700">Objetivo Q2</div>
    <div style="font-size:1.3rem;font-weight:700">$95,000 USD</div>
  </div>
</header>

<nav class="tab-bar">
  <button class="tab-btn active" onclick="showTab('overview')">📊 Dashboard Q2</button>
  <button class="tab-btn" onclick="showTab('vendors')">👤 Por Vendedor</button>
  <button class="tab-btn" onclick="showTab('negocios')">📋 Negocios</button>
  <button class="tab-btn" onclick="showTab('detalle')">🗓️ Detalle Semanal</button>
</nav>

<!-- ═══ TAB 1: OVERVIEW ═══ -->
<main class="page active" id="overview">

  <div class="kpi-grid">
    <div class="kpi k-blue">
      <div class="kpi-label">🏆 Close Won Q2</div>
      <div class="kpi-value">{usd(cw_t)}</div>
      <div class="kpi-sub">Objetivo: $95,000 · {pct(cw_t, 95000)}% completado</div>
    </div>
    <div class="kpi k-purple">
      <div class="kpi-label">⭐ Verbal Win</div>
      <div class="kpi-value" style="color:var(--purple)">{usd(vw_t)}</div>
      <div class="kpi-sub">RA&amp;D + Validación Interna · {len(d["vw_deals"])} negocios</div>
    </div>
    <div class="kpi k-teal">
      <div class="kpi-label">📦 Pipeline Activo</div>
      <div class="kpi-value">{usd(pipe_t)}</div>
      <div class="kpi-sub">Discovery · Qualified · Negotiation · {len(d["pipe_deals"])} negocios</div>
    </div>
    <div class="kpi k-orange">
      <div class="kpi-label">Total Forecast vs 2× objetivo</div>
      <div class="kpi-value">{kpi_pct}%</div>
      <div class="kpi-sub">{usd(fc)} / {usd(FORECAST_TARGET)} · Brecha: {usd(gap)}</div>
    </div>
  </div>

  <div class="progress-card">
    <div>
      <div class="prog-label">🏆 Close Won vs Objetivo Q2</div>
      <div class="prog-val" style="color:{'var(--green-dk)' if cw_t >= 95000 else 'var(--red-dk)'}">{pct(cw_t,95000)}% — {usd(cw_t)} / $95,000</div>
      <div class="prog-bar"><div class="prog-fill" style="width:{bw(cw_t,95000)}%;background:var(--green)"></div></div>
      <div class="prog-meta"><span>$0</span><span>$47,500</span><span><strong>$95,000 objetivo</strong></span></div>
    </div>
    <div>
      <div class="prog-label">📊 Forecast Activo vs Objetivo 2× ({usd(FORECAST_TARGET)})</div>
      <div class="prog-val">{kpi_pct}% — {usd(fc)} / {usd(FORECAST_TARGET)}</div>
      <div class="prog-stacked">
        <div style="width:{bw(vw_t,FORECAST_TARGET)}%;background:var(--purple);min-width:{2 if vw_t else 0}px" title="VW: {usd(vw_t)}"></div>
        <div style="width:{bw(pipe_t,FORECAST_TARGET)}%;background:var(--teal)" title="Pipeline: {usd(pipe_t)}"></div>
      </div>
      <div class="prog-meta">
        <span><span style="color:var(--purple)">■</span> VW {usd(vw_t)} &nbsp;<span style="color:var(--teal)">■</span> Pipe {usd(pipe_t)}</span>
        <span><strong>Brecha {usd(gap)}</strong></span>
      </div>
    </div>
  </div>

  <div class="two-col">
    <div class="team-card">
      <div class="team-name" style="color:#0052cc">🏢 Enterprise <span style="font-size:.75rem;font-weight:500;color:var(--muted);margin-left:6px">Obj: {usd(ENT_GOAL)}</span></div>
      <div class="team-row">
        <div class="team-row-header">
          <span class="team-row-label">🏆 Close Won</span>
          <span class="team-row-val" style="color:{'var(--green-dk)' if ent['cw']>=ENT_GOAL else 'var(--red-dk)'}">{usd(ent['cw'])} / {usd(ENT_GOAL)}</span>
        </div>
        <div class="prog-bar"><div class="prog-fill" style="width:{bw(ent['cw'],ENT_GOAL)}%;background:var(--green)"></div></div>
        <div class="prog-meta"><span>{pct(ent['cw'],ENT_GOAL)}% completado</span><span>Q2 Abril–Junio</span></div>
      </div>
      <div class="team-row">
        <div class="team-row-header">
          <span class="team-row-label">📊 Forecast vs 2× objetivo ({usd(ent_2x)})</span>
          <span class="team-row-val" style="color:var(--red-dk)">{pct(ent_fc,ent_2x)}%</span>
        </div>
        <div class="prog-stacked">
          <div style="width:{bw(ent['cw'],ent_2x)}%;background:var(--green);min-width:{2 if ent['cw'] else 0}px"></div>
          <div style="width:{bw(ent['vw'],ent_2x)}%;background:var(--purple);min-width:{2 if ent['vw'] else 0}px"></div>
          <div style="width:{bw(ent['pipeline'],ent_2x)}%;background:var(--teal)"></div>
        </div>
        <div class="prog-meta">
          <span><span style="color:var(--purple)">■</span> VW {usd(ent['vw'])} &nbsp;<span style="color:var(--teal)">■</span> Pipe {usd(ent['pipeline'])}</span>
          <span>Total {usd(ent_fc)} · Brecha {usd(max(0,ent_2x-ent_fc))}</span>
        </div>
      </div>
    </div>
    <div class="team-card">
      <div class="team-name" style="color:#00875a">🗺️ Territorio <span style="font-size:.75rem;font-weight:500;color:var(--muted);margin-left:6px">Obj: {usd(TER_GOAL)}</span></div>
      <div class="team-row">
        <div class="team-row-header">
          <span class="team-row-label">🏆 Close Won</span>
          <span class="team-row-val" style="color:{'var(--green-dk)' if ter['cw']>=TER_GOAL else 'var(--red-dk)'}">{usd(ter['cw'])} / {usd(TER_GOAL)}</span>
        </div>
        <div class="prog-bar"><div class="prog-fill" style="width:{bw(ter['cw'],TER_GOAL)}%;background:var(--green)"></div></div>
        <div class="prog-meta"><span>{pct(ter['cw'],TER_GOAL)}% completado</span><span>Q2 Abril–Junio</span></div>
      </div>
      <div class="team-row">
        <div class="team-row-header">
          <span class="team-row-label">📊 Forecast vs 2× objetivo ({usd(ter_2x)})</span>
          <span class="team-row-val" style="color:var(--red-dk)">{pct(ter_fc,ter_2x)}%</span>
        </div>
        <div class="prog-stacked">
          <div style="width:{bw(ter['cw'],ter_2x)}%;background:var(--green);min-width:{2 if ter['cw'] else 0}px"></div>
          <div style="width:{bw(ter['vw'],ter_2x)}%;background:var(--purple);min-width:{2 if ter['vw'] else 0}px"></div>
          <div style="width:{bw(ter['pipeline'],ter_2x)}%;background:var(--teal)"></div>
        </div>
        <div class="prog-meta">
          <span><span style="color:var(--purple)">■</span> VW {usd(ter['vw'])} &nbsp;<span style="color:var(--teal)">■</span> Pipe {usd(ter['pipeline'])}</span>
          <span>Total {usd(ter_fc)} · Brecha {usd(max(0,ter_2x-ter_fc))}</span>
        </div>
      </div>
    </div>
  </div>

  <div class="three-col">""")

    # Month cards
    month_dots = {"Abril": "#0052cc", "Mayo": "#00b8d9", "Junio": "#00875a", "Julio": "#6b21a8"}
    for mname, mclr in month_dots.items():
        md      = months[mname]
        m_total = md["vw"] + md["pipe"] + md["cw"]
        m_vw_w  = bw(md["vw"], m_total)
        m_p_w   = bw(md["pipe"], m_total)
        parts.append(f"""
    <div class="month-card">
      <div class="month-name">
        <span class="month-dot" style="background:{mclr}"></span>
        {mname} 2026
      </div>
      <div class="month-stat"><span>Negocios activos</span><strong>{md["count"]}</strong></div>
      <div class="month-stat"><span>⭐ Verbal Win</span><strong style="color:var(--purple)">{usd(md["vw"])}</strong></div>
      <div class="month-stat"><span>📦 Pipeline</span><strong>{usd(md["pipe"])}</strong></div>
      <div style="margin-top:8px">
        <div style="display:flex;height:8px;border-radius:5px;overflow:hidden;background:#eee;gap:1px">
          <div style="width:{m_vw_w}%;background:var(--purple);min-width:{2 if md['vw'] else 0}px"></div>
          <div style="width:{m_p_w}%;background:{mclr}"></div>
        </div>
      </div>
    </div>""")

    parts.append(f"""
  </div>

  <!-- All deals table -->
  <div class="table-wrap">
    <div class="table-toolbar">
      <h3>Todos los negocios activos Q2 — {active_count} negocios</h3>
      <div class="toolbar-right">
        <input class="search-input" id="search-overview" placeholder="Buscar negocio…" oninput="filterOverview()">
        <select class="filter-select" id="filter-owner" onchange="filterOverview()">
          <option value="">Todos los vendedores</option>
{owner_opts}
        </select>
        <select class="filter-select" id="filter-cat" onchange="filterOverview()">
          <option value="">Todas las etapas</option>
          <option value="Close Won">Close Won</option>
          <option value="Verbal Win">Verbal Win</option>
          <option value="Discovery">Discovery</option>
          <option value="Qualified">Qualified</option>
          <option value="Negotiation">Negotiation</option>
        </select>
        <select class="filter-select" id="filter-risk" onchange="filterOverview()">
          <option value="">Todos los riesgos</option>
          <option value="Alto">Riesgo Alto</option>
          <option value="Medio">Riesgo Medio</option>
          <option value="Bajo">Riesgo Bajo</option>
        </select>
      </div>
    </div>
    <div style="overflow-x:auto">
    <table>
      <thead><tr>
        <th onclick="sortTable(0,'overview-tbody')">Negocio ↕</th>
        <th onclick="sortTable(1,'overview-tbody')">Monto ↕</th>
        <th>Vendedor</th>
        <th>Etapa</th>
        <th onclick="sortTable(4,'overview-tbody')">Mes cierre ↕</th>
        <th>Origen</th>
        <th onclick="sortTable(6,'overview-tbody')">Últ. Contacto ↕</th>
        <th>Riesgo</th>
      </tr></thead>
      <tbody id="overview-tbody">
{deal_rows_html}
      </tbody>
    </table>
    </div>
    <div class="table-footer">{active_count} negocios activos · {usd(fc)} total forecast</div>
  </div>

</main>

<!-- ═══ TAB 2: POR VENDEDOR ═══ -->
<main class="page" id="vendors">
  <div class="vendor-layout">
    <nav class="vendor-sidebar">
{vendor_sidebar_final}
    </nav>
    <div class="vendor-content">
{vendor_sections_final}
    </div>
  </div>
</main>

<!-- ═══ TAB 3: NEGOCIOS ═══ -->
<main class="page" id="negocios">
  <div class="two-col" style="margin-bottom:18px">

    <div class="card card-pad">
      <div class="neg-card-header">
        <div>
          <div class="section-title">📈 Nuevos negocios por canal</div>
          <div class="section-sub" id="channel-sub">Evolución por fuente de origen</div>
        </div>
        <div class="seg-control" role="tablist" aria-label="Granularidad canal">
          <button class="seg-btn" data-gran="day" onclick="setChannelGran('day', this)">Día</button>
          <button class="seg-btn on" data-gran="week" onclick="setChannelGran('week', this)">Semana</button>
          <button class="seg-btn" data-gran="month" onclick="setChannelGran('month', this)">Mes</button>
        </div>
      </div>
      <div class="chart-box tall"><canvas id="chartChannels"></canvas></div>
      <div class="channel-actions" style="margin-top:10px">
        <button class="mini-btn" onclick="toggleAllChannels(true)">Mostrar todos</button>
        <button class="mini-btn" onclick="toggleAllChannels(false)">Ocultar todos</button>
        <button class="mini-btn" onclick="showTopChannels(5)">Top 5 canales</button>
      </div>
      <div class="channel-legend" id="channelLegend"></div>
    </div>

    <div class="card card-pad">
      <div class="neg-card-header">
        <div>
          <div class="section-title">📊 Nuevos negocios en el tiempo</div>
          <div class="section-sub" id="trend-sub">Total de negocios creados</div>
        </div>
        <div class="seg-control" role="tablist" aria-label="Granularidad">
          <button class="seg-btn" data-gran="day" onclick="setTrendGran('day', this)">Día</button>
          <button class="seg-btn on" data-gran="week" onclick="setTrendGran('week', this)">Semana</button>
          <button class="seg-btn" data-gran="month" onclick="setTrendGran('month', this)">Mes</button>
        </div>
      </div>
      <div class="chart-box tall"><canvas id="chartTrend"></canvas></div>
      <div class="chart-summary" id="trendSummary"></div>
    </div>

  </div>

  <div class="table-wrap">
    <div class="table-toolbar">
      <h3>👥 Nuevos negocios por vendedor × semana</h3>
      <div class="toolbar-right">
        <div class="heat-legend" title="Escala de calor por celda">
          <span>Bajo</span>
          <div class="heat-scale">
            <span style="background:#fff"></span>
            <span style="background:#e9f0ff"></span>
            <span style="background:#b3ccff"></span>
            <span style="background:#5c97ff"></span>
            <span style="background:#1a5fd4"></span>
            <span style="background:#03306e"></span>
          </div>
          <span>Alto</span>
        </div>
        <select class="filter-select" id="vendor-sort-mode" onchange="sortVendorMatrix()">
          <option value="total-desc">Ordenar: Total ↓ (mejor→peor)</option>
          <option value="total-asc">Total ↑ (peor→mejor)</option>
          <option value="last-desc">Última semana ↓</option>
          <option value="last-asc">Última semana ↑</option>
          <option value="avg-desc">Promedio semanal ↓</option>
          <option value="avg-asc">Promedio semanal ↑</option>
          <option value="trend-desc">Tendencia 4 sem ↓</option>
          <option value="trend-asc">Tendencia 4 sem ↑</option>
          <option value="name-asc">Nombre A→Z</option>
          <option value="name-desc">Nombre Z→A</option>
        </select>
        <input class="search-input" placeholder="Filtrar vendedor…" oninput="filterNegocios()" id="filter-negocios-vendor">
      </div>
    </div>
    <div class="vendor-matrix-wrap">
    <table class="vendor-matrix" id="vendor-matrix">
      <thead>
        <tr>
          <th class="vname" data-sort="name" title="Click para ordenar por nombre">Vendedor</th>
{wk_hdrs}
          <th data-sort="total" class="sorted-desc" title="Click para ordenar por total">Total</th>
        </tr>
      </thead>
      <tbody>
{matrix_rows_html}
      </tbody>
      <tfoot>
{totals_row}
      </tfoot>
    </table>
    </div>
  </div>
</main>

<!-- ═══ TAB 4: DETALLE SEMANAL ═══ -->
<main class="page" id="detalle">
  <div class="detalle-layout">
    <nav class="detalle-sidebar">
      <div class="detalle-sidebar-title">Semanas</div>
{week_btns_html}
    </nav>
    <div class="detalle-content">
      <div class="table-wrap">
        <div class="table-toolbar">
          <h3>🗓️ <span id="detalle-week-title">{init_lbl}</span></h3>
          <div class="toolbar-right">
            <span id="detalle-deal-count" style="font-size:.8rem;color:var(--muted)">—</span>
            <select class="filter-select" id="detalle-filter-vendor" onchange="applyDetallFilter()">
              <option value="">Todos los vendedores</option>
{ng_vendor_opts}
            </select>
          </div>
        </div>
        <div style="overflow-x:auto">
        <table id="week-deal-table">
          <thead><tr>
            <th>Negocio</th>
            <th>Vendedor</th>
            <th>Etapa</th>
            <th>Origen</th>
          </tr></thead>
          <tbody id="week-deal-tbody">
            <tr><td colspan="4" style="text-align:center;color:var(--muted);padding:24px">Cargando…</td></tr>
          </tbody>
        </table>
        </div>
      </div>
    </div>
  </div>
</main>

<script>
const _NG_DEALS = {ng_json};
const _WEEKS    = {weeks_json};
let _currentWeekIdx = {init_week};

{STATIC_JS}

// Init
document.addEventListener('DOMContentLoaded', function() {{
  const lastBtn = document.querySelector('.week-sidebar-btn.active');
  showWeek({init_week}, lastBtn);
}});
</script>
</body>
</html>""")

    return "".join(parts)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    today = datetime.date.today()

    print("Fetching owners…")
    owners = fetch_owners()
    print(f"  {len(owners)} owners found")

    # Q2 date range (Apr 1 – Jul 31 of current year, extended to capture borderline deals)
    yr         = today.year
    q2_start   = datetime.datetime(yr, 4, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    q2_end     = datetime.datetime(yr, 7, 31, 23, 59, 59, tzinfo=datetime.timezone.utc)
    q2_start_ms = str(int(q2_start.timestamp() * 1000))
    q2_end_ms   = str(int(q2_end.timestamp() * 1000))

    print("Fetching Q2 deals…")
    raw_q2 = hs_search_all(
        filters=[
            {"propertyName": "pipeline",  "operator": "EQ",  "value": PIPELINE_ID},
            {"propertyName": "closedate", "operator": "GTE", "value": q2_start_ms},
            {"propertyName": "closedate", "operator": "LTE", "value": q2_end_ms},
        ],
        properties=[
            "dealname", "amount", "closedate", "hubspot_owner_id",
            "dealstage", "notes_last_contacted", "hs_next_activity_date", "origen",
        ],
    )
    print(f"  {len(raw_q2)} Q2 deals")

    new_since = datetime.datetime(2025, 12, 29, 0, 0, 0, tzinfo=datetime.timezone.utc)
    new_since_ms = str(int(new_since.timestamp() * 1000))

    print("Fetching new deals since Dec 29 2025…")
    raw_new = hs_search_all(
        filters=[
            {"propertyName": "pipeline",   "operator": "EQ",  "value": PIPELINE_ID},
            {"propertyName": "createdate", "operator": "GTE", "value": new_since_ms},
        ],
        properties=["dealname", "createdate", "hubspot_owner_id", "origen", "dealstage"],
    )
    print(f"  {len(raw_new)} new deals")

    print("Processing data…")
    data = process_data(owners, raw_q2, raw_new)

    months_dict = {4: "enero", 5: "febrero", 6: "marzo", 7: "abril", 8: "mayo",
                   9: "junio", 10: "julio", 11: "agosto", 12: "septiembre",
                   1: "enero", 2: "febrero", 3: "marzo"}
    MONTHS_ES = {
        1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
        7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"
    }
    update_time = f"{today.day} de {MONTHS_ES[today.month]} de {today.year}"

    print("Generating HTML…")
    html = build_html(data, update_time)

    out = "index.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Done! {out} written ({len(html):,} bytes, {len(html.splitlines()):,} lines)")


if __name__ == "__main__":
    main()
