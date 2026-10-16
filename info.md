
# HomeAssistant - SamsungTV Smart Component

This is a custom component to allow control of SamsungTV devices in [HomeAssistant](https://home-assistant.io). 
Is a modified version of the built-in [samsungtv](https://www.home-assistant.io/integrations/samsungtv/) with some extra
 features.<br/>
**This plugin is only for 2016+ TVs model!** (maybe all tizen family)

This project is a fork of the component [SamsungTV Tizen](https://github.com/jaruba/ha-samsungtv-tizen). I added some 
feature like the possibility to configure it using the HA user interface, simplifing the configuration process. 
I also added some code optimizition in the comunication layer using async aiohttp instead of request.
**Part of the code and documentation available here come from the original project.**<br/>

# Additional Features:

* Ability to send keys using a native Home Assistant service
* Ability to send chained key commands using a native Home Assistant service
* Supports Assistant commands (Google Home, should work with Alexa too, but untested)
* Extended volume control
* Ability to customize source list at media player dropdown list
* Cast video URLs to Samsung TV
* Connect to SmartThings Cloud API for additional features: see TV channel names, see which HDMI source is selected, more key codes to change input source
* Display logos of TV channels (requires Smartthings enabled) and apps

# Configuration

Once the component has been installed, you need to configure it using web UI in order to make it work.

**Important**: To complete the configuration procedure properly, you must be sure that your **TV is turned on and 
connected to the LAN (wired or wireless)**. Stay near to your TV during configuration because probably you will need 
to accept the access request that will prompt on your TV screen.

**Note**: To configure the component for using **SmartThings (strongly suggested)** you need to generate an access 
token as explained in [this guide](https://github.com/danalec/ha-samsungtv/blob/master/docs/Smartthings.md). 
Also make sure your **TV is logged into your SmartThings account** and **registered in SmartThings phone app** before 
starting configuration.

### Configuration using the web UI

1. From the Home Assistant front-end, navigate to 'Configuration' then 'Integrations'. Click `+` button in botton right corner,
search '**SamsungTV Smart**' and click 'Configure'.
2. In the configuration mask, enter the IP address of the TV, the name for the Entity and the SmartThings personal 
access token (if created) and then click 'Submit'
3. **Important**: look for your TV screen and confirm **immediatly** with OK if a popup appear.
4. Congrats! You're all set!

**Note**: be sure that your TV and HA are connected to the same VLAN. Websocket connection through different VLAN normally
not work because not supported by Samsung TV.
If you have errors during configuration, try to power cycle your TV. This will close running applications that can prevent 
websocket connection initialization.

**Please refer to [readme](https://github.com/danalec/ha-samsungtv/blob/master/README.md) for details on optional parameter and additional configuration instruction.**

# Be kind!
If you like the component, why don't you support me by buying me a coffe?
It would certainly motivate me to further improve this work.

[![Buy me a coffe!](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/ollo69)

Credits
-------

This integration is maintained by [danalec][danalec], building on [SamsungTV Smart][samsungtv_smart] by [Ollo69][ollo69],
which is itself based on the integration [SamsungTV Tizen][samsungtv_tizen].<br/>
Original SamsungTV Tizen integration was developed by [jaruba][jaruba].<br/>
Logo support is based on [jaruba channels-logo][channels-logo] and was developed with the support of [Screwdgeh][Screwdgeh].<br/>
The original [ha-samsungtv-custom][ha_samsungtv_custom] platform by [roberodin][roberodin] is the ancestor of this work.<br/>

[danalec]: https://github.com/danalec
[ollo69]: https://github.com/ollo69
[samsungtv_smart]: https://github.com/ollo69/ha-samsungtv-smart
[samsungtv_tizen]: https://github.com/jaruba/ha-samsungtv-tizen
[jaruba]: https://github.com/jaruba
[Screwdgeh]: https://github.com/Screwdgeh
[channels-logo]: https://github.com/jaruba/channel-logos
[ha_samsungtv_custom]: https://github.com/roberodin/ha-samsungtv-custom
[roberodin]: https://github.com/roberodin
