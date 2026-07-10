# PSF Install

Install AFC with Proportional Sync-Feedback (PSF) from the `psf-dev` branch.

## Prerequisites

- Klipper, Moonraker, and Mainsail or Fluidd
- PSF hardware wired to an ADC-capable MCU pin

## Clone and install (printer)

### New install

```bash
cd ~
git clone https://github.com/Apollo1298/AFC-Klipper-Add-On.git
cd AFC-Klipper-Add-On
git checkout psf-dev
./install-afc.sh
```

### Existing AFC clone (switch to PSF branch)

```bash
cd ~/AFC-Klipper-Add-On
git remote add fork https://github.com/Apollo1298/AFC-Klipper-Add-On.git   # skip if already added
git fetch fork
git checkout psf-dev
git pull fork psf-dev
./install-afc.sh   # only needed if extras are not symlinked yet
sudo systemctl restart klipper
```

### Moonraker update manager (optional)

Point `afc-software` at the fork and branch so updates pull PSF work:

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
- Manual config / migration: [PSF_Migration.md](PSF_Migration.md).
- Use the **AFC** panel in Mainsail/Fluidd (not the MMU panel).
