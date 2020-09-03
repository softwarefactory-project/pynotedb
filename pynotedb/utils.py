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

import subprocess
from pathlib import Path
from typing import Callable, List, Optional
from hashlib import sha1


def execute(argv: List[str], cwd: Optional[Path] = None) -> None:
    """Returns command output, raise an exception if the command failed

    >>> execute(["ls", "/fail"])
    Traceback (most recent call last):
    ...
    RuntimeError: ls /fail: failed
    """
    if subprocess.Popen(argv, cwd=cwd).wait():
        raise RuntimeError("%s: failed" % ' '.join(argv))

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

def sha1sum(strdata: str) -> str:
    """Create a sha1

    >>> sha1sum('username:admin')
    'b54915000d281bb92f990131b8356c67fa065353'
    """
    m = sha1()
    m.update(strdata.encode('utf8'))
    return m.hexdigest()
