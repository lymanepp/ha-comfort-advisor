# [![comfort_advisor](https://raw.githubusercontent.com/lymanepp/ha-comfort-advisor/master/icons/logo.png)](https://github.com/lymanepp/ha-comfort-advisor)

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

Comfort Advisor provides the following calculated sensors for Home Assistant.

## Sensors

**Open Windows**

> The weather outside is comfortable and windows can be opened.

**Open Windows Reason**

> The explanation why window **Open Windows** sensor is on or off.

## Usage

To use Comfort Advisor check the documentation for your preferred way to setup sensors.

**UI/Frontend (Config Flow)
 [master](https://github.com/lymanepp/ha-comfort-advisor/blob/master/documentation/config_flow.md)**

## Installation

### Using [HACS](https://hacs.xyz/) (recommended)

This integration can be installed using HACS. To do it search for Comfort Advisor in the integrations section.

### Manual

To install this integration manually you can either

* Use git:

```sh
git clone https://github.com/lymanepp/ha-comfort-advisor.git
cd ha-comfort-advisor
# if you want a specific version checkout its tag
# e.g. git checkout 1.0.0

# replace $hacs_config_folder with your home assistant config folder path
cp -r custom_components $hacs_config_folder
```

* Download the source release and extract the custom_components folder into your home assistant config folder.

Finally you need to restart home assistant before you can use it.