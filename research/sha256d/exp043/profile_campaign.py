import cProfile
import pstats
import signal
import sys

sys.path.insert(
    0, "/home/hatch/workspace/bitcoin-autonomous-lab/research/"
       "sha256d/exp043")
import campaign_bench as cb  # noqa: E402


def handler(sig, frame):
    raise KeyboardInterrupt


signal.signal(signal.SIGALRM, handler)
signal.alarm(100)
pr = cProfile.Profile()
pr.enable()
try:
    cb.run_trial(46200, 32, True)
    print("TRIAL COMPLETED (unexpected)")
except KeyboardInterrupt:
    print("interrupted at 100 s as planned")
pr.disable()
st = pstats.Stats(pr)
st.sort_stats("tottime")
st.print_stats(16)
