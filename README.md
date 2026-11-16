# OpenBeken OTA Updater for Home Assistant

> **Work in progress:** This integration is under active development and may contain bugs or incomplete features.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/SnowyCrunchybar/ha-openbeken-ota.svg)](https://github.com/SnowyCrunchybar/ha-openbeken-ota/releases)

A local-first Home Assistant custom integration for discovering, backing up, and performing Over-The-Air (OTA) firmware updates on **OpenBeken** (`BK7231T`, `BK7231N`, `BK7238`, `BL602`, `W800`, `W600`) devices.

## Features

- **Automatic MQTT Device Discovery:** Automatically detects OpenBeken devices registered in Home Assistant via MQTT and tracks dynamic IP address changes in real time.
- **Local HTTP Firmware Caching:** Downloads the latest `.rbl` OTA binaries from the official [OpenBK7231T_App](https://github.com/openshwprojects/OpenBK7231T_App) GitHub releases into `/config/www/openbeken_ota/` and serves them locally over plain HTTP—bypassing TLS/HTTPS memory limitations on Beken hardware.
- **Automatic Configuration Backups:** Backs up `config.json` and `autoexec.bat` (if present) to `/config/openbeken_backups/<device>/<timestamp>/` before flashing or on demand.
- **Native Home Assistant `update` Entities:** Integrates directly into Home Assistant's native **Settings → Updates** view with release notes and version tracking.
- **Per-Device & Global Controls:** Includes dedicated buttons for checking updates, backing up configurations, restarting devices, and running sequential batch updates across all outdated devices.

## Installation via HACS

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=SnowyCrunchybar&repository=ha-openbeken-ota&category=integration)

1. Open **HACS** in Home Assistant.
2. Click the three dots in the top-right corner and select **Custom repositories**.
3. Add `https://github.com/SnowyCrunchybar/ha-openbeken-ota` as category **Integration**.
4. Find **OpenBeken OTA Updater** in HACS and click **Download**.
5. Restart Home Assistant.
