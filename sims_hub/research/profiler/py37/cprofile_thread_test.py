import sys, threading, cProfile
p = cProfile.Profile()
p.enable()
t = threading.Thread(target=p.disable); t.start(); t.join()
print('after disable() from another thread, main thread still profiled:', sys.getprofile() is not None)
p.disable()
print('after disable() on main thread:', sys.getprofile() is not None)
sys.stdout.flush()
