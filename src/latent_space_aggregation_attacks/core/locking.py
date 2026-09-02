from __future__ import annotations
import os
from pathlib import Path

class UnitLock:
    def __init__(self, path: str | Path): self.path=Path(path); self.fd=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try:
            self.fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError as exc:
            try:
                pid=int(self.path.read_text(encoding="ascii").strip())
                os.kill(pid,0)
            except (ValueError, OSError):
                self.path.unlink(missing_ok=True)
                self.fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
            else:
                raise RuntimeError(f"Unit is locked by active pid {pid}: {self.path}") from exc
        os.write(self.fd,str(os.getpid()).encode("ascii")); os.fsync(self.fd); return self
    def __exit__(self,*_):
        if self.fd is not None: os.close(self.fd)
        self.path.unlink(missing_ok=True)
