/*
 * ZeroDrift mini-rig firmware — Arduino Nano/Uno.
 * Receives "P<pan> T<tilt>\n" (servo degrees, 0-180) and "L0"/"L1"
 * (laser off/on) over USB serial at 115200. Nothing else.
 *
 * Wiring:
 *   Pan  servo signal -> D9    (orange/yellow wire)
 *   Tilt servo signal -> D10
 *   Laser module S    -> D7
 *   All servo + laser VCC -> 5V ; all GND -> GND
 */
#include <Servo.h>

Servo pan, tilt;
const int LASER_PIN = 7;

void setup() {
  Serial.begin(115200);
  pan.attach(9);
  tilt.attach(10);
  pinMode(LASER_PIN, OUTPUT);
  digitalWrite(LASER_PIN, LOW);
  pan.write(90);            // start centred
  tilt.write(90);
}

void loop() {
  static char buf[24];
  static int  n = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || n >= 23) {
      buf[n] = 0; n = 0;
      int p, t;
      if (sscanf(buf, "P%d T%d", &p, &t) == 2) {
        pan.write(constrain(p, 20, 160));    // soft limits: never slam the ends
        tilt.write(constrain(t, 40, 140));
      } else if (buf[0] == 'L') {
        digitalWrite(LASER_PIN, buf[1] == '1' ? HIGH : LOW);
      }
    } else buf[n++] = c;
  }
}
