"""Season simulation for every team from power ratings + home ice (validated win/OT model; config/winprob_params.json).
Each simulated season draws every team's true strength once (from its rating and uncertainty), then plays
every remaining game: P(home win) = logistic(a + b*diff), P(overtime) = logistic(c + d*|diff|),
P(home win | OT) = logistic(e + f*diff); OT/shootout loser gets 1 point.
With `series` (params/playoff_params.json + elite counts), each simulated season also plays out the playoffs:
NHL bracket (top 3 per division + 2 wild cards; the better division winner meets the second wild card), every
series P(A wins) = average over the blended models of logistic(alpha * (b_power * strength gap + b_elite * capped elite gap)). The series strength is the
same draw as the season's, scaled to the end-of-season uncertainty the series model was fitted and backtested on."""
import numpy as np


def _lg(x):
    return 1 / (1 + np.exp(-x))


def game_probs(diff, wp):
    a, b = wp["win"]; c, d = wp["ot"]; e, f = wp["otwin"]
    pwin = _lg(a + b * diff); pot = _lg(c + d * np.abs(diff)); potw = _lg(e + f * diff)
    p_reg_home = np.clip(pwin - pot * potw, 0, 1)
    return p_reg_home, pot, potw


def simulate(ratings, sds, points, remaining, wp, conf=None, div=None, sims=10000, seed=11, series=None, points3=None):
    """points3: current points under 3-2-1-0 (regulation win 3, OT/SO win 2, OT/SO loss 1). When given, the same simulated
    games are also scored that way and playoff, division and seed odds are reported for both systems (out[t]['alt'])."""
    teams = sorted(ratings)
    ix = {t: i for i, t in enumerate(teams)}
    rng = np.random.default_rng(seed)
    true = np.array([ratings[t] for t in teams])[None, :] + rng.normal(size=(sims, len(teams))) * np.array([sds[t] for t in teams])[None, :]
    pts = np.tile(np.array([points.get(t, 0) for t in teams], float), (sims, 1))
    pts3 = np.tile(np.array([points3.get(t, 0) for t in teams], float), (sims, 1)) if points3 is not None else None
    for g in remaining:
        h, a = g[0], g[1]; shift = g[2] if len(g) > 2 else 0.0     # shift: rest (back-to-back) edge, in rating-difference units
        if h not in ix or a not in ix:
            continue
        i, j = ix[h], ix[a]
        diff = true[:, i] - true[:, j] + shift
        preg, pot, potw = game_probs(diff, wp)
        u = rng.random(sims); v = rng.random(sims)
        reg_home = u < preg
        ot = (u >= preg) & (u < preg + pot)
        ot_home = ot & (v < potw)
        reg_away = ~reg_home & ~ot
        pts[:, i] += 2 * reg_home + 2 * ot_home + 1 * (ot & ~ot_home)
        pts[:, j] += 2 * reg_away + 2 * (ot & ~ot_home) + 1 * ot_home
        if pts3 is not None:
            pts3[:, i] += 3 * reg_home + 2 * ot_home + 1 * (ot & ~ot_home)
            pts3[:, j] += 3 * reg_away + 2 * (ot & ~ot_home) + 1 * ot_home
    out = {t: {"mean": float(pts[:, ix[t]].mean()), "lo95": float(np.percentile(pts[:, ix[t]], 2.5)), "hi95": float(np.percentile(pts[:, ix[t]], 97.5)),
               "lo50": float(np.percentile(pts[:, ix[t]], 25)), "hi50": float(np.percentile(pts[:, ix[t]], 75)),
               "lo80": float(np.percentile(pts[:, ix[t]], 10)), "hi80": float(np.percentile(pts[:, ix[t]], 90))} for t in teams}
    def qualify(P_, tie):
        """playoff spots, division winners, conference cut line and seed slots (NHL format) for a points matrix"""
        score = P_ + tie
        made = np.zeros_like(P_, bool); divwin = np.zeros_like(P_, bool); cut = {}; seedc = np.zeros((len(teams), 8))
        for cf in set(conf.values()):
            members = [t for t in teams if conf.get(t) == cf]
            divs = sorted({div[t] for t in members})
            top3 = np.zeros_like(P_, bool)
            for dv in divs:
                dm = [ix[t] for t in members if div[t] == dv]
                order = np.argsort(-score[:, dm], axis=1)
                for k in range(min(3, len(dm))):
                    top3[np.arange(sims), np.array(dm)[order[:, k]]] = True
                divwin[np.arange(sims), np.array(dm)[order[:, 0]]] = True
            cm = np.array([ix[t] for t in members])
            rest = np.where(top3[:, cm], -1e9, score[:, cm])
            order = np.argsort(-rest, axis=1)
            wc = np.zeros_like(P_, bool)
            for k in range(2):
                wc[np.arange(sims), cm[order[:, k]]] = True
            made |= top3 | wc
            last_in = np.where(made[:, cm], P_[:, cm], np.inf).min(axis=1)
            cut[cf] = {"median": float(np.median(last_in)), "mean": float(last_in.mean()),
                       "lo80": float(np.percentile(last_in, 10)), "hi80": float(np.percentile(last_in, 90))}
            # conference seed 1-8 by points among the 8 playoff teams (for the projected-seeding view)
            sc_in = np.where(made[:, cm], score[:, cm], -1e9)
            rk = np.argsort(-sc_in, axis=1)
            nmade = made[:, cm].sum(axis=1)
            for k in range(8):
                ok = nmade > k          # only playoff teams get a seed slot
                np.add.at(seedc, cm[rk[ok, k]], np.eye(8)[k])
        return made, divwin, cut, score, seedc / sims
    if conf and div:
        tie = rng.random(pts.shape) * 0.01
        made, divwin, cut, score, seedc = qualify(pts, tie)
        for t in teams:
            out[t]["playoff"] = float(made[:, ix[t]].mean()); out[t]["division"] = float(divwin[:, ix[t]].mean())
            out[t]["seed"] = [round(float(x), 4) for x in seedc[ix[t]]]
        if pts3 is not None:
            made3, divwin3, cut3, _, seedc3 = qualify(pts3, tie)
            for t in teams:
                k = ix[t]
                out[t]["alt"] = {"mean": float(pts3[:, k].mean()), "lo80": float(np.percentile(pts3[:, k], 10)), "hi80": float(np.percentile(pts3[:, k], 90)),
                                 "playoff": float(made3[:, k].mean()), "division": float(divwin3[:, k].mean()), "seed": [round(float(x), 4) for x in seedc3[k]]}
            out["_cut3"] = cut3
        out["_cut"] = cut
        if series:
            out["_playoffs"] = _playoffs(teams, ix, conf, div, score, true, ratings, sds, series, rng)
        out["_hist"] = {t: np.bincount(pts[:, ix[t]].astype(int), minlength=200)[:200].tolist() for t in teams}
    return out


def _playoffs(teams, ix, conf, div, score, true, ratings, sds, S, rng):
    """Round-by-round odds from the simulated standings. S: b_power, b_elite, alpha, elite {team: n}, tv_end."""
    n_sims, n = score.shape
    rat = np.array([ratings[t] for t in teams]); sd = np.array([sds[t] for t in teams])
    k = np.sqrt(np.clip(sd ** 2 - S["tv_end"], 0, None)) / np.where(sd > 0, sd, 1)
    strength = rat[None, :] + (true - rat[None, :]) * k[None, :]
    E0 = np.array([S["elite"].get(t, 0) for t in teams], float)
    # series model: the average of the listed models (each logistic in power gap + capped elite gap), scaled by alpha
    MODELS = S.get("blend") or [{"b_power": S["b_power"], "b_elite": S["b_elite"], "elite_cap": S.get("elite_cap", 99)}]
    MS = [(S["alpha"] * m["b_power"], S["alpha"] * m["b_elite"], np.minimum(E0, m.get("elite_cap", 99))) for m in MODELS]
    cnt = np.zeros((n, 5)); seeds = np.zeros((n, 5)); opp = np.zeros((n, n))
    u = rng.random((n_sims, 15))
    confs = sorted(set(conf.values()))
    members = {cf: [ix[t] for t in teams if conf.get(t) == cf] for cf in confs}
    divs = {cf: sorted({div[t] for t in teams if conf.get(t) == cf}) for cf in confs}
    dmem = {dv: [ix[t] for t in teams if div.get(t) == dv] for dv in set(div.values())}
    for s_ in range(n_sims):
        sc = score[s_]; st = strength[s_]; k_ = 0
        def play(i, j):
            nonlocal k_
            p = sum(1 / (1 + np.exp(-(bp * (st[i] - st[j]) + be * (E[i] - E[j])))) for bp, be, E in MS) / len(MS); w = i if u[s_, k_] < p else j; k_ += 1; return w
        champs = []
        for cf in confs:
            tops = {dv: sorted(dmem[dv], key=lambda i: -sc[i])[:3] for dv in divs[cf]}
            used = {i for v in tops.values() for i in v}
            wc = sorted([i for i in members[cf] if i not in used], key=lambda i: -sc[i])[:2]
            d1, d2 = sorted(divs[cf], key=lambda dv: -sc[tops[dv][0]])
            for dv in (d1, d2):
                for r_, i in enumerate(tops[dv]): seeds[i, r_] += 1
            seeds[wc[0], 3] += 1; seeds[wc[1], 4] += 1
            ms = [(tops[d1][0], wc[1]), (tops[d1][1], tops[d1][2]), (tops[d2][0], wc[0]), (tops[d2][1], tops[d2][2])]
            for a, b in ms:
                cnt[a, 0] += 1; cnt[b, 0] += 1; opp[a, b] += 1; opp[b, a] += 1
            w1 = [play(a, b) for a, b in ms]
            for i in w1: cnt[i, 1] += 1
            w2 = [play(w1[0], w1[1]), play(w1[2], w1[3])]
            for i in w2: cnt[i, 2] += 1
            c = play(w2[0], w2[1]); cnt[c, 3] += 1; champs.append(c)
        cnt[play(champs[0], champs[1]), 4] += 1
    out = {}
    for t in teams:
        i = ix[t]; made = cnt[i, 0]
        top_opp = sorted([(opp[i, j] / max(made, 1), teams[j]) for j in range(n) if opp[i, j] > 0], reverse=True)[:3]
        out[t] = {"make": round(made / n_sims, 4), "r1": round(cnt[i, 1] / n_sims, 4), "r2": round(cnt[i, 2] / n_sims, 4), "final": round(cnt[i, 3] / n_sims, 4),
                  "cup": round(cnt[i, 4] / n_sims, 4), "cupIfIn": round(cnt[i, 4] / made, 4) if made else None,
                  "seeds": [round(x / n_sims, 4) for x in seeds[i]], "r1opp": [[o, round(p, 3)] for p, o in top_opp]}
    return out
