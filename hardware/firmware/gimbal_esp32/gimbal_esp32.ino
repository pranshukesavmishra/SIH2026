/*
 * FSOC-PAT pan-tilt: two servos behind the same command contract as the
 * virtual gimbal -- absolute angle commands in, rate-limited motion out,
 * and every state report carries a timestamp so the host can measure the
 * real command latency instead of guessing it.
 *
 * Wiring: pan MG996R signal -> GPIO 18, tilt -> GPIO 19.
 *         Servo V+ -> external 5V 3A (NOT the ESP32 5V pin), grounds common,
 *         1000 uF electrolytic across the servo supply.
 *
 * Serial (115200), lines:
 *   "P <pan_deg> <tilt_deg>"  absolute command, e.g. "P 12.5 -3.0"
 *   "R <deg_per_s>"           slew rate limit (default 60)
 *   "C"                       centre (90/90 servo frame)
 *   "?"                       -> "S <pan> <tilt> <millis>"
 * Every accepted command is answered "A <millis>" immediately, which is the
 * timestamp the host-side latency calibration uses.
 */
#include <ESP32Servo.h>
Servo pan, tilt;
float cur_p = 0, cur_t = 0, cmd_p = 0, cmd_t = 0, rate = 60.0;
unsigned long last_us = 0;
const float P_MIN = -80, P_MAX = 80, T_MIN = -40, T_MAX = 60;

void writeServos() {
  pan.write(constrain(cur_p, P_MIN, P_MAX) + 90.0);
  tilt.write(constrain(cur_t, T_MIN, T_MAX) + 90.0);
}

void setup() {
  Serial.begin(115200);
  pan.setPeriodHertz(50);  tilt.setPeriodHertz(50);
  pan.attach(18, 500, 2500); tilt.attach(19, 500, 2500);
  writeServos();
  last_us = micros();
}

void loop() {
  // Rate-limited slew toward the command, 200 Hz update.
  unsigned long now = micros();
  if (now - last_us >= 5000) {
    float dt = (now - last_us) * 1e-6;
    last_us = now;
    float step = rate * dt;
    cur_p += constrain(cmd_p - cur_p, -step, step);
    cur_t += constrain(cmd_t - cur_t, -step, step);
    writeServos();
  }
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.startsWith("P ")) {
    int sp = line.indexOf(' ', 2);
    cmd_p = line.substring(2, sp).toFloat();
    cmd_t = line.substring(sp + 1).toFloat();
    Serial.printf("A %lu\n", millis());
  } else if (line.startsWith("R ")) {
    rate = line.substring(2).toFloat();
    Serial.printf("A %lu\n", millis());
  } else if (line == "C") {
    cmd_p = cmd_t = 0; Serial.printf("A %lu\n", millis());
  } else if (line == "?") {
    Serial.printf("S %.2f %.2f %lu\n", cur_p, cur_t, millis());
  }
}
