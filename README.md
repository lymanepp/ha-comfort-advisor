# https://github.com/lymanepp/ha-comfort-advisor

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

Comfort Advisor provides the following calculated sensors for Home Assistant.

## Sensors

**Can Open Windows**

> Whether windows can be open, for fresh air and to save energy. Windows can be open when:
>
> - it's comfortable outside (simmer index, dew point and humidity within your limits), unless the
>   outdoor air would make the heating or cooling work harder: adding heat or moisture to a warm
>   house, or chilling a cool house by more than the temperature tolerance; or
> - the house is warmer than comfortable and the outdoor air is cooler and drier, even if it's
>   below the comfortable range, as long as it's above the lowest cooling temperature and within
>   the dew point and humidity limits.
>
> The `reason` attribute explains the current advice: `fresh_air`, `free_cooling`, `adds_heat`,
> `adds_chill` or `uncomfortable`.

**High Simmer Index**

> The high simmer index over the next 24 hours.

**Open Windows At / Close Windows At**

> The next time the windows are recommended to be opened or closed, based on the hourly forecast.
> Forecast hours are compared against the current indoor conditions.

## Usage

To use Comfort Advisor check the documentation for your preferred way to setup sensors.

**UI/Frontend (Config Flow)
 [master](https://github.com/lymanepp/ha-comfort-advisor/blob/master/documentation/config_flow.md)**

## Installation

Requires Home Assistant 2026.10 or newer.

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