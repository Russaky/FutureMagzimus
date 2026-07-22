#pragma once

#define FIRMWARE_VERSION  "v1.0"

#define ESPNOW_CHANNEL  1

// SoftAP fallback settings (used when no known STA network is reachable)
#define AP_SSID      "MagLight"
#define AP_PASSWORD  "magzimus"

// Time to wait for each known network in WIFI_NETWORKS (credentials.h) before
// trying the next one / falling back to the SoftAP.
#define WIFI_NETWORK_TIMEOUT_MS  5000

// Constants
#define GROUP_ID        1

// Dedicated MAC address for the Bridge to lock source priority on Light Controllers
#define BRIDGE_MAC_ADDR  {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF}
