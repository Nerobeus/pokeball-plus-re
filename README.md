# Poké Ball Plus reverse engineering

How we took control of the Nintendo Poké Ball Plus over Bluetooth Low Energy, from a PC and from an ESP32-S3 watch:
play the activities stored in the ball, and write our own (custom LED colours, custom vibrations, game effects).
Nothing here needs a Switch, a phone app or any authentication.

**Read the [wiki](https://github.com/Nerobeus/pokeball-plus-re/wiki)**: method, command protocol, flash layout,
step-by-step custom activities, safety notes.

## What works

- Read the buttons, the 12-bit stick, the IMU and the battery.
- Play any activity stored in the ball (LED, vibration, sound): `03 02 00 NN 00` on characteristic `…e7`.
- Read the whole 4 MB flash, device info, step counter, the stored Pokémon.
- Write the ball's activity database: custom LED patterns, custom vibrations (200 Hz waves), activities that combine
  them. A game on an ESP32-S3 watch uses ten of them as feedback (hit, KO, victory, heal…) plus an ambient light.

## Scripts

| Script | Use |
|---|---|
| `pbp_inventaire.py` | find the ball, connect, dump its whole GATT table |
| `pbp_banc.py` | test bench: keeps the connection, logs every reply, runs commands from `pbp_cmd.txt` (frames, flash copy, button-driven sequences) |
| `pbp_analyse.py` | match each reply of a bench log to the command that caused it |
| `pbp_effets.py` | build custom LED patterns, vibrations and activities as frames for the bench |

```
pip install -r requirements.txt
python pbp_inventaire.py
```

Usage details are on the [Tools](https://github.com/Nerobeus/pokeball-plus-re/wiki/Tools) page. Comments and log
messages in the scripts are in French.

## Before you write anything

Reading is safe. Writing changes the ball's flash: read the
[Safety](https://github.com/Nerobeus/pokeball-plus-re/wiki/Safety) page first, keep a copy of the database area, and
never touch the firmware update service. Do not share dumps of the ball's flash: the firmware belongs to Nintendo.

## Credits and licence

Built on earlier work listed on the [Credits](https://github.com/Nerobeus/pokeball-plus-re/wiki/Credits) page.
Not affiliated with or endorsed by Nintendo, The Pokémon Company or Niantic. Scripts under the MIT licence
(`LICENSE`).
