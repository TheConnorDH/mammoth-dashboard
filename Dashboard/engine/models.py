"""Statistical layer: standard errors, 95% significance, Poisson game model, season simulation,
empirical-Bayes shrinkage of player value. Parameters come from validate.py (config/model_params.json)."""
import math, random

Z95 = 1.96


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------ team metric standard errors
def team_se(sits, ep2):
    """Return {metric_key: standard error} for the team's current values (event-level randomness)."""
    a, e, pp, pk = sits.get("all"), sits.get("5on5"), sits.get("5on4"), sits.get("4on5")
    se = {}
    if not a:
        return se
    g = lambda r, k: num(r[k]) if r else 0.0
    gp = max(1.0, g(a, "games_played"))
    se["gf_pg"] = math.sqrt(max(g(a, "goalsFor"), 1)) / gp
    se["ga_pg"] = math.sqrt(max(g(a, "goalsAgainst"), 1)) / gp
    def prop(p, n):
        return math.sqrt(max(p * (1 - p), 1e-6) / n) if n else None
    sf, sa = g(a, "shotsOnGoalFor"), g(a, "shotsOnGoalAgainst")
    se["sh_pct"] = prop(g(a, "goalsFor") / sf if sf else .1, sf)
    se["sv_pct"] = prop(1 - g(a, "goalsAgainst") / sa if sa else .9, sa)
    se["reb_rate_for"] = math.sqrt(max(g(a, "reboundsFor"), 1)) / sf if sf else None
    se["reb_rate_against"] = math.sqrt(max(g(a, "reboundsAgainst"), 1)) / sa if sa else None
    gf = g(a, "goalsFor")
    se["reb_goal_share"] = prop(g(a, "reboundGoalsFor") / gf if gf else .12, gf) if gf else None
    hrs_a = g(a, "iceTime") / 3600
    se["reb_ga_60"] = math.sqrt(max(g(a, "reboundGoalsAgainst"), 1)) / hrs_a if hrs_a else None
    fw, fl = g(a, "faceOffsWonFor"), g(a, "faceOffsWonAgainst")
    se["fo_pct"] = prop(fw / (fw + fl) if fw + fl else .5, fw + fl)
    if e:
        hrs = g(e, "iceTime") / 3600
        F, A = g(e, "xGoalsFor"), g(e, "xGoalsAgainst")
        vF, vA = g(e, "unblockedShotAttemptsFor") * ep2["5on5"], g(e, "unblockedShotAttemptsAgainst") * ep2["5on5"]
        se["xgf_pct_5v5"] = math.sqrt(A * A * vF + F * F * vA) / (F + A) ** 2 if F + A else None
        cf, ca = g(e, "shotAttemptsFor"), g(e, "shotAttemptsAgainst")
        se["cf_pct_5v5"] = prop(cf / (cf + ca) if cf + ca else .5, cf + ca)
        hf, ha = g(e, "highDangerShotsFor"), g(e, "highDangerShotsAgainst")
        se["hd_share_5v5"] = prop(hf / (hf + ha) if hf + ha else .5, hf + ha)
        se["xgf60_5v5"] = math.sqrt(vF) / hrs if hrs else None
        se["xga60_5v5"] = math.sqrt(vA) / hrs if hrs else None
        se["blocked_share_5v5"] = prop(g(e, "blockedShotAttemptsFor") / cf if cf else .28, cf)
    if pp and num(pp["iceTime"]) > 0:
        hrs = g(pp, "iceTime") / 3600
        se["pp_xgf60"] = math.sqrt(g(pp, "unblockedShotAttemptsFor") * ep2["5on4"]) / hrs
        se["pp_gf60"] = math.sqrt(max(g(pp, "goalsFor"), 1)) / hrs
        se["pp_sog60"] = math.sqrt(max(g(pp, "shotsOnGoalFor"), 1)) / hrs
        se["pp_reb60"] = math.sqrt(max(g(pp, "reboundsFor"), 1)) / hrs
        pw, pl = g(pp, "faceOffsWonFor"), g(pp, "faceOffsWonAgainst")
        se["pp_fo_pct"] = prop(pw / (pw + pl) if pw + pl else .54, pw + pl)
    if pk and num(pk["iceTime"]) > 0:
        hrs = g(pk, "iceTime") / 3600
        se["pk_xga60"] = math.sqrt(g(pk, "unblockedShotAttemptsAgainst") * ep2["4on5"]) / hrs
        se["pk_dzgive60"] = math.sqrt(max(g(pk, "dZoneGiveawaysFor"), 1)) / hrs
        se["pk_rebga60"] = math.sqrt(max(g(pk, "reboundGoalsAgainst"), 1)) / hrs
    return {k: v for k, v in se.items() if v}


def significance(cur, ref, se, hib):
    """Classify Utah's value vs. the league-average reference at 95%."""
    if cur is None or ref is None or not se or hib is None:
        return {"z": None, "label": "n/a"}
    z = (cur - ref) / se
    good = z if hib else -z
    if good >= Z95:
        lab = "confirmed strength"
    elif good <= -Z95:
        lab = "confirmed weakness"
    elif good >= 1.0:
        lab = "leaning strength"
    elif good <= -1.0:
        lab = "leaning weakness"
    else:
        lab = "not yet distinguishable"
    return {"z": round(z, 2), "label": lab}


# ------------------------------------------------------------------ Poisson game model
def _pois(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


TIE_F = 1.0   # calibrated in build: inflates Poisson tie probability to match the league's real OT rate


def game_point_probs(lf, la, ot_win=0.5):
    """P(regulation win), P(regulation loss), P(tie after regulation) for Poisson goal rates,
    with ties inflated by TIE_F (teams play tighter when tied late; plain Poisson under-counts OT)."""
    pw = pl = pt = 0.0
    for i in range(16):
        pi = _pois(lf, i)
        for j in range(16):
            p = pi * _pois(la, j)
            if i > j: pw += p
            elif i < j: pl += p
            else: pt += p
    t2 = min(0.6, pt * TIE_F)
    scale = (1 - t2) / (1 - pt) if pt < 1 else 1
    return pw * scale, pl * scale, t2


def calibrate_ties(gpg, league_pts_pct):
    """Solve TIE_F so an average team's expected points % equals the league's actual points %."""
    global TIE_F
    lo, hi = 0.5, 3.0
    for _ in range(40):
        TIE_F = (lo + hi) / 2
        if expected_points(gpg / 2, gpg / 2) / 2 < league_pts_pct: lo = TIE_F
        else: hi = TIE_F
    return round(TIE_F, 3)


def expected_points(lf, la, ot_win=0.5):
    pw, pl, pt = game_point_probs(lf, la)
    return 2 * pw + pt * (1 + ot_win)


def deserved_points(xgf, xga, gp):
    """Expected standings points from shot quality: each game played at the season's xG rates."""
    if not gp or not xgf or not xga:
        return None
    return round(gp * expected_points(xgf / gp, xga / gp), 1)


# ------------------------------------------------------------------ season simulation
def simulate_season(cur_pts, gp, n_games, share_mean, share_sd, goals_per_game, line_mean, line_sd, sims=10000, seed=7):
    """Monte Carlo of the remaining schedule. Each sim draws a true goal share from the posterior,
    plays the remaining games with Poisson scoring (OT/SO coin flip), and compares the final total
    with a playoff line drawn from its historical distribution."""
    rng = random.Random(seed)
    remaining = n_games - gp
    finals, made = [], 0
    cache = {}
    for _ in range(sims):
        s = min(0.75, max(0.25, rng.gauss(share_mean, share_sd)))
        key = round(s, 3)
        if key not in cache:
            cache[key] = game_point_probs(goals_per_game * s, goals_per_game * (1 - s))
        pw, pl, pt = cache[key]
        pts = cur_pts
        for _ in range(remaining):
            u = rng.random()
            if u < pw: pts += 2
            elif u < pw + pt: pts += 2 if rng.random() < 0.5 else 1
        finals.append(pts)
        if pts > rng.gauss(line_mean, line_sd):
            made += 1
    finals.sort()
    q = lambda p: finals[int(p * (len(finals) - 1))]
    return {"mean": round(sum(finals) / len(finals), 1), "lo95": q(0.025), "hi95": q(0.975), "lo50": q(0.25), "hi50": q(0.75),
            "p_playoff": round(made / sims, 3), "hist": _hist(finals)}


def _hist(vals, width=2):
    lo, hi = min(vals), max(vals)
    bins = {}
    for v in vals:
        b = int((v - lo) // width) * width + lo
        bins[b] = bins.get(b, 0) + 1
    return [{"x": k, "n": bins[k]} for k in sorted(bins)]


def posterior_share(prior_mean, prior_sd, obs, obs_se):
    if obs is None or not obs_se:
        return prior_mean, prior_sd
    w0, w1 = 1 / prior_sd ** 2, 1 / obs_se ** 2
    m = (prior_mean * w0 + obs * w1) / (w0 + w1)
    return m, math.sqrt(1 / (w0 + w1))


# ------------------------------------------------------------------ player shrinkage
def shrink_player(p, rel):
    """Empirical-Bayes talent estimate: each component scaled by reliability t/(t+k) from history."""
    table = rel.get(p["grp"], {})
    t = p["toi"]
    out = 0.0
    for c, v in p["comp"].items():
        k = table.get(c, {}).get("k_min")
        if k is None:
            continue
        out += v * t / (t + k)
    return round(out, 2)


# ------------------------------------------------------------------ calibrated team significance
def team_posterior(x, lg_mean, n_games, tr, hib):
    """True-score model calibrated on 18 seasons: how far Utah's TRUE level sits from league average,
    given n games of evidence. Captures every noise source (schedule, score effects, luck), not just
    shot randomness, because the noise is measured from real season-to-season carry-over."""
    if x is None or lg_mean is None or not tr or not n_games or hib is None:
        return {"z": None, "label": "n/a"}
    noise_n = tr["noise_full"] * tr["gp_ref"] / n_games
    relv = tr["var_true"] / (tr["var_true"] + noise_n)
    dev = relv * (x - lg_mean)
    sd = math.sqrt(tr["var_true"] * (1 - relv))
    z = dev / sd if sd else 0
    good = z if hib else -z
    lab = ("confirmed strength" if good >= Z95 else "confirmed weakness" if good <= -Z95 else
           "leaning strength" if good >= 1.0 else "leaning weakness" if good <= -1.0 else "not yet distinguishable")
    return {"z": round(z, 2), "label": lab, "rel": round(relv, 3), "talent": lg_mean + dev,
            "lo": lg_mean + dev - Z95 * sd, "hi": lg_mean + dev + Z95 * sd}


# ------------------------------------------------------------------ pooled player talent (two seasons)
def player_talent(cur, prev, rel):
    """Pool this season with last season (minutes-weighted per component), then regress each
    component toward the position average by its measured reliability. Returns per-60 talent and
    a 95% interval from the true-talent spread measured on 18 seasons."""
    table = rel.get(cur["grp"], {})
    t_cur = cur["toi"]; t_prev = prev["toi"] if prev and prev["grp"] == cur["grp"] else 0.0
    T = t_cur + t_prev
    if T <= 0:
        return None
    rate = 0.0
    for c in set(cur["comp"]) | (set(prev["comp"]) if t_prev else set()):
        k = table.get(c, {}).get("k_min")
        if k is None:
            continue
        tot = cur["comp"].get(c, 0.0) + (prev["comp"].get(c, 0.0) if t_prev else 0.0)
        rate += (tot / T * 60) * T / (T + k)
    tt = table.get("total", {})
    k_tot, vt = tt.get("k_min", 1500), tt.get("var_true60", 0.02)
    rel_tot = T / (T + k_tot)
    sd = math.sqrt(vt * (1 - rel_tot))
    return {"rate60": rate, "lo60": rate - Z95 * sd, "hi60": rate + Z95 * sd, "minutes": T, "rel": rel_tot}
