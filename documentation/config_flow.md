# Initial Configuration
## In your Home Assistant UI go to "Configuration", then click "Devices & Services"

![Config Dashboard](https://raw.githubusercontent.com/lymanepp/ha-comfort-advisor/master/screenshots/config_dashboard.png)

## Make sure Integrations is selected and click the "+" button in the bottom right corner

![Config Integrations](https://raw.githubusercontent.com/lymanepp/ha-comfort-advisor/master/screenshots/config_integrations.png)

## Search for or scroll down to find "Comfort Advisor" and select it

![Config Integrations Search](https://raw.githubusercontent.com/lymanepp/ha-comfort-advisor/master/screenshots/config_integrations_search.png)

## Name your virtual device and select the temperature and humidity sensor you want to use

*Note: Enable [advanced mode](https://www.home-assistant.io/blog/2019/07/17/release-96/#advanced-mode)
in your user profile if you want additional options.
We filter the sensors to include only those who have the correct device class.
If you want to select other make sure to enable
[advanced mode](https://www.home-assistant.io/blog/2019/07/17/release-96/#advanced-mode)*

![Config Comfort Advisor](https://raw.githubusercontent.com/lymanepp/ha-comfort-advisor/master/screenshots/config_comfort_advisor.png)

## A virtual device is created to manage your calculated sensors

![Config Virtual Device](https://raw.githubusercontent.com/lymanepp/ha-comfort-advisor/master/screenshots/config_devices_comfort_advisor.png)

# Configuration Options

## Click configure on the configuration to set additional options

![Config Virtual Device](https://raw.githubusercontent.com/lymanepp/ha-comfort-advisor/master/screenshots/config_options_comfort_advisor.png)

<dl>
  <dt><strong>Enable Polling</strong> <code>boolean</code></dt>
  <dd>
    Enable this if you want the sensors to be polled. This can avoid double
    calculated values if your input sensors split change updates for humidity
    and temperature.
  </dd>
  <dt><strong>Use custom icons pack</strong>  <code>boolean</code></dt>
  <dd>
    Enable this if you have the <a href="https://github.com/lymanepp/ha-comfort-advisor/blob/master/README.md#custom-icons">custom icon pack</a>
    installed and want to use it as default icons for the sensors
  </dd>
</dl>
