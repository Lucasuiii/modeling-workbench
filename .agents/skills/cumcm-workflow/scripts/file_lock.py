"""Cross-platform process lock used by workspace recorders."""
import errno
import os
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(path: Path, *, wait: bool = True):
    """Lock a stable sidecar through close. Never unlink it while callers may be opening it."""
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            # msvcrt.locking locks from the current file position. A real byte
            # is required; two creators may append it concurrently, but both
            # still lock byte zero and never truncate the lock file.
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            while True:
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    if not wait:
                        raise BlockingIOError(f"lock busy: {path}") from exc
                    time.sleep(0.05)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)
