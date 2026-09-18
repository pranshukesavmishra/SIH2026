// ZeroDrift beacon unit — a frequency-precise blinking LED target.
//
// Replaces "hold up a phone strobe app" with a signal whose frequency is
// commanded, stable, and known — the ground truth the tracker's adaptive
// blink-frequency estimator is validated against live: type F6.0 here,
// watch the dashboard's "measured blink" follow to 6.0 Hz.
//
// Serial protocol @ 115200 baud, newline-terminated (matches the
// cross-session briefing):
//   F<float>   blink frequency in Hz (boot default 4.0; 0.5 .. 14.0)
//   B<0-255>   brightness (PWM)
//   M0 / M1    steady-on / blinking
//
// Every accepted command is echoed back ("OK F6.00") so a laptop script
// can log exactly what the beacon was doing at any moment. Runs from a
// battery once flashed — the serial port is only needed to command it.
//
// Wiring: LED (+ series resistor, ~220R for a standard 5 mm high-bright
// LED) on pin 9 (PWM). 50% duty cycle, millis()-based so drift stays far
// below what a 30 fps camera can resolve.

const int LED_PIN = 9;

float blink_hz = 4.0;
int brightness = 255;
bool blinking = true;

unsigned long period_ms = 250;   // 1000 / 4.0
char line[24];
byte n = 0;

void apply() {
  period_ms = (unsigned long)(1000.0 / blink_hz);
  if (period_ms < 36) period_ms = 36;      // ~14 Hz cap: stay observable
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  Serial.begin(115200);
  apply();
  Serial.println("ZeroDrift beacon ready  F4.00 B255 M1");
}

void handle() {
  line[n] = 0;
  if (line[0] == 'F') {
    float f = atof(line + 1);
    if (f >= 0.5 && f <= 14.0) {
      blink_hz = f;
      apply();
      Serial.print("OK F"); Serial.println(blink_hz);
    } else {
      Serial.println("ERR F range 0.5-14.0");
    }
  } else if (line[0] == 'B') {
    int b = atoi(line + 1);
    if (b >= 0 && b <= 255) {
      brightness = b;
      Serial.print("OK B"); Serial.println(brightness);
    }
  } else if (line[0] == 'M') {
    blinking = (line[1] == '1');
    Serial.print("OK M"); Serial.println(blinking ? 1 : 0);
  }
  n = 0;
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { if (n) handle(); }
    else if (n < sizeof(line) - 1) line[n++] = c;
  }
  // 50% duty square wave, phase-continuous across frequency changes
  bool on = true;
  if (blinking) {
    unsigned long ph = millis() % period_ms;
    on = ph < period_ms / 2;
  }
  analogWrite(LED_PIN, on ? brightness : 0);
}
