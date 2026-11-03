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
>
> Once windows can be open, they stay open until a reading is past a limit by a margin (1°F and
> 2% humidity by default, configurable), so the advice doesn't switch back and forth when a
> reading hovers near a limit. The open and close times follow the same rule.

**High Simmer Index**

> The high simmer index over the next 24 hours.

**Open Time Remaining**

> Hours until the windows should be closed, rounded to the nearest half hour: `0` while windows
> can't be open, and unknown when they can stay open longer than the forecast covers (24 hours).
> It's recalculated whenever the advice is, at least every hour, so it's current the moment
> **Can Open Windows** turns on. For example, to announce it:
>
> ```yaml
> {% set hours = states('sensor.comfort_advisor_open_time_remaining') %}
> {% if hours in ['unknown', 'unavailable'] %}
>   Windows can be opened for the rest of the day.
> {% else %}
>   Windows can be opened for about {{ hours | float | round(1) }} hours.
> {% endif %}
> ```

**Open Windows At / Close Windows At**

> The next time the windows are recommended to be opened or closed, based on the hourly forecast.
> Forecast hours are compared against the current indoor conditions.
>
> The forecast is corrected by how far the outdoor sensor is from it right now (temperature and
> dew point, limited to 10°F), fading out over the next 3 hours. So if it's warmer here than
> forecast, the forecast cool-down is expected later. The current corrections are available as
> the diagnostic sensors **Forecast Temperature Offset** and **Forecast Dew Point Offset**
> (not enabled by default).

## Pollen (optional)

Comfort Advisor can keep the windows closed when pollen is above the **highest acceptable pollen
level** (default: *low*). Select one or more pollen sensors during setup (or later with
**Reconfigure**); the highest level among them counts. The **Can Open Windows** reason is then
`high_pollen`.

Pollen sensors must report either a **0–5 index** or a **level name** (None, Very Low, Low,
Medium/Moderate, High, Very High). Pollen data is a daily forecast, so the current level applies
to the whole forecast. Sensors that are unavailable or have no current level are ignored, so a
pollen service outage doesn't stop the advice.

These integrations work directly (US coverage). **Google Pollen** is recommended: it's the one
this integration's maintainer uses.

| Integration | Install | Sensors to select | Notes |
|---|---|---|---|
| **[Google Pollen](https://github.com/robbybarnes/google_pollen)** (Google Pollen API), recommended | HACS custom repository: `https://github.com/robbybarnes/google_pollen` | Grass, tree and weed pollen index (0–5), e.g. `sensor.google_pollen_grass_pollen_index` | Updates every 6 hours by default; 5-day forecast attributes. Needs a Google Cloud API key with the Pollen API enabled (free monthly usage covers a few updates a day). Requires Home Assistant 2025.4.4 or newer. |
| [Pollen Levels](https://github.com/eXPerience83/pollenlevels) (Google Pollen API) | HACS (default store) | Grass, tree and weed pollen (0–5 index) | Same data source as Google Pollen. Requires Home Assistant 2026.5 or newer. |
| [Tomorrow.io](https://www.home-assistant.io/integrations/tomorrowio/) | Built in | Tree, weed and grass pollen index (None–Very High) | Needs a Tomorrow.io API key; the free plan has tight request limits. |

AccuWeather (pollen counts) and IQVIA (a 0–12 allergy index) use other scales; a
[template sensor](https://www.home-assistant.io/integrations/template/) can convert them to 0–5.
All of these are modeled daily forecasts, not measured counts, so compare them with local
reports for a season before relying on one.

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