"""
fetch.py  —  FULL FETCH BEHAVIOUR
==================================
    command (voice or keyboard) -> SEARCH floor -> APPROACH (walk) -> GRAB -> REACT

Built-in robustness:
  * Proportional steering  (turn speed scales with how off-centre the object is)
  * Lost-target recovery   (target gone for a while -> back to SEARCH, not stuck)
  * Camera-failure guard    (many failed reads -> stop with an error, no silent loop)
  * Voice + keyboard fallback (Wi-Fi/mic dies -> type the command)
  * File log (fetch.log)     (a record of what happened, for the demo)

Runs REAL on the robot (xgolib present) and in PRINT-ONLY sim on a laptop.

============================  TUNE THESE ON THE ROBOT  ========================
Watch find_object.py output first to set GRAB_AREA and the speeds.
"""

import cv2
import time
import datetime
from find_object import find_target, find_objects   # Layer 1 (same folder)

# ── Robot connection (falls back to simulation on a laptop) ───────────
try:
    from xgolib import XGO
    dog = XGO('xgomini')
    dog.reset()
    ROBOT = True
except Exception as e:
    dog = None
    ROBOT = False
    print(f"[sim] xgolib not available — movements will be printed only ({e})")

# ── Object → action name and preset action id ─────────────────────────
ACTIONS = {
    "blue_ball": "STAND TALL", "blue_cube": "SIT DOWN", "green_ball": "LIE DOWN",
    "purple_cube": "WAVE ARM", "red_ball": "ATTACK + BARK", "yellow_cube": "SPIN / DANCE",
}
ACTION_IDS = {                 # confirm with explore.py, then fix numbers
    "LIE DOWN": 1, "STAND TALL": 2, "SIT DOWN": 6,
    "WAVE ARM": 17, "ATTACK + BARK": 21, "SPIN / DANCE": 24,
}

VALID_COLORS = ["red", "green", "blue", "yellow", "purple"]
VALID_SHAPES = ["ball", "cube"]

# ── Movement tuning (all conservative; limits are VX 25 / VYAW 100) ───
BURST        = 0.35    # seconds each move/turn runs, then auto-stops
FWD_SPEED    = 12      # forward speed while approaching (max 25)
KP_TURN      = 55      # proportional gain: turn speed = KP_TURN * cx
MAX_TURN     = 40      # cap on turn speed
MIN_TURN     = 14      # below this the robot won't actually rotate (deadband)
TURN_SIGN    = -1      # flip to +1 if it turns the WRONG way (test with robot_test.py)
SEARCH_TURN  = 22      # speed while spinning to look for the object
CENTRE_BAND  = 0.15    # |cx| under this = go straight instead of turning
GRAB_AREA    = 25000   # object this big (close) => stop and grab  <-- TUNE
LOOP_PAUSE   = 0.15    # small pause between observe cycles

# ── Grab tuning (arm x in [-80,155], z in [-95,155]; claw 0..255) ─────
ARM_REST   = (90, 120)    # tucked / carrying
ARM_DOWN   = (120, -80)   # reach forward + down to the floor
CLAW_OPEN  = 0            # verify with robot_test.py which value opens
CLAW_CLOSE = 255
GRAB_NUDGE = 8            # tiny forward creep to get over the object

# ── Safety counters ───────────────────────────────────────────────────
LOST_LIMIT     = 8        # ~consecutive misses before giving up the approach
CAM_FAIL_LIMIT = 15       # consecutive failed camera reads before ERROR
SEARCH_LIMIT   = 24       # search bursts before concluding "not found"


def log(msg):
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    try:
        with open("fetch.log", "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ── Movement wrappers (print-only in sim) ─────────────────────────────
def move_forward(speed=FWD_SPEED):
    log(f"  forward {speed}")
    if ROBOT:
        dog.move_x(speed, runtime=BURST)
    else:
        time.sleep(BURST)


def turn(speed):
    log(f"  turn {speed}")
    if ROBOT:
        dog.turn(speed, runtime=BURST)
    else:
        time.sleep(BURST)


def stop():
    if ROBOT:
        dog.move_x(0)
        dog.turn(0)


# ── Command input: voice, with keyboard fallback ──────────────────────
def parse_command(text):
    text = (text or "").lower()
    color = next((c for c in VALID_COLORS if c in text), None)
    shape = next((s for s in VALID_SHAPES if s in text), None)
    return f"{color}_{shape}" if color and shape else None


def get_command():
    # Try voice first
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            print("\nListening... say e.g. 'fetch green ball'  (or press Ctrl+C to type)")
            audio = r.listen(source, timeout=6, phrase_time_limit=4)
        text = r.recognize_google(audio)
        print(f"Heard: \"{text}\"")
        parsed = parse_command(text)
        if parsed:
            return parsed
        print("Didn't catch a colour + shape.")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Voice unavailable ({e}).")
    # Keyboard fallback
    raw = input("Type command (e.g. 'fetch green ball'): ")
    return parse_command(raw)


# ── Grab sequence (Layer 3 — the part that needs the most tuning) ──────
def do_grab():
    log("GRAB: opening claw")
    if ROBOT:
        dog.claw(CLAW_OPEN); time.sleep(1)
    log("GRAB: arm down to floor")
    if ROBOT:
        dog.arm(*ARM_DOWN); time.sleep(1.5)
    log("GRAB: nudge forward over object")
    if ROBOT:
        dog.move_x(GRAB_NUDGE, runtime=0.3); time.sleep(0.5)
    log("GRAB: closing claw")
    if ROBOT:
        dog.claw(CLAW_CLOSE); time.sleep(1)
    log("GRAB: lifting")
    if ROBOT:
        dog.arm(*ARM_REST); time.sleep(1.5)


def do_action(action_name):
    log(f"REACT: {action_name}")
    if not ROBOT:
        return
    aid = ACTION_IDS.get(action_name)
    if aid:
        dog.action(aid, wait=True)
        time.sleep(0.5)
        dog.reset()


# ── Main fetch loop (state machine) ───────────────────────────────────
def fetch(target):
    log(f"=== FETCH {target}  (action: {ACTIONS.get(target, '?')}) ===")
    cap = cv2.VideoCapture(0)

    state = "SEARCH"
    lost = 0
    cam_fail = 0
    searches = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                cam_fail += 1
                if cam_fail > CAM_FAIL_LIMIT:
                    log("ERROR: camera not returning frames — stopping.")
                    state = "ERROR"
                    break
                continue
            cam_fail = 0

            obj = find_target(frame, target)

            if state == "SEARCH":
                if obj:
                    log(f"Found {target} (cx={obj['cx']:+.2f}, area={obj['area']:.0f})")
                    lost = 0
                    state = "APPROACH"
                else:
                    searches += 1
                    if searches > SEARCH_LIMIT:
                        log(f"Could not find {target}. Giving up.")
                        break
                    turn(TURN_SIGN * SEARCH_TURN)

            elif state == "APPROACH":
                if not obj:
                    lost += 1
                    if lost > LOST_LIMIT:
                        log("Lost the target — going back to search.")
                        state = "SEARCH"
                        searches = 0
                        lost = 0
                    continue
                lost = 0

                if obj["area"] >= GRAB_AREA:
                    log("Close enough — stopping to grab.")
                    stop()
                    state = "GRAB"
                else:
                    cx = obj["cx"]
                    if abs(cx) > CENTRE_BAND:
                        # PROPORTIONAL steering: bigger offset -> faster turn
                        cmd = TURN_SIGN * clamp(KP_TURN * cx, -MAX_TURN, MAX_TURN)
                        if abs(cmd) < MIN_TURN:
                            cmd = MIN_TURN if cmd > 0 else -MIN_TURN
                        turn(cmd)
                    else:
                        move_forward(FWD_SPEED)

            elif state == "GRAB":
                do_grab()
                state = "REACT"

            elif state == "REACT":
                do_action(ACTIONS[target])
                log("=== DONE ===")
                break

            time.sleep(LOOP_PAUSE)
    finally:
        stop()
        cap.release()


def main():
    print("\n" + "=" * 52)
    print(f"  ROBODOG FETCH   —   {'REAL ROBOT' if ROBOT else 'SIMULATION'}")
    print("=" * 52)
    try:
        while True:
            target = get_command()
            if not target:
                print("Try again — e.g. 'fetch blue cube'.")
                continue
            fetch(target)
            again = input("\nAnother? (Enter = yes, q = quit) ").strip().lower()
            if again == "q":
                break
    except KeyboardInterrupt:
        pass
    finally:
        if ROBOT:
            dog.reset()
        print("\nGoodbye.")


if __name__ == "__main__":
    main()
