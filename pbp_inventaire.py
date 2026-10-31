"""Poké Ball Plus par le Bluetooth du PC : recherche, connexion, inventaire complet du GATT, valeurs lisibles,
quelques trames de …e6."""
import asyncio, sys, time
from bleak import BleakScanner, BleakClient

E6 = "6675e16c-f36d-4567-bb55-6b51e27a23e6"


async def main():
    print("recherche de la balle (appuyer sur son bouton)…", flush=True)
    dev = None
    fin = time.time() + 60
    while not dev and time.time() < fin:
        dev = await BleakScanner.find_device_by_filter(lambda d, a: (a.local_name or d.name or "").startswith("Pokemon"), timeout=10)
    if not dev:
        print("pas trouvée"); return
    print("trouvée :", dev.address, dev.name, flush=True)
    async with BleakClient(dev) as c:
        print("connectée", flush=True)
        for s in c.services:
            print(f"service {s.uuid} ({s.description}) poignées {s.handle}")
            for ch in s.characteristics:
                v = ""
                if "read" in ch.properties:
                    try:
                        b = await c.read_gatt_char(ch)
                        v = f" = {b.hex(' ')} {bytes(x if 32 <= x < 127 else 46 for x in b).decode()!r}"
                    except Exception as e:
                        v = f" (lecture refusée : {e})"
                print(f"  car. {ch.uuid} poignée {ch.handle} {','.join(ch.properties)} max {ch.max_write_without_response_size}{v}")
                for d in ch.descriptors:
                    try:
                        b = await c.read_gatt_descriptor(d.handle)
                        dv = b.hex(' ')
                    except Exception as e:
                        dv = f"(refus {e})"
                    print(f"    desc. {d.uuid} poignée {d.handle} = {dv}")
        n = [0]

        def trame(_, b):
            n[0] += 1
            if n[0] <= 5:
                print("e6 :", b.hex(' '), flush=True)
        await c.start_notify(E6, trame)
        await asyncio.sleep(3)
        print(f"{n[0]} trames en 3 s", flush=True)

asyncio.run(main())
