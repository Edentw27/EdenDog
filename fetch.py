import cv2, time, datetime
from find_object import find_target

try:
    from xgolib import XGO
    dog = XGO('xgomini'); dog.reset(); ROBOT = True
except Exception as e:
    dog = None; ROBOT = False; print(f"[sim] no xgolib ({e})")

ACTIONS = {"blue_ball":"STAND TALL","blue_cube":"SIT DOWN","green_ball":"LIE DOWN",
           "purple_cube":"WAVE ARM","red_ball":"ATTACK + BARK","yellow_cube":"SPIN / DANCE"}
ACTION_IDS = {"LIE DOWN":1,"STAND TALL":2,"SIT DOWN":6,"WAVE ARM":17,"ATTACK + BARK":21,"SPIN / DANCE":24}
VALID_COLORS = ["red","green","blue","yellow","purple"]; VALID_SHAPES = ["ball","cube"]

# ---- TUNE ----
FWD_BURST=1.4; TURN_BURST=0.8; FWD_SPEED=15
KP_TURN=30; MAX_TURN=25; MIN_TURN=18; TURN_SIGN=-1
SEARCH_TURN=30; CENTRE_BAND=0.40; GRAB_AREA=8000
LOST_LIMIT=12; CAM_FAIL_LIMIT=15; SEARCH_LIMIT=30; SETTLE=0.35

ARM_REST=(90,120); ARM_DOWN=(120,-80); CLAW_OPEN=0; CLAW_CLOSE=255; GRAB_NUDGE=8

def log(m):
    line=f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {m}"; print(line)
    try:
        open("fetch.log","a").write(line+"\n")
    except: pass

def clamp(v,lo,hi): return max(lo,min(hi,v))

def flush(cap):
    for _ in range(4): cap.read()   # drop stale buffered frames after moving

def move_forward(s=FWD_SPEED):
    log(f"  forward {s}")
    if ROBOT: dog.move_x(s, runtime=FWD_BURST)
    else: time.sleep(FWD_BURST)

def turn(s):
    log(f"  turn {s}")
    if ROBOT: dog.turn(s, runtime=TURN_BURST)
    else: time.sleep(TURN_BURST)

def stop():
    if ROBOT: dog.move_x(0); dog.turn(0)

def parse(t):
    t=(t or "").lower(); c=next((x for x in VALID_COLORS if x in t),None); s=next((x for x in VALID_SHAPES if x in t),None)
    return f"{c}_{s}" if c and s else None

def get_command():
    try:
        import speech_recognition as sr
        r=sr.Recognizer()
        with sr.Microphone() as src:
            r.adjust_for_ambient_noise(src,duration=0.5); print("\nListening... 'fetch green ball' (Ctrl+C to type)")
            audio=r.listen(src,timeout=6,phrase_time_limit=4)
        txt=r.recognize_google(audio); print(f"Heard: {txt}")
        p=parse(txt)
        if p: return p
        print("no colour+shape")
    except KeyboardInterrupt: pass
    except Exception as e: print(f"voice off ({e})")
    return parse(input("Type command: "))

def do_grab():
    log("GRAB open"); 
    if ROBOT: dog.claw(CLAW_OPEN); time.sleep(1)
    log("GRAB arm down")
    if ROBOT: dog.arm(*ARM_DOWN); time.sleep(1.5)
    log("GRAB nudge")
    if ROBOT: dog.move_x(15,runtime=1.5); time.sleep(0.5); dog.move_x(15,runtime=1.2); time.sleep(0.5)
    log("GRAB close")
    if ROBOT: dog.claw(CLAW_CLOSE); time.sleep(1)
    log("GRAB lift")
    if ROBOT: dog.arm(*ARM_REST); time.sleep(1.5)

def do_action(a):
    log(f"REACT {a}")
    if ROBOT and ACTION_IDS.get(a): dog.action(ACTION_IDS[a]); time.sleep(3); dog.reset()

def fetch(target):
    log(f"=== FETCH {target} ({ACTIONS.get(target,'?')}) ===")
    cap=cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_AUTO_WB, 0)
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
    state="SEARCH"; lost=0; camfail=0; searches=0; last_cx=0.0
    try:
        while True:
            ok,frame=cap.read()
            if not ok:
                camfail+=1
                if camfail>CAM_FAIL_LIMIT: log("ERROR: camera dead"); break
                continue
            camfail=0
            obj=find_target(frame,target)

            if state=="SEARCH":
                if obj:
                    log(f"Found {target} cx={obj['cx']:+.2f} area={obj['area']:.0f}"); stop(); flush(cap)
                    lost=0; last_cx=obj['cx']; state="APPROACH"
                else:
                    searches+=1
                    if searches>SEARCH_LIMIT: log("not found, giving up"); break
                    turn(TURN_SIGN*SEARCH_TURN); flush(cap)

            elif state=="APPROACH":
                if not obj:
                    lost+=1
                    if lost>LOST_LIMIT:
                        log("lost -> search"); state="SEARCH"; searches=0; lost=0
                    else:
                        # coast toward where we last saw it
                        cmd=TURN_SIGN*clamp(KP_TURN*last_cx,-MAX_TURN,MAX_TURN)
                        if abs(cmd)<MIN_TURN: cmd=MIN_TURN if last_cx>0 else -MIN_TURN
                        turn(cmd); flush(cap)
                    continue
                lost=0; last_cx=obj['cx']
                if obj['area']>=GRAB_AREA:
                    log("close -> grab"); stop(); state="GRAB"
                elif abs(obj['cx'])>CENTRE_BAND:
                    cmd=TURN_SIGN*clamp(KP_TURN*obj['cx'],-MAX_TURN,MAX_TURN)
                    if abs(cmd)<MIN_TURN: cmd=MIN_TURN if obj['cx']>0 else -MIN_TURN
                    turn(cmd); flush(cap)
                else:
                    move_forward(); flush(cap)

            elif state=="GRAB":
                state="REACT"
            elif state=="REACT":
                do_action(ACTIONS[target]); log("=== DONE ==="); break
            time.sleep(SETTLE)
    finally:
        stop(); cap.release()

def main():
    print(f"\nROBODOG FETCH - {'ROBOT' if ROBOT else 'SIM'}")
    try:
        while True:
            t=get_command()
            if not t: print("try again"); continue
            fetch(t)
            if input("\nAgain? (Enter=yes, q=quit) ").strip().lower()=="q": break
    except KeyboardInterrupt: pass
    finally:
        if ROBOT: dog.reset()
        print("bye")

if __name__=="__main__": main()
