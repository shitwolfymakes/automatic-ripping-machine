# MakeMKV

ARM rips **video** discs (DVD and Blu-ray) with [MakeMKV](https://www.makemkv.com/).
The ripper image builds MakeMKV from the official signed source — no licence is
baked into the image, so every ripper container needs a working key at runtime.
(Audio CDs don't touch MakeMKV; they're ripped with abcde. Data discs are imaged
directly.)

## How the key works

Before each disc, the ripper runs a small script that ensures a key is in place,
choosing one of two paths:

1. **You supply a key.** Set `MAKEMKV_KEY=T-…` in `~/arm/.env` (a purchased
   permanent key, or a beta key you grabbed yourself). The script writes it into
   the container's `~/.MakeMKV/settings.conf`. No forum traffic, no surprises —
   **this is the recommended setup for anything beyond casual use.**
2. **You leave it unset.** The script scrapes the *current month's free beta
   key* from MakeMKV's public forum thread and uses that. This is the same
   approach ARM has shipped for years and is fine for DVDs, but the forum sits
   behind Cloudflare and rate-limits, so the scrape is brittle under load.

The free beta key rotates roughly monthly. Because the refresh runs per disc, a
container left running across a rotation **self-heals on the next disc** — no
restart needed.

After setting a key, apply it and verify:

```bash
cd ~/arm && docker compose up -d
docker compose exec arm-ripper-sr0 grep app_Key /home/arm/.MakeMKV/settings.conf
```

## Buying a key

While MakeMKV is in beta the free key works, but you can buy a permanent key to
avoid the monthly rotation and the forum scrape: <https://www.makemkv.com/buy/>.
Set it as `MAKEMKV_KEY` per path 1 above.

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
[`docs/ops/makemkv.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/ops/makemkv.md).

## Licence

Using MakeMKV means accepting its EULA. The full text is mirrored at
**[MakeMKV EULA](MakeMKV-EULA)**. Note in particular that MakeMKV can bypass
copy protection to read a disc, and it's your responsibility to comply with the
copyright law in your jurisdiction.

## Reference

- **[MakeMKV output codes](MakeMKV-Codes)** — the `DRV:`/`TINFO:`/`SINFO:`
  message fields `makemkvcon` emits, handy when debugging a scan.
- **[`docs/ops/makemkv.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/ops/makemkv.md)**
  — the in-repo operations doc: key handling internals, how the image is built,
  and every failure mode with its log signature.
