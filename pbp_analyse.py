"""Relie chaque réponse de e8 à l'écriture qui l'a provoquée (même commande, la plus récente avant la réponse), puis
liste les réponses autres que le refus 02. Arguments : ligne de départ du journal."""
import re, sys, os
D = os.path.dirname(os.path.abspath(__file__))
n0 = int(sys.argv[1]) if len(sys.argv) > 1 else 0
lignes = open(os.path.join(D, "pbp_banc.log"), encoding="cp1252", errors="replace").read().splitlines()[n0:]
ecr, rep = [], []
for l in lignes:
    m = re.match(r"\[\s*([\d.]+)\] (?:ÉCRIT|.CRIT) e7 : (.*)", l)
    if m:
        b = m.group(2).split(); ecr.append((float(m.group(1)), b)); continue
    m = re.match(r"\[\s*([\d.]+)\] NOTIF a23e8 : (.*)", l)
    if m: rep.append((float(m.group(1)), m.group(2).split()))
pris = set()
for t, b in rep:
    # la réponse arrive environ 1,2 s après sa commande : la commande non prise la plus proche de t - 1,2 (même numéro
    # pour un refus ou un succès, qui le rappellent)
    cand = [k for k, (tw, w) in enumerate(ecr) if tw < t - 0.15 and k not in pris and (b[0] != "01" or w[0] == b[3])]
    if not cand: print("?", t, " ".join(b)); continue
    k = min(cand, key=lambda k: abs(ecr[k][0] - (t - 1.2))); pris.add(k)
    tw, w = ecr[k]
    if b[0] == "01" and b[4] == "02": continue
    print(f"{tw:8.2f} cmd {w[0]} long {int(w[1], 16):3d} : {' '.join(w[:12])}{' …' if len(w) > 12 else ''}  ->  {' '.join(b)}")
print(len(ecr), "écritures,", len(rep), "réponses")
if "-p" in sys.argv:
    print("sans réponse :", " ".join(f"{w[0]}/{int(w[1], 16)}" for k, (tw, w) in enumerate(ecr) if k not in pris))
