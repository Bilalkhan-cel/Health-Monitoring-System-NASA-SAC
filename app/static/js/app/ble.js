// Web Bluetooth heart-rate strap (standard Heart Rate service 0x180D, measurement 0x2A37).
// Works in Chrome and Edge on a secure context (localhost or HTTPS).

const HEART_RATE_SERVICE = 0x180d;
const HEART_RATE_MEASUREMENT = 0x2a37;

export function bluetoothAvailable() {
  return Boolean(navigator.bluetooth && window.isSecureContext);
}

// Parse a Heart Rate Measurement value (Bluetooth SIG GATT spec): flag bit 0 = 16-bit value.
export function parseHeartRate(dataView) {
  const flags = dataView.getUint8(0);
  return flags & 0x01 ? dataView.getUint16(1, true) : dataView.getUint8(1);
}

export async function connectStrap(onBeat, onDisconnect) {
  const device = await navigator.bluetooth.requestDevice({ filters: [{ services: [HEART_RATE_SERVICE] }] });
  device.addEventListener('gattserverdisconnected', () => onDisconnect?.());
  const server = await device.gatt.connect();
  const service = await server.getPrimaryService(HEART_RATE_SERVICE);
  const characteristic = await service.getCharacteristic(HEART_RATE_MEASUREMENT);
  characteristic.addEventListener('characteristicvaluechanged', (event) => {
    const bpm = parseHeartRate(event.target.value);
    if (bpm > 20 && bpm < 240) onBeat(bpm);
  });
  await characteristic.startNotifications();
  return {
    name: device.name || 'Heart-rate strap',
    disconnect() {
      if (device.gatt.connected) device.gatt.disconnect();
    },
  };
}
