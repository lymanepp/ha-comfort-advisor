# https://github.com/lymanepp/ha-comfort-advisor

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

Comfort Advisor provides the following calculated sensors for Home Assistant.

All sensors are unavailable while any input sensor or the hourly forecast is unavailable.

Results are recalculated when an input changes and as each forecast hour arrives. Input
changes that arrive within a second of each other (such as a temperature and humidity
published together) are combined into one recalculation, and temperature and enthalpy
values are rounded to one decimal place, so small changes don't record new states.

## Sensors

**Can Open Windows** (binary sensor, shown as Yes/No)

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

## Recommended: condition the input sensors

Raw temperature and humidity sensors often report small changes every few seconds, and
temperature and humidity separately. For steadier advice and fewer recorded states, put a
[Signal Conditioner](https://github.com/lymanepp/ha-signal-conditioner) in front of each of
the four input sensors and select the conditioned sensors in Comfort Advisor. With the same
time window on every conditioner, all four publish together at each interval boundary, and
Comfort Advisor recalculates once per interval.

```yaml
signal_conditioner:
  outdoor_temperature:
    source: sensor.outdoor_temperature_raw
    window:
      duration: 60   # seconds; use the same window for all four
      output: mean
    rounding:
      precision: 1
    availability:
      stale_after: 900   # for sensors that never report unavailable on their own
  # ...and the same for outdoor humidity, indoor temperature and indoor humidity
```

Signal Conditioner can also calibrate sensors and reject out-of-range readings.

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