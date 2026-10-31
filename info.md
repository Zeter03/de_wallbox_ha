# dé EV Charger Integration

A fully local Home Assistant integration for **dé EV Chargers** (and other Tuya-based 11kW/22kW generic EV wallboxes). 

Because this uses local UDP/TCP polling via `tinytuya`, it responds instantly and does not rely on the Tuya Cloud, ensuring privacy and reliability!

### Features
* 🏎️ **Adjustable Current Limit:** Dynamically change charge speeds (6A - 16A) for Solar Excess charging.
* 📊 **Live 3-Phase Metrics:** Real-time Voltage, Current, and Power over L1, L2, and L3.
* 🔋 **Session Stats:** Track Session Energy (kWh) and Duration.
* 🔌 **Control Modes:** Start/Stop Charging, Toggle Plug & Charge mode, and Force Single-Phase mode.
* 📡 **Auto-Discovery:** Automatically finds the charger on your local network.

*Requires your Tuya `local_key`. Please see the repository README for instructions on how to get it.*