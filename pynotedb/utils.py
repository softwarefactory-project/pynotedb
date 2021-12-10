# Copyright (c) 2020 Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from collections import Iterable
import subprocess
import os
import itertools
from pathlib import Path
from typing import Any, Callable, List, Optional, Iterator, TYPE_CHECKING
from hashlib import sha1


if TYPE_CHECKING:
    Proc = subprocess.Popen[Any]
else:
    Proc = Any

def wait_popen(proc: Proc) -> None:
    if proc.wait():
        args = isinstance(proc.args, Iterable) and [str(x) for x in proc.args] or [str(proc.args), ]
        raise RuntimeError("%s: failed" % ' '.join(args))

def execute(argv: List[str], cwd: Optional[Path] = None) -> None:
    """Execute command, raise an exception if it fails

    >>> execute(["ls", "/fail"])
    Traceback (most recent call last):
    ...
    RuntimeError: ls /fail: failed
    """
    wait_popen(subprocess.Popen(argv, cwd=cwd))

def pread(argv: List[str], cwd: Optional[Path] = None) -> bytes:
    """Return command outputs, raise an exception if it fails

    >>> pread(["dd", "if=/dev/zero", "bs=2", "count=1"])
    b'\\x00\\x00'
    """
    proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE)
    stdout, _ = proc.communicate()
    wait_popen(proc)
    return stdout

def try_action(action: Callable[[], None]) -> bool:
    """Return True if an action succeed, otherwise false

    >>> try_action(lambda: 1/0)
    False
    >>> try_action(lambda: None)
    True
    """
    try:
        action()
        return True
    except:
        return False

def ls(root: Path) -> Iterator[Path]:
    """List a directory and return absolute path"""
    return map(lambda fn: root / fn, os.listdir(root))

def lsR(root: Path) -> Iterator[Path]:
    """Recursive list a directory and return absolute path"""
    return filter(lambda p: ".git" not in p.parts, itertools.chain.from_iterable(
        map(
            lambda lsdir: list(map(lambda f: Path(lsdir[0]) / f, lsdir[2])),
            os.walk(root),
        )
    ))

def sha1sum(strdata: str) -> str:
    """Create a sha1

    >>> sha1sum('username:admin')
    'b54915000d281bb92f990131b8356c67fa065353'
    """
    m = sha1()
    m.update(strdata.encode('utf8'))
    return m.hexdigest()
