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

import argparse
from sys import argv
from pathlib import Path
from typing import Callable, List, NewType, Optional
from pynotedb.utils import execute, sha1sum, try_action


# Create new types to avoid mis-usage
Email = NewType('Email', str)
PubKey = NewType('PubKey', str)
Url = NewType('Url', str)
Clone = NewType('Clone', Path)
Branch = NewType('Branch', str)
Ref = NewType('Ref', str)
ExternalScheme = NewType('ExternalScheme', str)

fetch_head = Ref('FETCH_HEAD')
meta_config = Ref('refs/meta/config')
meta_external_ids = Ref('refs/meta/external-ids')
scheme_gerrit = ExternalScheme('gerrit')
scheme_username = ExternalScheme('username')

def mk_clone(url: Url) -> Clone:
    """Clone a project to ~/.cache/pynotedb/"""
    path = Path("~/.cache/pynotedb/" + (url[:-4] if url.endswith(".git") else url).split('/')[-1]).expanduser()
    if not path.exists():
        path.mkdir(parents=True)
        execute(["git", "clone", url, str(path)])
    else:
        execute(["git", "remote", "set-url", "origin", url], cwd=path)
    return Clone(path)

def git(clone: Clone, args: List[str]) -> None:
    """A convenient wrapper around git commands"""
    execute(["git"] + args, cwd=clone)

def fetch(clone: Clone, ref: Ref) -> None:
    """fetch a ref"""
    git(clone, ["fetch", "origin", ref])

def checkout(clone: Clone, branch: Branch, ref: Ref) -> None:
    """checkout a ref, raising an exception if it doesn't exists"""
    git(clone, ["checkout", "-B", branch, ref])

def fetch_checkout(clone: Clone, branch: Branch, ref: Ref) -> None:
    """fetch a ref and check it out"""
    fetch(clone, ref)
    checkout(clone, branch, fetch_head)

def commit_and_push(clone: Clone, message: str, ref: Ref) -> None:
    try_action(lambda: git(clone, ["commit", "-a", "-m", message]))
    # TODO: check if ref is already pushed
    try_action(lambda: git(clone, ["push", "origin", "HEAD:" + ref]))

def new_orphan(clone: Clone, branch: Branch) -> None:
    """create a new orphan commit"""
    try_action(lambda: git(clone, ["branch", "-D", branch]))
    git(clone, ["checkout", "--orphan", branch])
    git(clone, ["rm", "--cached", "-r", "--", "."])
    git(clone, ["clean", "-d", "-f", "-x"])

def mk_ref_id(refname: str) -> str:
    """Create gerrit CD/ABCD name, refname must not be empty.

    >>> mk_ref_id("1")
    '01/1'
    >>> mk_ref_id("41242")
    '42/41242'
    """
    refid = refname[-2:] if len(refname) > 1 else ("0" + refname[-1])
    return refid + "/" + refname

def mk_ref(name: str) -> Callable[[str], Ref]:
    def func(refname: str) -> Ref:
        return Ref("refs/" + name + "/" + mk_ref_id(refname))
    return func

def mk_user_ref(user: str) -> Ref:
    """Create a user ref

    >>> mk_user_ref("1")
    'refs/users/01/1'
    """
    return mk_ref("users")(user)

def mk_group_ref(group: str) -> Ref:
    """Create a group ref"""
    return mk_ref("groups")(group)

def invert_ref_id(ref: Ref) -> Ref:
    """Invert a gerrit ref

    >>> invert_ref_id("refs/groups/CD/ABCD")
    'refs/groups/AB/ABCD'
    """
    r, g, _, i = ref.split('/')
    return Ref('/'.join([r, g, i[:2], i]))

def get_group_id(all_users: Clone, group_name: str) -> Optional[str]:
    fetch_checkout(all_users, Branch("meta_config"), meta_config)
    groups = (all_users / "groups").read_text()
    group = list(
        filter(lambda s: s and s[-1] == group_name,
               map(str.split, groups.split("\n"))))
    if len(group) == 1:
        return group[0][0]
    return None

def write_external_id_file(all_users: Clone, scheme: ExternalScheme, username: str, account_id: str) -> None:
    (all_users / sha1sum(scheme + ":" + username)).write_text("\n".join([
        "[externalId \"" + scheme + ":" + username + "\"]",
        "\taccountId = " + account_id,
        ""
    ]))

def write_gerrit_username_id_files(all_users: Clone, username: str, account_id: str) -> None:
    """Create a ssh and http account external id"""
    write_external_id_file(all_users, scheme_gerrit, username, account_id)
    write_external_id_file(all_users, scheme_username, username, account_id)

def add_account_external_id(all_users: Clone, username: str, account_id: str) -> None:
    """Create an account external id"""
    fetch_checkout(all_users, Branch("ids"), meta_external_ids)
    write_gerrit_username_id_files(all_users, username, account_id)
    git(all_users, ["add", "."])
    commit_and_push(
        all_users, "Add externalId for user " + username, meta_external_ids)

def create_admin_user(email: Email, pubkey: PubKey, all_users_url: Url) -> None:
    """Ensure the admin user is created"""
    all_users = mk_clone(all_users_url)
    admin_ref = mk_user_ref("1")
    if not try_action(lambda: fetch(all_users, admin_ref)):
        # Add user to admin group
        admin_group_id = get_group_id(all_users, "Administrators")
        if not admin_group_id:
            raise RuntimeError("%s: Administrators group doesn't exists!" % all_users)
        admin_group_ref = mk_group_ref(admin_group_id)
        if not try_action(lambda: fetch_checkout(all_users, Branch("group_admin"), admin_group_ref)):
            # For some reason, group ref can be AB/ABCD
            admin_group_ref = invert_ref_id(admin_group_ref)
            fetch_checkout(all_users, Branch("group_admin"), admin_group_ref)
        members_file = all_users / "members"
        if members_file.exists():
            members = members_file.read_text().split('\n')
        else:
            members = []
        if "1" not in members:
            members_file.write_text("\n".join(members + ["1", ""]))
        git(all_users, ["add", "members"])
        commit_and_push(all_users, "Add admin user to Administrators group", admin_group_ref)

        # Create externalId
        if not try_action(lambda: fetch_checkout(all_users, Branch("external_ids"), meta_external_ids)):
            new_orphan(all_users, Branch("external_ids"))
        write_gerrit_username_id_files(all_users, "admin", "1")
        (all_users / sha1sum("mailto:" + email)).write_text("\n".join([
            "[externalId \"mailto:" + email + "\"]",
            "\taccountId = 1",
            "\temail = " + email,
            ""
        ]))
        git(all_users, ["add", "."])
        commit_and_push(all_users, "Add admin external id", meta_external_ids)

        # Create user
        new_orphan(all_users, Branch("user_admin"))
        (all_users / "account.config").write_text("\n".join([
            "[account]",
            "\tfullName = Administrator",
            "\tpreferredEmail = " + email,
            ""
        ]))
        (all_users / "authorized_keys").write_text(pubkey + "\n")
        git(all_users, ["add", "account.config", "authorized_keys"])
        commit_and_push(all_users, "Initialize admin user", admin_ref)

def main() -> None:
    """The CLI entrypoint"""
    def usage(argv: List[str]) -> argparse.Namespace:
        parser = argparse.ArgumentParser(description="notedb-tools")
        parser.add_argument("action", choices=["create-admin-user"])
        parser.add_argument("--fqdn", help="The FDQN for admin email")
        parser.add_argument("--pubkey", help="SSH public key content")
        parser.add_argument("--all-users", help="URL of the All-Users project")
        return parser.parse_args(argv)
    args = usage(argv[1:])
    if args.action == "create-admin-user":
        if not args.fqdn or not args.pubkey or not args.all_users:
            raise RuntimeError("create-admin-user: needs fqdn, pubkey and all-users argument")
        create_admin_user(Email("admin@" + args.fqdn), PubKey(args.pubkey), Url(args.all_users))
