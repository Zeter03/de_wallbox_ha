# Home Assistant: dé EV Charger (Tuya Local)

![HACS Custom Integration](https://img.shields.io/badge/HACS-Custom_Integration-orange)
![Local Polling](https://img.shields.io/badge/IoT_Class-Local_Polling-green)

Control and monitor your Tuya-based 3-phase EV Wallbox entirely locally.

## Installation

1. Open Home Assistant -> HACS -> Integrations.
2. Click the 3 dots in the top right -> **Custom repositories**.
3. Paste the URL of this repository and select **Integration**.
4. Click **Download**, then restart Home Assistant.

## Configuration 

Go to **Settings > Devices & Services > Add Integration** and search for `dé EV Charger`. 
You can use **Auto Discover** to scan your network automatically. 

**Note:** You must obtain your Tuya `local_key` and `Device ID`. You can extract these by using the official [Tuya IoT Platform](https://iot.tuya.com/) or via the `tinytuya` wizard (`python -m tinytuya wizard`).