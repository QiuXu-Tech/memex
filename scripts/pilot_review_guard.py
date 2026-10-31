"""Stop scheduling a reviewer after its provider explicitly rejects access."""
import threading

class ReviewGuard:
 def __init__(self):self._lock=threading.Lock();self._blocked=set()
 def is_blocked(self,model):
  with self._lock:return model in self._blocked
 def block(self,model):
  with self._lock:self._blocked.add(model)
