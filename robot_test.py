"""
robot_test.py  —  RUN ON THE ROBOT FIRST
==========================================
Before letting the robot walk and grab on its own, use this to confirm:
  * which way it turns (left/right)
  * that forward is really forward
  * good arm positions for reaching the floor and lifting
  * which claw value is OPEN vs CLOSED

Put the robot on a clear flat surface with space around it.

Type single keys + Enter:
  f = forward burst      b = back burst
  l = turn left burst    r = turn right burst
  d = arm DOWN to floor  u = arm UP (lift)
  o = claw open          c = claw close
  x = reset (neutral)    q = quit

Or type a custom command to find good values:
  arm 120 -80     (arm to x=120 forward, z=-80 down)
  turn 30         (turn at speed 30 for one burst)
  fwd 12          (forward at speed 12 for one burst)
  claw 255        (claw to 255)
"""

import time
from xgolib import XGO

dog = XGO('xgomini')
dog.reset()
time.sleep(1)

BURST = 0.4         # seconds each movement runs before auto-stopping
FWD_SPEED = 12      # of max 25
TURN_SPEED = 30     # of max 100

# Arm presets (TUNE these with the custom 'arm X Z' command)
ARM_DOWN = (120, -80)   # reach forward + down toward the floor
ARM_UP   = (90, 120)    # lifted / carrying
CLAW_OPEN = 0           # <-- verify: which of 0 / 255 actually opens
CLAW_CLOSE = 255

print("Ready. Type a key (f/b/l/r/d/u/o/c/x/q) or a custom command.\n")

while True:
    cmd = input("> ").strip().lower()
    if cmd == "q":
        break
    try:
        if cmd == "f":
            dog.move_x(FWD_SPEED, runtime=BURST)
        elif cmd == "b":
            dog.move_x(-FWD_SPEED, runtime=BURST)
        elif cmd == "l":
            dog.turn(TURN_SPEED, runtime=BURST)
        elif cmd == "r":
            dog.turn(-TURN_SPEED, runtime=BURST)
        elif cmd == "d":
            dog.arm(*ARM_DOWN)
        elif cmd == "u":
            dog.arm(*ARM_UP)
        elif cmd == "o":
            dog.claw(CLAW_OPEN)
        elif cmd == "c":
            dog.claw(CLAW_CLOSE)
        elif cmd == "x":
            dog.reset()
        elif cmd.startswith("arm"):
            _, x, z = cmd.split()
            dog.arm(int(x), int(z))
        elif cmd.startswith("turn"):
            _, s = cmd.split()
            dog.turn(int(s), runtime=BURST)
        elif cmd.startswith("fwd"):
            _, s = cmd.split()
            dog.move_x(int(s), runtime=BURST)
        elif cmd.startswith("claw"):
            _, p = cmd.split()
            dog.claw(int(p))
        else:
            print("  unknown. keys: f b l r d u o c x q  | or: arm X Z / turn S / fwd S / claw P")
    except Exception as e:
        print("  error:", e)

dog.reset()
print("done")
