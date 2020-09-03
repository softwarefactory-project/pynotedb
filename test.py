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

import os
import unittest
import pynotedb
from pynotedb.utils import execute
from pathlib import Path


def create_all_users(test_repo):
    test_repo.mkdir(parents=True)
    execute(["git", "init", test_repo])
    (test_repo / "groups").write_text("""# groups...
    12345 Administrators
    """)
    pynotedb.git(test_repo, ["add", "groups"])
    pynotedb.git(test_repo, ["commit", "-m", "init"])
    (test_repo / ".git/refs/meta").mkdir()
    execute(["mv", ".git/refs/heads/master", ".git/refs/meta/config"], test_repo)
    (test_repo / ".git/refs/groups/12").mkdir(parents=True)
    execute(["cp", ".git/refs/meta/config", ".git/refs/groups/12/12345"], test_repo)


def check_admin_user_created(test_repo):
    pynotedb.git(test_repo, ["ls-tree", "refs/users/01/1"])


class TestPyNoteDb(unittest.TestCase):
    def setUp(self):
        cache = Path("~/.cache/pynotedb").expanduser()
        execute(["rm", "-Rf", str(cache)])
        self.test_repo = cache / "users.git"
        create_all_users(self.test_repo)

    def test_create_admin_user(self):
        pynotedb.create_admin_user("admin@localhost", "ssh-rsa key", str(self.test_repo))
        check_admin_user_created(self.test_repo)


if __name__ == '__main__':
    unittest.main()
