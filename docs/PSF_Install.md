# PSF Install

Install AFC with Proportional Sync-Feedback (PSF) from the `psf-dev` branch.

## Prerequisites

- Klipper, Moonraker, and Mainsail or Fluidd
- PSF hardware wired to an ADC-capable MCU pin

## Clone and install (printer)

Without `-b`, the installer **keeps** the clone's current branch (it does not switch to `main`). Prefer an explicit `-b psf-dev` so the working tree cannot drift.

### New install

```bash
cd ~
git clone -b psf-dev https://github.com/Apollo1298/AFC-Klipper-Add-On.git
cd AFC-Klipper-Add-On
./install-afc.sh -b psf-dev
```

Equivalent if you already cloned without `-b`:

```bash
cd ~/AFC-Klipper-Add-On
git checkout psf-dev
./install-afc.sh -b psf-dev
```

### Existing AFC clone (switch to PSF branch)

```bash
cd ~/AFC-Klipper-Add-On
git remote add fork https://github.com/Apollo1298/AFC-Klipper-Add-On.git   # skip if already added
git fetch fork
git checkout psf-dev
git pull fork psf-dev
./install-afc.sh -b psf-dev
sudo systemctl restart klipper
```

### Moonraker update manager (optional)

Point `afc-software` at the fork and branch so updates pull PSF work. A new install writes this from the live clone; if an older block still points at upstream `main`, replace it with:

```ini
[update_manager afc-software]
type: git_repo
path: ~/AFC-Klipper-Add-On
origin: https://github.com/Apollo1298/AFC-Klipper-Add-On.git
managed_services: klipper
primary_branch: psf-dev
is_system_service: False
```

Then use **Update** in Mainsail/Fluidd, or `git pull` on `psf-dev`, and restart Klipper.

## Notes

- Buffer type **PSF** is selectable for **BoxTurtle** and **NightOwl** in the installer.
- The installer refuses to write PSF config if `extras/AFC_psf.py` is missing (wrong branch).
- Manual config / migration: [PSF_Migration.md](PSF_Migration.md).
- Use the **AFC** panel in Mainsail/Fluidd (not the MMU panel).
