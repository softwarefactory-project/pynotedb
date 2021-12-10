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

def ensure_git_config():
    os.environ.setdefault("HOME", str(Path("~/").expanduser()))
    if any(map(lambda p: p.expanduser().exists(), [Path("~/.gitconfig"), Path("~/.config/git/config")])):
        return
    pynotedb.execute(["git", "config", "--global", "user.email", "you@example.com"])
    pynotedb.execute(["git", "config", "--global", "user.name", "Your Name"])


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
    execute(["cp", ".git/refs/meta/config", ".git/refs/meta/external-ids"], test_repo)
    (test_repo / ".git/refs/groups/12").mkdir(parents=True)
    execute(["cp", ".git/refs/meta/config", ".git/refs/groups/12/12345"], test_repo)
    pynotedb.new_orphan(test_repo, "group_names")
    (test_repo / "4243").write_text("\n".join(["[group]", "  name = test group", "  uuid = 54321", ""]))
    (test_repo / "1245").write_text("\n".join(["[group]", "  name = Administrators", "  uuid = 12345", ""]))
    pynotedb.git(test_repo, ["add", "4243", "1245"])
    pynotedb.git(test_repo, ["commit", "-m", "init test group"])
    execute(["mv", ".git/refs/heads/group_names", ".git/refs/meta/group-names"], test_repo)
    (test_repo / ".git/refs/groups/54").mkdir(parents=True)
    execute(["cp", ".git/refs/groups/12/12345", ".git/refs/groups/54/54321"], test_repo)


def check_admin_user_created(test_repo):
    pynotedb.git(test_repo, ["ls-tree", "refs/users/01/1"])


def check_admin_user_delete(test_repo):
    pynotedb.delete_user(test_repo, "Administrator", "admin@localhost")
    if "refs/users/01/1" in pynotedb.git_read(pynotedb.mk_clone(test_repo), ["ls-remote"]):
        raise RuntimeError("Administrator user ref still exists")
    try:
        pynotedb.delete_user(test_repo, "Administrator", "admin@localhost")
        raise RuntimeError("Second Administrator deletion should have failed")
    except RuntimeError:
        pass


def check_delete_group(test_repo, group_name):
    pynotedb.delete_group(test_repo, group_name)
    try:
        pynotedb.delete_group(test_repo, group_name)
    except RuntimeError:
        return
    raise RuntimeError("Second %s group deletion should have failed" % group_name)

def assertEq(note, a, b):
    if a != b:
        raise RuntimeError("%s, expected: %s, got: %s" % (note, b, a))

def check_nest_func(test_repo):
    sha = pynotedb.sha1sum("test")
    assertEq(
        "nesting 1 failed",
        pynotedb.nest_sha(test_repo, sha, 1),
        (test_repo / sha[:2] / sha[2:]))

class TestPyNoteDb(unittest.TestCase):
    def setUp(self):
        ensure_git_config()
        cache = Path("~/.cache/pynotedb").expanduser()
        execute(["rm", "-Rf", str(cache)])
        self.test_repo = cache / "users.git"
        create_all_users(self.test_repo)

    def test_create_admin_user(self):
        pynotedb.create_admin_user("admin@localhost", "ssh-rsa key", str(self.test_repo), "gerrit")
        check_admin_user_created(self.test_repo)
        users = pynotedb.list_users(self.test_repo)
        if len(users) != 1:
            raise RuntimeError("users list should have one element: %s" % users)
        admin = users[0]
        if admin['id'] != '1' or admin.get('username') != "admin" or admin.get('email') != 'admin@localhost':
            raise RuntimeError('invalid admin user info: %s' % admin)
        check_admin_user_delete(self.test_repo)

    def test_add_account_external_id(self):
        repo = pynotedb.mk_clone(str(self.test_repo))
        pynotedb.fetch_checkout(repo, "extids", "refs/meta/external-ids")
        pynotedb.add_account_external_id(repo, "john", "42", "gerrit")

    def test_delete_group(self):
        check_delete_group(self.test_repo, "test group")

    def test_parser(self):
        url = "git://gerrit/All-Users.git"
        path = str(self.test_repo)
        self.assertIsNotNone(pynotedb.parse_url(url))
        self.assertRaises(RuntimeError, pynotedb.parse_url, path)
        self.assertIsNotNone(pynotedb.parse_path(path))
        self.assertRaises(RuntimeError, pynotedb.parse_path, url)
        self.assertIsNotNone(pynotedb.parse_url_or_path(url))
        self.assertIsNotNone(pynotedb.parse_url_or_path(path))

    def test_illegal_actions(self):
        def fake_args(**kw):
            return type("argparse.Namespace", (), kw)
        self.assertRaises(RuntimeError, pynotedb.main_do, fake_args(
            action="delete-group", name="fake", all_users="git://gerrit/All-Users.git"))
        self.assertRaises(RuntimeError, pynotedb.main_do, fake_args(
            action="delete-user", name="fake", email="fake", all_users="git://gerrit/All-Users.git"))

    def test_sha_nest(self):
        check_nest_func(self.test_repo)

if __name__ == '__main__':
    unittest.main()
