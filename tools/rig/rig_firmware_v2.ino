// ZeroDrift Mini-Rig Mk2 firmware — DRAFT, not yet bench-tested.
// Verify step/dir pin wiring, direction signs, and step/degree scaling
// against your actual hardware before trusting any of this.
//
// Requires the AccelStepper library (Arduino Library Manager).
//
// Serial protocol @ 115200 baud, newline-terminated commands:
//   P<int> T<int>   coarse pan/tilt target position, in motor steps
//                    from center (0 = center; sign = direction)
//   p<int> t<int>   fine pan/tilt target angle, in servo degrees
//                    (same 20-160 / 40-140 soft limits as Mk1)
//   L0 / L1         laser off / on
//   V0 / V1         vibration injector off / on
//
// Coarse and fine commands are independent — send whichever axis you're
// updating; unset ones keep their last commanded position.

#include <AccelStepper.h>
#include <Servo.h>

// ---- Pin map — adjust to your actual wiring ----
const int PAN_STEP_PIN = 2,  PAN_DIR_PIN  = 3;
const int TILT_STEP_PIN = 4, TILT_DIR_PIN = 5;
const int FINE_PAN_PIN = 9, FINE_TILT_PIN = 10;
const int LASER_PIN = 7;
const int VIBRATION_PIN = 8;

// ---- Coarse stage: steppers via AccelStepper (driver interface: STEP/DIR) ----
AccelStepper panStepper(AccelStepper::DRIVER, PAN_STEP_PIN, PAN_DIR_PIN);
AccelStepper tiltStepper(AccelStepper::DRIVER, TILT_STEP_PIN, TILT_DIR_PIN);

// ---- Fine stage: micro servos ----
Servo finePan, fineTilt;

void setup() {
  Serial.begin(115200);

  panStepper.setMaxSpeed(800);       // steps/s — tune to your NEMA17 + driver microstepping
  panStepper.setAcceleration(400);
  tiltStepper.setMaxSpeed(800);
  tiltStepper.setAcceleration(400);

  finePan.attach(FINE_PAN_PIN);
  fineTilt.attach(FINE_TILT_PIN);
  finePan.write(90);
  fineTilt.write(90);

  pinMode(LASER_PIN, OUTPUT);
  digitalWrite(LASER_PIN, LOW);
  pinMode(VIBRATION_PIN, OUTPUT);
  digitalWrite(VIBRATION_PIN, LOW);
}

void loop() {
  static char buf[24];
  static int n = 0;

  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || n >= 23) {
      buf[n] = 0;
      n = 0;
      handleLine(buf);
    } else {
      buf[n++] = c;
    }
  }

  panStepper.run();
  tiltStepper.run();
}

void handleLine(const char *line) {
  int a, b;

  if (line[0] == 'P') {
    // coarse: "P<pan> T<tilt>" — either or both may be present
    if (sscanf(line, "P%d T%d", &a, &b) == 2) {
      panStepper.moveTo(a);
      tiltStepper.moveTo(b);
    } else if (sscanf(line, "P%d", &a) == 1) {
      panStepper.moveTo(a);
    }
  } else if (line[0] == 'T') {
    if (sscanf(line, "T%d", &b) == 1) {
      tiltStepper.moveTo(b);
    }
  } else if (line[0] == 'p') {
    // fine: "p<pan> t<tilt>"
    if (sscanf(line, "p%d t%d", &a, &b) == 2) {
      finePan.write(constrain(a, 20, 160));
      fineTilt.write(constrain(b, 40, 140));
    } else if (sscanf(line, "p%d", &a) == 1) {
      finePan.write(constrain(a, 20, 160));
    }
  } else if (line[0] == 't') {
    if (sscanf(line, "t%d", &b) == 1) {
      fineTilt.write(constrain(b, 40, 140));
    }
  } else if (line[0] == 'L') {
    digitalWrite(LASER_PIN, line[1] == '1' ? HIGH : LOW);
  } else if (line[0] == 'V') {
    digitalWrite(VIBRATION_PIN, line[1] == '1' ? HIGH : LOW);
  }
}
