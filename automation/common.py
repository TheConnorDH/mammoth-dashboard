"""Shared helpers for the daily pipeline: paths, polite HTTP with retries, logging."""
import os, sys, time, json, io, zipfile, http.client, urllib.request, urllib.error, datetime as dt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = os.path.join(REPO, "Dashboard")
SRC = os.path.join(REPO, "Source Data")          # last season's MoneyPuck season files (build.py reads ../Source Data)
TEAM = "UTA"
SEASON = 2026                                     # MoneyPuck season key (2026 = 2026-27)
NHL_SEASON = "20262027"
UA = "Mammoth-dashboard/1.0 (personal, non-commercial; once-daily update; credits MoneyPuck.com)"


def P(*a):
    return os.path.join(DASH, *a)


def log(*a):
    print("[%s]" % dt.datetime.utcnow().strftime("%H:%M:%S"), *a, flush=True)


def get(url, tries=4, timeout=90, binary=False):
    """GET with retries and backoff. Raises on final failure."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            return data if binary else data.decode("utf-8")
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError, OSError, UnicodeDecodeError) as e:
            last = e
            log(f"  retry {i + 1}/{tries} {url}: {e}")
            time.sleep(5 * (i + 1) ** 2)
    raise RuntimeError(f"download failed: {url}: {last}")


def get_json(url, tries=4, **kw):
    for i in range(tries):
        t = get(url, tries=tries, **kw)
        try:
            return json.loads(t)
        except ValueError as e:                     # truncated body: try again
            log(f"  bad JSON {url}: {e}"); time.sleep(5 * (i + 1))
    raise RuntimeError(f"bad JSON from {url}")


def unzip_single_csv(blob):
    """MoneyPuck zips hold one CSV; return its text."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    names = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX") and not os.path.basename(n).startswith("._")]
    if len(names) != 1:
        raise RuntimeError(f"expected one CSV in zip, found {names}")
    return z.read(names[0]).decode("utf-8")


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def write_json(path, obj, indent=1):
    write_text(path, json.dumps(obj, indent=indent, ensure_ascii=False))


def mountain_today():
    """Today's date in Utah (UTC-7 standard / UTC-6 daylight; DST approximated by US rules)."""
    now = dt.datetime.utcnow()
    y = now.year
    # second Sunday in March, first Sunday in November (2am local ~ 9am/8am UTC; close enough for a morning job)
    mar = dt.datetime(y, 3, 8); dst_start = mar + dt.timedelta(days=(6 - mar.weekday()) % 7, hours=9)
    nov = dt.datetime(y, 11, 1); dst_end = nov + dt.timedelta(days=(6 - nov.weekday()) % 7, hours=8)
    off = 6 if dst_start <= now < dst_end else 7
    return (now - dt.timedelta(hours=off)).date()
