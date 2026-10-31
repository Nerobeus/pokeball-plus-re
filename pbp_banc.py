"""Banc d'essai de la Poké Ball Plus par le Bluetooth du PC : connexion gardée, toutes les notifications journalisées,
commandes lues dans pbp_cmd.txt (une par ligne, ajoutées à la fin) :
  w CAR HEX     écriture sans réponse (CAR : suffixe court de la caractéristique, ex. e7, aec)
  wr CAR HEX    écriture avec réponse
  r CAR         lecture
  n CAR         abonnement
  p SECONDES    pause
  q             fin
Boutons de la balle journalisés à chaque changement (octet 1 de e6) : le haut sert de marque « ça a réagi »."""
import asyncio, os, sys, time
from bleak import BleakScanner, BleakClient

ICI = os.path.dirname(os.path.abspath(__file__))
CMD = os.path.join(ICI, "pbp_cmd.txt")
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:7.2f}]", *a, flush=True)


POS = [0]
SUITE = [None]
ATTENTE = [None]
ESSAI = [None]


async def main():
    open(CMD, "w").close()
    while True:
        if await session() == "q": return


async def session():
    dev = None
    while not dev:
        log("recherche (appuyer sur le bouton de la balle)")
        dev = await BleakScanner.find_device_by_filter(lambda d, a: (a.local_name or d.name or "").startswith("Pokemon"), timeout=15)
    async with BleakClient(dev, disconnected_callback=lambda c: log("DÉCONNECTÉE")) as c:
        log("connectée", dev.address)
        chars = {}
        for s in c.services:
            for ch in s.characteristics:
                chars[ch.uuid] = ch

        def car(suf):
            m = [ch for u, ch in chars.items() if u.endswith(suf.lower())]
            if len(m) != 1: raise ValueError(f"caractéristique {suf} : {len(m)} candidates")
            return m[0]

        boutons = [None]

        def e6(_, b):
            if len(b) > 1 and b[1] != boutons[0]:
                if boutons[0] == 0 and b[1] and SUITE[0]:   # mode suite : chaque appui envoie la trame suivante
                    t, i, fin = SUITE[0]
                    if i <= fin:
                        SUITE[0] = (t, i + 1, fin)
                        data = bytes.fromhex(t.replace("{i}", f"{i:02x}"))
                        asyncio.get_running_loop().create_task(c.write_gatt_char(car("a23e7"), data, response=False))
                        log(f"APPUI -> n° {i} : {data.hex(' ')}")
                boutons[0] = b[1]
                log(f"BOUTONS {b[1]:02x}")

        def notif(nom):
            def f(_, b):
                if ESSAI[0] and not ESSAI[0].done():
                    ESSAI[0].set_result(bytes(b)); return
                if ATTENTE[0] and len(b) >= 11 and b[0] == ATTENTE[0][0] and b[3:7] == ATTENTE[0][1]:
                    fut = ATTENTE[0][2]
                    if not fut.done(): fut.set_result(bytes(b[11:]))
                    return
                if ATTENTE[0] and len(b) == 5 and b[0] == 1 and b[3] == ATTENTE[0][3]:   # refus de la lecture attendue
                    fut = ATTENTE[0][2]
                    if not fut.done(): fut.set_result(b[4])
                log(f"NOTIF {nom} : {b.hex(' ')}")
            return f

        async def lire(op, type_rep, pos, taille):
            """Lecture d'une zone (09 : application, 0b : mémoire) ; réponse ou code d'erreur ; 4 essais"""
            for essai in range(4):
                fut = asyncio.get_running_loop().create_future()
                ATTENTE[0] = (type_rep, pos.to_bytes(4, "little"), fut, op)
                trame = bytes([op, 8, 0]) + pos.to_bytes(4, "little") + taille.to_bytes(4, "little")
                await c.write_gatt_char(car("a23e7"), trame, response=False)
                try:
                    return await asyncio.wait_for(fut, 3.0)
                except asyncio.TimeoutError:
                    pass
                finally:
                    ATTENTE[0] = None
            return None

        await c.start_notify(car("a23e6"), e6)
        for suf in ("a23e8",):
            try:
                await c.start_notify(car(suf), notif(suf))
            except Exception as e:
                log(f"abonnement {suf} refusé : {e}")
        log("prête")
        while c.is_connected:
            with open(CMD) as f:
                f.seek(POS[0])
                lignes = f.readlines()
                POS[0] = f.tell()
            for l in lignes:
                m = l.split()
                if not m: continue
                try:
                    if m[0] == "q": return "q"
                    if m[0] == "p": await asyncio.sleep(float(m[1])); continue
                    if m[0] == "copie":   # copie OP DEBUT FIN TAILLE FICHIER (hexa) : lectures en suite dans le fichier
                        op, deb, fin, t = (int(x, 16) for x in m[1:5])
                        with open(os.path.join(ICI, m[5]), "ab") as f:
                            pos = deb
                            while pos < fin and c.is_connected:
                                r = await lire(op, {0x09: 5, 0x0b: 6}[op], pos, min(t, fin - pos))
                                if isinstance(r, bytes):
                                    f.write(r); f.flush(); pos += len(r)
                                    if (pos - deb) % 0x1000 < len(r): log(f"copie {op:02x} : {pos:06x}")
                                    if not r: log("copie : réponse vide"); break
                                else:
                                    log(f"copie {op:02x} : arrêt à {pos:06x} ({'sans réponse' if r is None else f'code {r}'})"); break
                        log("copie finie"); continue
                    if m[0] == "sonde":   # sonde OP POS... : 16 octets lus à chaque position
                        op = int(m[1], 16)
                        for x in m[2:]:
                            r = await lire(op, {0x09: 5, 0x0b: 6}[op], int(x, 16), 16)
                            log(f"sonde {op:02x} {x} : {r.hex(' ') if isinstance(r, bytes) else r}")
                        continue
                    if m[0] == "essais":   # essais FICHIER : une trame hexa par ligne, réponse attendue (2 essais)
                        for t in open(os.path.join(ICI, m[1])).read().splitlines():
                            if not t.strip() or not c.is_connected: continue
                            data = bytes.fromhex(t); r = None
                            for _ in range(2):
                                ESSAI[0] = asyncio.get_running_loop().create_future()
                                await c.write_gatt_char(car("a23e7"), data, response=False)
                                try:
                                    r = await asyncio.wait_for(ESSAI[0], 3.0); break
                                except asyncio.TimeoutError:
                                    pass
                            ESSAI[0] = None
                            log(f"ESSAI {data[:16].hex(' ')}{' …' if len(data) > 16 else ''} ({len(data) - 3}) -> {r.hex(' ') if r else 'rien'}")
                        log("essais finis"); continue
                    if m[0] == "suite":   # suite DEBUT FIN HEX... avec {i}
                        SUITE[0] = (" ".join(m[3:]), int(m[1]), int(m[2])); log(f"suite {SUITE[0]}"); continue
                    ch = car(m[1])
                    if m[0] in ("w", "wr"):
                        data = bytes.fromhex("".join(m[2:]))
                        await c.write_gatt_char(ch, data, response=(m[0] == "wr"))
                        log(f"ÉCRIT {m[1]} : {data.hex(' ')}")
                    elif m[0] == "r":
                        log(f"LU {m[1]} : {(await c.read_gatt_char(ch)).hex(' ')}")
                    elif m[0] == "n":
                        await c.start_notify(ch, notif(m[1])); log(f"abonné {m[1]}")
                except Exception as e:
                    log(f"ERREUR {l.strip()} : {e}")
            await asyncio.sleep(0.1)

asyncio.run(main())
