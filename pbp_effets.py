"""Effets sur mesure de la Poké Ball Plus pour les jeux de la montre : motifs de lumière, vibrations (sinusoïdes de
200 Hz, la fréquence du vibreur de la balle, en WAV MS-ADPCM 8 kHz) et activités qui les réunissent, écrits dans la
base de la balle (README.md). Produit un fichier de trames pour `essais` de pbp_banc.py, et les WAV des vibrations.

    python pbp_effets.py [--vibrations] [--activites 79,100] [sortie.txt]

--vibrations ajoute les trois sons (jeu 0, n° 24 à 26) : seulement s'ils manquent, car la flash ne s'écrit que sur un
emplacement vierge (vérifier d'abord : `88` de l'emplacement = CRC de 8 Ko de ff). --activites n'écrit que ces
activités et leurs motifs (ajout à une balle qui a déjà les autres). Les numéros des activités (ACT0 + effet, et
ACT_AMBIANCE) sont ceux de engine/platform/esp32/main/manette.c et de l'ordre ENG_EFFET_* du moteur."""
import io, os, struct, sys, zlib
import numpy as np
import soundfile as sf

ICI = os.path.dirname(os.path.abspath(__file__))
SR = 8000
ACT0 = 70                     # activités 70 à 79
ACT_AMBIANCE = 100            # lumière d'ambiance
ACT_ETEINT = 101              # LED éteinte (la montre la joue en lâchant la balle)
K, BLANC, ROUGE = (0, 0, 0), (15, 15, 15), (15, 0, 0)
CYAN = (2, 14, 15)            # 0x22E4FF, teinte NÉON de l'interface d'Echoes (THEMES de hud.c), sur 4 bits

# Vibrations : jeu 0, emplacement -> segments (durée s, amplitude) d'un 200 Hz ; rampes de 5 ms à chaque bord
VIBRATIONS = {
    24: [(0.08, 0.9), (0.02, 0)],                          # coup sec
    25: [(0.07, 0.9), (0.09, 0), (0.07, 0.9), (0.02, 0)],  # double coup
    26: 'longue',                                         # 0,7 s qui s'éteint sur 0,25 s
}
# Motifs : n° -> (répétitions, [(durée × 50 ms, (rouge, vert, bleu) de 0 à 15)]) ; le noir final rend la balle éteinte
MOTIFS = {
    60: (1, [(2, BLANC), (1, K)]),                                                       # validation : éclair blanc
    61: (1, [(2, ROUGE), (2, K), (2, ROUGE), (1, K)]),                                   # coup reçu : deux éclairs
    62: (1, [(6, ROUGE), (4, (9, 0, 0)), (4, (5, 0, 0)), (4, (2, 0, 0)), (1, K)]),       # K.O. : rouge qui s'éteint
    63: (1, [(4, (15, 6, 0)), (3, (15, 3, 0)), (3, (8, 2, 0)), (3, (3, 1, 0)), (1, K)]), # crash : orange
    64: (1, [(3, ROUGE), (3, (10, 0, 15)), (3, ROUGE), (3, (10, 0, 15)), (4, ROUGE), (1, K)]),   # combat
    65: (1, [(3, (15, 12, 0)), (3, (0, 15, 2)), (3, (15, 12, 0)), (3, (0, 15, 2)), (8, (15, 12, 0)), (1, K)]),   # victoire
    66: (1, [(3, (0, 4, 1)), (3, (0, 9, 2)), (8, (0, 15, 4)), (3, (0, 9, 2)), (3, (0, 4, 1)), (1, K)]),          # soin
    67: (1, [(8, (10, 0, 0)), (8, (3, 0, 0)), (8, (10, 0, 0)), (8, (3, 0, 0)), (12, (6, 0, 0)), (1, K)]),        # défaite
    68: (0x14, [(10, CYAN)]),   # ambiance : cyan 10 s, rejouée par la montre ; jamais 1f (boucle sans fin : la balle ne dort plus)
    69: (1, [(1, K)]),                                                                   # éteint
}
# Activités, dans l'ordre ENG_EFFET_* : (motif, son du jeu 0 ou None)
EFFETS = [
    ('validation', 60, 24), ('coup reçu', 61, 25), ('K.O.', 62, 26), ('crash', 63, 26), ('combat', 64, 25),
    ('victoire', 65, 24), ('soin', 66, None), ('niveau gagné', 2, 24), ('défaite', 67, 26),   # motif 2 : arc-en-ciel de la balle
    ('coup porté', None, 24),                                                            # vibration seule
]
AMBIANCE = ('ambiance', 68, None)
ETEINT = ('éteint', 69, None)

ETAT_ACT, ENR_ACT = 0x55000, 0x551fc           # activité n : état, enregistrement de 0x20 octets
ETAT_LED, ENR_LED = 0x5917c, 0x59378           # motif n : état, enregistrement de 0x80 octets
ETAT_SON0, ENR_SON0 = 0x69178, 0x691a0         # son n du jeu 0 : état, emplacement de 0x2000 octets
ENTETE = bytes.fromhex('00000000efbeadde')     # validé + magique


def trame(op, p): return bytes([op, len(p) & 255, len(p) >> 8]) + p
def ecrire(a, data): return [trame(0x87, struct.pack('<II', a + o, len(data[o:o + 200])) + data[o:o + 200]) for o in range(0, len(data), 200)]
def lire(a, n): return trame(0x0b, struct.pack('<II', a, n))


def motif(rep, etapes):
    corps = bytes([len(etapes), rep]) + b''.join(bytes([d, g << 4 | r, b]) for d, (r, g, b) in etapes)
    return b'\x00\x00' + bytes([len(corps) + 2]) + corps   # longueur = octets après 00 00, + 1


def vibration(segs):
    if segs == 'longue':
        n = int(0.7 * SR); x = 0.9 * np.sin(2 * np.pi * 200 * np.arange(n) / SR)
        x *= np.concatenate([np.linspace(0, 1, 40), np.ones(n - 40 - 2000), np.linspace(1, 0, 2000)])
        x = np.concatenate([x, np.zeros(160)])
    else:
        parts = []
        for d, a in segs:
            n = int(d * SR); e = np.full(n, float(a)); r = min(40, n // 2)
            if a and r: e[:r] *= np.linspace(0, 1, r); e[-r:] *= np.linspace(1, 0, r)
            parts.append(e * np.sin(2 * np.pi * 200 * np.arange(n) / SR))
        x = np.concatenate(parts)
    b = io.BytesIO(); sf.write(b, x.astype(np.float32), SR, format='WAV', subtype='MS_ADPCM'); w = b.getvalue()
    i = w.find(b'fmt '); fmt = w[i:i + 8 + struct.unpack_from('<I', w, i + 4)[0]]
    j = w.find(b'data'); data = w[j + 8:j + 8 + struct.unpack_from('<I', w, j + 4)[0]]
    # en-tête comme ceux de la balle : RIFF, fmt (MS-ADPCM, blocs de 256 octets), fact, data
    wav = b'RIFF' + struct.pack('<I', 4 + len(fmt) + 12 + 8 + len(data)) + b'WAVE' + fmt + b'fact' + struct.pack('<II', 4, len(x)) + b'data' + struct.pack('<I', len(data)) + data
    assert len(wav) <= 0x2000, 'vibration trop longue pour le jeu 0'
    return wav


def main():
    libres = [a for k, a in enumerate(sys.argv[1:], 1) if not a.startswith('--') and sys.argv[k - 1] != '--activites']
    sortie = libres[0] if libres else os.path.join(ICI, 'effets.txt')
    T, verif = [], []
    if '--vibrations' in sys.argv:
        for n, segs in VIBRATIONS.items():
            w = vibration(segs); a = ENR_SON0 + 0x2000 * n
            open(os.path.join(ICI, f'vibration{n}.wav'), 'wb').write(w)
            T += ecrire(a, w) + ecrire(ETAT_SON0 + n, b'\x00')
            T.append(trame(0x88, struct.pack('<II', a, len(w)))); verif.append(f'son {n} : CRC {zlib.crc32(w).to_bytes(4, "little").hex(" ")}')
    acts = {ACT0 + k: e for k, e in enumerate(EFFETS)}
    acts[ACT_AMBIANCE] = AMBIANCE
    acts[ACT_ETEINT] = ETEINT
    if '--activites' in sys.argv:
        garde = {int(x) for x in sys.argv[sys.argv.index('--activites') + 1].split(',')}
        acts = {a: e for a, e in acts.items() if a in garde}
    for n, (rep, etapes) in MOTIFS.items():   # les motifs des activités écrites
        if any(led == n for _, led, _ in acts.values()):
            T += ecrire(ENR_LED + 0x80 * n, ENTETE + motif(rep, etapes)) + ecrire(ETAT_LED + n, b'\x00')
    for a, (nom, led, son) in acts.items():
        donnees = b'\x00' + struct.pack('<H', 0xffff if led is None else led) + (struct.pack('<HB', son, 0) if son is not None else b'\xff\xff\xff')
        T += ecrire(ENR_ACT + 0x20 * a, ENTETE + donnees)
    for a in acts: T += ecrire(ETAT_ACT + a, b'\x00')   # états en dernier : une activité n'existe qu'une fois complète
    T.append(lire(ETAT_ACT + ACT0, ACT_ETEINT - ACT0 + 1))
    open(sortie, 'w').write('\n'.join(t.hex() for t in T) + '\n')
    print(f'{len(T)} trames dans {sortie}')
    for v in verif: print(v)
    for a, (nom, led, son) in acts.items(): print(f'activité {a} : {nom} (motif {led}, son {son})')


if __name__ == '__main__':
    main()
