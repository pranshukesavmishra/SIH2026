/*
 * FSOC-PAT beacon: an LED pulsed at an exact, crystal-derived frequency.
 *
 * The tracker identifies the beacon BY its modulation frequency, so timing
 * accuracy here is functional, not cosmetic: software blinking with delay()
 * drifts and jitters, while the ESP32's LEDC peripheral generates the
 * waveform in hardware and the CPU never touches it again.
 *
 * Wiring: LED anode -> 220R -> GPIO 4, cathode -> GND.
 * Serial (115200): "F 4.0"  set frequency in Hz     "D 50" duty percent
 *                  "ON" / "OFF"                     "?" report state
 */
const int PIN = 4, CH = 0;
float freq_hz = 4.0, duty_pct = 50.0;
bool on = true;

void apply() {
  if (on && freq_hz > 0.05) {
    ledcSetup(CH, freq_hz, 12);
    ledcAttachPin(PIN, CH);
    ledcWrite(CH, (uint32_t)(4095.0 * duty_pct / 100.0));
  } else {
    ledcDetachPin(PIN);
    pinMode(PIN, OUTPUT);
    digitalWrite(PIN, on ? HIGH : LOW);   // ON with freq 0 = continuous wave
  }
}

void setup() { Serial.begin(115200); apply(); }

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.startsWith("F ")) freq_hz = line.substring(2).toFloat();
  else if (line.startsWith("D ")) duty_pct = line.substring(2).toFloat();
  else if (line == "ON") on = true;
  else if (line == "OFF") on = false;
  apply();
  Serial.printf("ok f=%.2f d=%.0f on=%d\n", freq_hz, duty_pct, on);
}
