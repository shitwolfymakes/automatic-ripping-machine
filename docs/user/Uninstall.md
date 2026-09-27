# Uninstall

ARM v3 keeps everything inside its install prefix and installs no systemd units
or distro integration, so removing it is two commands:

```bash
cd ~/arm
docker compose down          # stop and remove the containers + network
```

Then delete the prefix once you've saved anything you want to keep:

```bash
rm -rf ~/arm
```

(Use your actual prefix if you installed with `--prefix`.)

## What `docker compose down` removes

- The `armv3-*` containers and the compose network.
- It does **not** delete your bind-mounted data — `db/`, `raw/`, `media/`,
  `logs/`, and `certs/` are plain directories under the prefix and survive until
  you `rm -rf` them.

To also drop any anonymous volumes the stack created, add `--volumes`:

```bash
docker compose down --volumes
```

## Save these first if you might reinstall

- **`certs/arm-ca.key`** — your unique CA. If you keep it (and `.env`), a
  reinstall won't force every LAN device to re-trust a new certificate.
- **`media/`** (and `raw/` if you haven't transcoded yet) — your actual ripped
  content.
- A **Postgres dump** if you want to preserve job history:

  ```bash
  docker exec armv3-db pg_dump -U arm arm > ~/arm-final-backup.sql
  ```

## Removing the host udev rule (desktop installs)

If you installed on a desktop, the installer added a scoped auto-mount rule.
Remove it if you no longer want ARM's drives left un-automounted:

```bash
sudo rm /etc/udev/rules.d/99-arm-no-automount.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Removing the images

```bash
docker image ls 'automaticrippingmachine/*'
docker image rm <image-id> ...
```
