import sys, time, _thread, threading, zipimport, marshal, builtins
print('version', sys.version)
print('sys.path', sys.path)
print('builtin modules', sys.builtin_module_names)
print('has _current_frames', hasattr(sys, '_current_frames'), 'setprofile', hasattr(sys, 'setprofile'), 'settrace', hasattr(sys, 'settrace'))
print('switchinterval', sys.getswitchinterval())
print('perf_counter', time.perf_counter(), time.get_clock_info('perf_counter'))
print('thread_time', time.thread_time())
import cProfile, pstats, _lsprof
print('cProfile ok', cProfile.Profile)
print('meta_path', sys.meta_path)
print('path_hooks', sys.path_hooks)
res = []
def worker():
    res.append(threading.get_ident())
t = threading.Thread(target=worker); t.start(); t.join()
print('thread ran', res, 'main', threading.get_ident())
print('frames', list(sys._current_frames().keys()))
sys.stdout.flush()
