# MakeMKV

ARM rips **video** discs (DVD and Blu-ray) with [MakeMKV](https://www.makemkv.com/).
The ripper image builds MakeMKV from the official signed source — no licence is
baked into the image, so every ripper container needs a working key at runtime.
(Audio CDs don't touch MakeMKV; they're ripped with abcde. Data discs are imaged
directly.)

## How the key works

Before each disc, the ripper runs a small script that ensures a key is in place.
It uses one of two sources, in this order:

1. **The key you set in the UI** *(recommended).* Open **Config → MakeMKV key**
   and paste your key (a purchased permanent key, or a beta you grabbed
   yourself). The ripper fetches it from the backend before each rip, so there
   is no file to edit, it survives a restart or recreate, and you can change it
   without restarting anything.
2. **The free beta key, when the UI key is blank.** The script scrapes the
   *current month's free beta key* from MakeMKV's public forum thread and uses
   that. This is the same approach ARM has shipped for years and is fine for
   DVDs, but the forum sits behind Cloudflare and rate-limits, so the scrape is
   brittle under load.

Rippers are started by the backend, not by Compose, so a `MAKEMKV_KEY` line in
`~/arm/.armctl/.env` never reaches them. Set the key in the UI.

The free beta key rotates roughly monthly. Because the refresh runs per disc, a
container left running across a rotation **self-heals on the next disc**, with no
restart needed.

After setting a key, verify it landed on the next rip. Find the ripper container
for your drive, then read its settings file:

```bash
docker ps --filter label=arm.drive_id --format '{{.Names}}'
docker exec <ripper-name> grep app_Key /home/arm/.MakeMKV/settings.conf
```

## Buying a key

While MakeMKV is in beta the free key works, but you can buy a permanent key to
avoid the monthly rotation and the forum scrape: <https://www.makemkv.com/buy/>.
Paste it into **Config → MakeMKV key**.

## DVD vs Blu-ray — where the key actually matters

| Disc type | Needs a valid key? | Why |
|---|---|---|
| DVD (CSS or unprotected) | **No** | CSS support is in the open-source half of MakeMKV. |
| Blu-ray (AACS) | **Yes** | AACS is in the closed-source binary, gated by registration. |
| UHD Blu-ray (AACS 2.0) | **Yes** | Same path; also needs a compatible "friendly" UHD drive. |
| Audio CD | **No** | Ripped with abcde + cdparanoia, not MakeMKV. |

So if DVDs rip fine but Blu-rays fail with `App key incorrect`, the key is the
problem. If **every** MakeMKV call fails with `MSG:5021 … application version is
too old`, that's a different issue: MakeMKV beta binaries carry a hard ~60-day
kill switch and **no key overrides it** — you wait for the next upstream beta and
rebuild the ripper image. DVDs keep working in the meantime. Full failure-mode
table in
[`docs/user/MakeMKV-Ripper.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/user/MakeMKV-Ripper.md).

## Licence

Using MakeMKV means accepting its EULA. The full text is mirrored at
**[MakeMKV EULA](MakeMKV-EULA)**. Note in particular that MakeMKV can bypass
copy protection to read a disc, and it's your responsibility to comply with the
copyright law in your jurisdiction.

## Reference

- **[MakeMKV output codes](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/developers/reference/MakeMKV-Codes.md)** — the `DRV:`/`TINFO:`/`SINFO:`
  message fields `makemkvcon` emits, handy when debugging a scan.
- **[`docs/user/MakeMKV-Ripper.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/user/MakeMKV-Ripper.md)**
  — the in-repo operations doc: key handling internals, how the image is built,
  and every failure mode with its log signature.
