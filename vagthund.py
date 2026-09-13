#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Outputvagthund for dashboards under AI-MichelKlos.

Kontrollerer de PUBLICEREDE sider og deres data, ikke GitHub Actions:
  1. Svarer siden, og er den hel (status, størrelse, canvas, fejltekst)?
  2. Er dataene faktisk hentet for nylig, og fejlede nogen kilder?
  3. Er en DST-kilde foran dashboardet (Statistikbanken-API)?
  4. Halter et datasæt bagefter det samme datasæt i et andet dashboard?
  5. Ser hovedtallene forkerte ud (huller, nuller, urealistiske spring)?

Kun aggregerede hovedserier tjekkes for tal. Opdelinger på a-kasse, kommune
og sanktionstype springes over, fordi små tal og diskretionering giver støj.

Brug:  python3 vagthund.py [--forrige tidligere_state.json] [--state ny_state.json]
Skriver rapporten til stdout og en maskinlæsbar state-fil (default state.json).
"""

import argparse, json, re, sys, urllib.request, urllib.error
from datetime import datetime, timezone

BASE = "https://ai-michelklos.github.io/"
NOW = datetime.now(timezone.utc)

DASHBOARDS = [
    {"navn": "arbejdsmarked (hub)",            "repo": "arbejdsmarked",                    "data": None,  "min_bytes": 8000},
    {"navn": "Analytisk overblik",             "repo": "Dashboard",                        "data": "data/dashboard-data.json", "min_bytes": 60000, "max_dage": 9},
    {"navn": "Dashboard-dak-jur",              "repo": "Dashboard-dak-jur",                "data": "data/dashboard-data.json", "min_bytes": 60000, "max_dage": 9},
    {"navn": "A-kasseindsigt",                 "repo": "A-kasseindsigt-dashboard",         "data": "data/dashboard-data.json", "min_bytes": 30000, "max_dage": 9},
    {"navn": "Kommunal beskæftigelsesindsats", "repo": "kommunal-beskaeftigelsesindsats",  "data": "data/dashboard-data.json", "min_bytes": 20000, "max_dage": 9},
    {"navn": "Udenlandske lønmodtagere",       "repo": "udenlandskeloenmodtagere",         "data": "data/dashboard-data.json", "min_bytes": 10000, "max_dage": 11},
    {"navn": "Arbejdsstyrke",                  "repo": "arbejdsstyrke",                    "data": "data/dashboard-data.json", "min_bytes": 3000,  "max_dage": 11},
    {"navn": "Ansatte i danske virksomheder",  "repo": "ansatteidanskevirksomheder",       "data": None,  "min_bytes": 100000},
]

# Containere med opdelinger: spring over (kun totalen tjekkes)
SPRING_OVER = {"byakasse", "bykommune", "funds", "municipalities", "kommuner",
               "sanctions", "types", "items", "ageitems", "nationalities",
               "fundnames", "methodnotes", "labels", "meta", "sourcestatus",
               "sourceregister", "updatestatus", "focus", "byregion", "regions"}
# Kun disse nøgler under en opdelingscontainer må åbnes (nationale totaler)
TOTALER = {"tot", "total", "hele landet", "i alt", "national", "danmark"}

MIN_NIVEAU = 100      # serier med lavere typisk niveau tjekkes ikke for spring
SPRING_PCT = 0.30     # mindste relative spring der kan udløse advarsel
SPRING_FAKTOR = 8     # ... og det skal være så mange gange det typiske udsving

fund = []             # (alvor, dashboard, nøgle, tekst); alvor 1=kritisk 2=advarsel
state = {"kørt": NOW.isoformat(), "dashboards": {}}

def hent(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": "dak-vagthund/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()

def flag(alvor, dash, nøgle, tekst):
    fund.append({"alvor": alvor, "dashboard": dash, "nøgle": f"{dash}|{nøgle}", "tekst": tekst})

def periode_dato(p):
    if not isinstance(p, str): return None
    p = p.strip()
    m = re.fullmatch(r"(\d{4})M(\d{1,2})", p)
    if m: return datetime(int(m.group(1)), int(m.group(2)), 28, tzinfo=timezone.utc)
    m = re.fullmatch(r"(\d{4})[KQ](\d{1,2})", p)
    if m: return datetime(int(m.group(1)), min(12, int(m.group(2)) * 3), 28, tzinfo=timezone.utc)
    m = re.fullmatch(r"(\d{4})", p)
    if m: return datetime(int(m.group(1)), 12, 28, tzinfo=timezone.utc)
    return None

_dst = {}
def dst_seneste(tabel):
    if tabel in _dst: return _dst[tabel]
    try:
        _, body = hent(f"https://api.statbank.dk/v1/tableinfo/{tabel}?format=JSON&lang=da", timeout=40)
        d = json.loads(body)
        seneste = None
        for v in d.get("variables", []):
            if v.get("time") and v.get("values"):
                seneste = v["values"][-1]["id"]
        _dst[tabel] = (seneste, d.get("updated"))
    except Exception:
        _dst[tabel] = (None, None)
    return _dst[tabel]

# ---------------- talkontrol af hovedserier ----------------
def tjek_serie(dash, navn, values):
    n = len(values)
    if n < 12: return
    hale = values[-3:]
    tidligere = values[-15:-3]
    if all(v is None for v in hale) and all(v is not None for v in tidligere):
        flag(1, dash, navn, f"{navn}: de seneste 3 datapunkter er tomme, selvom serien ellers er fuld")
        return
    tal = [v for v in values if isinstance(v, (int, float))]
    if len(tal) < 12: return
    if all(v == 0 for v in tal[-3:]) and any(v != 0 for v in tal[-15:-3]):
        flag(1, dash, navn, f"{navn}: de seneste 3 værdier er 0, hvor serien tidligere havde tal")
        return
    niveau = sorted(abs(v) for v in tal[-13:])[6]
    if niveau < MIN_NIVEAU: return
    skridt = [abs(b - a) / abs(a) for a, b in zip(tal[-13:-1], tal[-12:]) if a]
    if len(skridt) < 8: return
    typisk = sorted(skridt[:-1])[len(skridt[:-1]) // 2]
    sidste = skridt[-1]
    if sidste > SPRING_PCT and sidste > max(0.08, SPRING_FAKTOR * typisk):
        f2 = f"{tal[-2]:,.0f}".replace(",", "."); f1 = f"{tal[-1]:,.0f}".replace(",", ".")
        flag(2, dash, navn, f"{navn}: sidste datapunkt ændrer sig {sidste*100:.0f} pct. "
                            f"({f2} -> {f1}), typisk udsving er {typisk*100:.1f} pct.")

def gennemgå(dash, obj, sti="", dybde=0):
    if dybde > 4: return
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in SPRING_OVER:
                if isinstance(v, dict):                      # åbn kun totalen
                    for k2, v2 in v.items():
                        if str(k2).lower() in TOTALER:
                            gennemgå(dash, v2, f"{sti}.{k}.{k2}" if sti else f"{k}.{k2}", dybde + 1)
                continue
            gennemgå(dash, v, f"{sti}.{k}" if sti else str(k), dybde + 1)
    elif isinstance(obj, list):
        if len(obj) >= 12 and all(v is None or isinstance(v, (int, float)) for v in obj):
            tjek_serie(dash, sti, obj)

# ---------------- selvtest (køres uden netværk med --selftest) ----------------
if "--selftest" in sys.argv:
    ren = [1000 + (i % 5) * 10 for i in range(30)]
    gennemgå("T", {"a": {"total": list(ren)}})
    if fund: print("SELVTEST FEJLEDE: falsk alarm på ren serie:", fund); sys.exit(2)
    gennemgå("T", {"a": {"total": ren[:-3] + [None, None, None]},
                   "b": {"total": ren[:-3] + [0, 0, 0]},
                   "c": {"total": ren[:-1] + [ren[-1] * 3]}})
    if len(fund) != 3: print(f"SELVTEST FEJLEDE: fandt {len(fund)} af 3 indbyggede fejl:", fund); sys.exit(2)
    if periode_dato("2026M07") >= periode_dato("2026M08"): print("SELVTEST FEJLEDE: periodesortering"); sys.exit(2)
    print("SELVTEST OK: scriptet fanger huller, nulstilling og spring, og giver ikke falsk alarm.")
    sys.exit(0)

# ---------------- kontrol ----------------
perioder = {}   # dataset -> [(dashboard, periode)]

for d in DASHBOARDS:
    dash, url = d["navn"], BASE + d["repo"] + "/"
    s = state["dashboards"][dash] = {"url": url}
    try:
        st, body = hent(url)
        s["side_status"], s["side_bytes"] = st, len(body)
        if st != 200:
            flag(1, dash, "side", f"Siden svarer HTTP {st}")
        else:
            html = body.decode("utf-8", "replace")
            synlig = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
            if len(body) < d["min_bytes"]:
                flag(1, dash, "side_tom", f"Siden er kun {len(body)} bytes (forventet mindst {d['min_bytes']})")
            if d["repo"] != "arbejdsmarked" and "<canvas" not in html.lower():
                flag(1, dash, "canvas", "Ingen <canvas> på siden, graferne kan mangle")
            for m in ["Der opstod en fejl", "Fejl ved indlæsning", "Kunne ikke hente", "Data mangler"]:
                if m.lower() in synlig.lower():
                    flag(2, dash, "fejltekst", f"Fejltekst på siden: '{m}'"); break
            if d["repo"] == "arbejdsmarked":
                for lnk in sorted(set(re.findall(r'href="(https://ai-michelklos\.github\.io/[^"]+)"', html))):
                    try:
                        stl, _ = hent(lnk, timeout=30)
                        if stl != 200: flag(1, dash, "link:" + lnk, f"Dødt link ({stl}): {lnk}")
                    except Exception as e:
                        flag(1, dash, "link:" + lnk, f"Link kunne ikke hentes: {lnk} ({e})")
    except Exception as e:
        flag(1, dash, "side", f"Siden kunne ikke hentes: {e}")

    if not d["data"]: continue
    try:
        st, body = hent(url + d["data"])
        data = json.loads(body)
    except Exception as e:
        flag(1, dash, "datafil", f"Datafilen kunne ikke læses: {e}")
        continue
    s["data_bytes"] = len(body)
    meta = data.get("meta", {})
    us = meta.get("updateStatus") or {}
    checked = us.get("checkedAt") or meta.get("checkedAt") or meta.get("retrievedAt")
    s["checkedAt"] = checked
    if us.get("state") and us["state"] != "ok":
        flag(1, dash, "updatestatus", f"updateStatus.state = '{us['state']}'"
             + (f", fejlede kilder: {', '.join(map(str, us.get('failed') or []))}" if us.get("failed") else ""))
    elif us.get("failed"):
        flag(1, dash, "failed", f"Kilder fejlede ved seneste hentning: {', '.join(map(str, us['failed']))}")
    if checked:
        try:
            c = datetime.fromisoformat(str(checked).replace("Z", "+00:00"))
            if c.tzinfo is None: c = c.replace(tzinfo=timezone.utc)
            alder = (NOW - c).days
            s["alder_dage"] = alder
            if alder > d.get("max_dage", 9):
                flag(1, dash, "stilstand", f"Data er ikke hentet i {alder} dage (senest {c:%d.%m.%Y}), opdateringen er sandsynligvis gået i stå")
        except Exception:
            pass

    s["kilder"] = {}
    for navn, k in (meta.get("sourceStatus") or meta.get("sourceRegister") or {}).items():
        if not isinstance(k, dict): continue
        ds, per = str(k.get("dataset") or navn), k.get("latestPeriod")
        s["kilder"][navn] = {"dataset": ds, "periode": per, "state": k.get("state")}
        if k.get("state") and k["state"] not in ("ok", "cached"):
            flag(2, dash, "kilde:" + navn, f"Kilde '{navn}' ({ds}) har status '{k['state']}'")
        if not per: continue
        pd = periode_dato(per)
        if pd and pd > NOW:      # fremskrivning, ikke en forsinket kilde
            continue
        perioder.setdefault(ds, []).append((dash, per))
        if "danmarks statistik" in (k.get("source") or "").lower():
            seneste, opdat = dst_seneste(ds)
            sd = periode_dato(seneste) if seneste else None
            if sd and pd and sd > pd and sd <= NOW:
                flag(1, dash, f"dst:{ds}", f"{navn} ({ds}): dashboardet viser {per}, men Statistikbanken har {seneste}"
                                           + (f" (kilden opdateret {str(opdat)[:10]})" if opdat else ""))
    gennemgå(dash, data.get("sections") or data)

for ds, par in sorted(perioder.items()):
    datoer = {p: periode_dato(p) for _, p in par}
    gyldige = {p: dt for p, dt in datoer.items() if dt}
    if len(set(gyldige.values())) > 1:
        nyeste = max(gyldige, key=lambda p: gyldige[p])
        bagud = [f"{dash} ({p})" for dash, p in par if p != nyeste]
        flag(2, "På tværs", f"kryds:{ds}", f"Datasæt {ds}: nyeste periode er {nyeste}, men {', '.join(bagud)} halter bagefter")

# ---------------- sammenlign med forrige kørsel ----------------
ap = argparse.ArgumentParser()
ap.add_argument("--forrige"); ap.add_argument("--state", default="state.json")
a = ap.parse_args()
forrige, kendte = None, {}
if a.forrige:
    try:
        forrige = json.load(open(a.forrige))
        kendte = {f["nøgle"]: f.get("først_set", forrige.get("kørt", "")[:10]) for f in forrige.get("fund", [])}
    except Exception as e:
        print(f"(kunne ikke læse forrige state: {e})", file=sys.stderr)

for f in fund:
    f["først_set"] = kendte.get(f["nøgle"], NOW.strftime("%Y-%m-%d"))
    f["nyt"] = f["nøgle"] not in kendte
løste = []
if forrige:
    nu = {f["nøgle"] for f in fund}
    løste = [f for f in forrige.get("fund", []) if f["nøgle"] not in nu]
    # er et dashboard holdt op med at opdatere siden sidst?
    for dash, gl in forrige.get("dashboards", {}).items():
        ny = state["dashboards"].get(dash, {})
        if gl.get("checkedAt") and ny.get("checkedAt") == gl.get("checkedAt") and (ny.get("alder_dage") or 0) > 8:
            pass  # dækkes allerede af stilstandstjekket
        gb, nb = gl.get("side_bytes"), ny.get("side_bytes")
        if gb and nb and nb < gb * 0.7:
            flag(1, dash, "krympet", f"Siden er krympet fra {gb} til {nb} bytes siden sidste kontrol")

state["fund"] = fund

# ---------------- rapport ----------------
kritiske = [f for f in fund if f["alvor"] == 1]
advarsler = [f for f in fund if f["alvor"] == 2]
nye = [f for f in fund if f.get("nyt")]
if kritiske:   status = "Kræver handling"
elif advarsler: status = "Se efter"
else:          status = "Alt OK"

L = [f"Outputkontrol af dashboards, {NOW.astimezone():%d-%m-%Y kl. %H:%M}", f"Status: {status}", ""]
if not fund:
    L.append("Ingen problemer fundet. Alle sider svarer, data er hentet for nylig, ingen kilder fejlede, og hovedtallene ser rigtige ud.")
for titel, gruppe in (("KRITISK", kritiske), ("ADVARSEL", advarsler)):
    if not gruppe: continue
    L.append(f"{titel} ({len(gruppe)}):")
    for f in gruppe:
        mærke = " [NY]" if f.get("nyt") else f" [kendt siden {f['først_set']}]"
        L.append(f"  - {f['dashboard']}: {f['tekst']}{mærke}")
    L.append("")
if løste:
    L.append(f"Løst siden sidste kontrol ({len(løste)}):")
    for f in løste: L.append(f"  - {f['dashboard']}: {f['tekst']}")
    L.append("")
L.append("Kontrolleret:")
for dash, s in state["dashboards"].items():
    bid = f"side {s.get('side_status','-')} ({s.get('side_bytes','-')} bytes)"
    if s.get("checkedAt"): bid += f", data hentet {str(s['checkedAt'])[:16].replace('T',' kl. ')}"
    else: bid += ", ingen separat datafil"
    L.append(f"  - {dash}: {bid}")
L += ["", "Jobindsats-API'et kræver token og kan ikke spørges direkte. Jobindsats-kilder vurderes",
      "derfor på krydstjek mellem dashboards og på om hentningen kører. DST-kilder sammenlignes",
      "direkte med Statistikbanken."]

rapport = "\n".join(L)
print(rapport)
state["status"] = status
state["rapport"] = rapport
json.dump(state, open(a.state, "w"), ensure_ascii=False, indent=1)
