#!/usr/bin/env python3
# vendo_keepalive.py — LPB session holder
# r=rebuild  f=fire  s=status  h=help  q=quit
import os, random, select, shutil, sys, threading, time
import requests
from collections import deque

# ── config ──
TARGET       = "http://10.0.0.1"
INTERVAL     = 3
STALL        = 10
REBUILD_CD   = 25
ROTATE_MAC   = True
HISTORY_LEN  = 24

# ── ansi ──
R  = "\033[0m"; B  = "\033[1m"; D  = "\033[2m"
RD = "\033[31m"; GR = "\033[32m"; YL = "\033[33m"
MG = "\033[35m"; CY = "\033[36m"; GY = "\033[90m"

stop  = threading.Event()
lock  = threading.Lock()
state = {
    "session": None, "sse_open": 0,
    "fires": 0, "renews": 0, "stalls": 0, "consec_3": 0,
    "cmac": None, "started": time.time(),
    "status": "INIT", "last_rebuild": 0.0,
    "history": deque(maxlen=HISTORY_LEN),
    "events":  deque(maxlen=4),
}
_last_render = [""]
_last_input  = [0.0]

def rand_mac():
    return ":".join(f"{random.randint(0,255):02x}" for _ in range(6))

def stdin_ready():
    try:
        r, _, _ = select.select([sys.stdin], [], [], 0)
        return bool(r)
    except Exception:
        return False

def badge(s):
    return {
        "LIVE": f"{GR}* LIVE{R}",
        "WAIT": f"{YL}~ WAIT{R}",
        "RBLD": f"{MG}^ RBLD{R}",
        "ERR ": f"{RD}x ERR {R}",
    }.get(s, f"{D}. INIT{R}")

def sse_bar(n):
    f = max(0, min(n, 2))
    return f"{GR}[]" * f + f"{D}..{R}" * (2 - f) + f"  {n}/2"

def spark(hist):
    if not hist:
        return f"{GY}.{R}"
    s = ""
    for h in hist:
        if h == "2":   s += f"{GR}*{R}"
        elif h == "3": s += f"{D}.{R}"
        else:          s += f"{RD}x{R}"
    return s

def render():
    with lock:
        up = int(time.time() - state["started"])
        mm, ss = divmod(up, 60); hh, mm = divmod(mm, 60)
        status = state["status"]
        fires, renews, stalls = state["fires"], state["renews"], state["stalls"]
        sse = state["sse_open"]
        mac = state["cmac"] or "----"
        hist = list(state["history"])
        evs  = list(state["events"])

    out = ["\033[H\033[J"]     # home + clear from cursor down
    out.append("")
    out.append(f"  {CY}{B}VENDO KEEPALIVE{R}  {D}v1{R}")
    out.append(f"  {GY}{'-'*46}{R}")
    out.append("")
    out.append(f"  {D}status{R}   {badge(status)}")
    out.append(f"  {D}uptime{R}   {B}{hh:02d}:{mm:02d}:{ss:02d}{R}")
    out.append(f"  {D}fires{R}    {B}{fires:>4}{R}    "
               f"{D}renew{R} {GR}{renews}{R}    "
               f"{D}stall{R} {YL}{stalls}{R}")
    out.append(f"  {D}sse{R}      {sse_bar(sse)}")
    out.append(f"  {D}mac{R}      {GY}{mac}{R}")
    out.append("")
    out.append(f"  {D}activity{R} {spark(hist)}")
    out.append("")
    out.append(f"  {D}events{R}")
    if evs:
        for ts, msg in evs:
            out.append(f"   {GY}{ts}{R} {msg}")
    else:
        out.append(f"   {GY}--:--:--{R} {D}(none){R}")
    out.append("")
    out.append(f"  {GY}{'-'*46}{R}")
    out.append(f"  {D}r{R} rebuild  {D}f{R} fire  {D}s{R} status  "
               f"{D}h{R} help  {D}q{R} quit")
    out.append("")
    return "\r\n".join(out) + "\033[J"

def paint(force=False):
    if stdin_ready():
        _last_input[0] = time.time()
        return
    if time.time() - _last_input[0] < 0.4:
        return
    s = render()
    if not force and s == _last_render[0]:
        return
    _last_render[0] = s
    sys.stdout.write(s)
    sys.stdout.flush()

def add_event(msg):
    with lock:
        state["events"].append((time.strftime("%H:%M:%S"), msg))
    paint(force=True)

# ── SSE ──
def hold_sse(sess, path):
    while not stop.is_set():
        try:
            r = sess.get(TARGET + path, timeout=30, stream=True,
                         headers={"Accept": "text/event-stream",
                                  "Cache-Control": "no-cache"})
            with lock: state["sse_open"] += 1
            for _ in r.iter_lines(decode_unicode=True):
                if stop.is_set(): return
        except Exception:
            pass
        with lock:
            state["sse_open"] = max(0, state["sse_open"] - 1)
        if stop.is_set(): return
        time.sleep(0.5)

def start_sse(sess):
    threading.Thread(target=hold_sse,
                     args=(sess, "/admin/index?portaljs=1"), daemon=True).start()
    threading.Thread(target=hold_sse,
                     args=(sess, "/admin/index?insertcoin=1"), daemon=True).start()

# ── session ──
def build_session(cmac):
    s = requests.Session(); s.headers.update({"User-Agent": "Mozilla/5.0"})
    try:
        s.get(TARGET + "/", timeout=4)
        if cmac: s.cookies.set("cmac", cmac, domain="10.0.0.1")
        s.get(TARGET + "/portal", timeout=4)
        s.get(TARGET + "/", timeout=4)
    except Exception:
        return None
    return s

def rebuild(tag=""):
    now = time.time()
    with lock:
        if tag != "manual" and now - state["last_rebuild"] < REBUILD_CD:
            return
        state["last_rebuild"] = now
        state["sse_open"] = 0
        state["consec_3"] = 0
        state["status"] = "RBLD"
        if state["session"]:
            try: state["session"].close()
            except Exception: pass
        state["session"] = None
    paint(force=True)

    cmac = rand_mac() if ROTATE_MAC else None
    s = build_session(cmac)
    if s is None:
        with lock: state["status"] = "ERR "
        add_event(f"{RD}x{R} rebuild failed")
        return
    with lock:
        state["session"] = s
        state["cmac"] = cmac or s.cookies.get("cmac")
    start_sse(s)
    time.sleep(1.5)
    add_event(f"{MG}^{R} rebuild {tag}  {state['cmac'][-5:]}")

def fire():
    with lock: s = state["session"]
    if s is None: return None
    try:
        r = s.post(TARGET + "/admin/index?pfunc=1", timeout=4,
                   headers={"Referer": TARGET + "/portal",
                            "X-Requested-With": "XMLHttpRequest"})
        return r.text.strip()[:6]
    except Exception:
        return "ERR"

# ── loop ──
def loop():
    rebuild("startup")
    while not stop.is_set():
        body = fire()
        with lock:
            state["fires"] += 1
            state["history"].append(
                "2" if body == "2" else
                "E" if body != "3" else "3")
        if body == "2":
            with lock:
                state["renews"] += 1
                state["consec_3"] = 0
                state["status"] = "LIVE"
            add_event(f"{GR}*{R} renew #{state['renews']}  "
                      f"{state['cmac'][-5:]}")
        elif body == "3":
            with lock:
                state["consec_3"] += 1
                c3 = state["consec_3"]
                if state["status"] != "RBLD":
                    state["status"] = "WAIT"
            if c3 >= STALL:
                with lock:
                    state["stalls"] += 1
                    n = state["stalls"]
                rebuild(f"stall{n}")
        else:
            with lock: state["status"] = "ERR "
            add_event(f"{YL}~{R} unexpected: {body}")
        paint()
        d = time.time() + INTERVAL
        while time.time() < d:
            if stop.is_set(): return
            time.sleep(0.1)

# ── commands ──
def cmds():
    while not stop.is_set():
        try:
            sys.stdout.write("\r\033[K  ")
            sys.stdout.write(f"{CY}>{R} ")
            sys.stdout.flush()
            c = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            stop.set(); return
        _last_input[0] = time.time()
        if c == "q": stop.set(); return
        elif c == "r": rebuild("manual")
        elif c == "f":
            r = fire()
            add_event(f"{CY}*{R} fire  ->  {r!r}")
        elif c == "s":
            with lock:
                f, rn, st = state["fires"], state["renews"], state["stalls"]
                mac = state["cmac"]
            add_event(f"{CY}*{R} f{f} r{rn} s{st}  {mac}")
        elif c == "h":
            add_event(f"{D}r f s h q{R}")
        elif c:
            add_event(f"{D}? {c}{R}")

# ── main ──
def main():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    threading.Thread(target=loop, daemon=True).start()
    try:
        cmds()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        sys.stdout.write("\033[H\033[J")
        with lock:
            up = int(time.time() - state["started"])
            mm, ss = divmod(up, 60); hh, mm = divmod(mm, 60)
            print(f"\n  session ended")
            print(f"  uptime  {hh:02d}:{mm:02d}:{ss:02d}")
            print(f"  fires   {state['fires']}  renew {state['renews']}  "
                  f"stall {state['stalls']}")
            print(f"  mac     {state['cmac']}\n")
        sys.exit(0)

if __name__ == "__main__":
    main()
