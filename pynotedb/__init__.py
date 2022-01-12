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
import json
import os
from urllib.parse import urlparse
from sys import argv
from pathlib import Path
from functools import reduce
from typing import Callable, List, Iterator, NewType, Optional, Tuple, Union, Dict, Any
from pynotedb.utils import execute, ls, lsR, pread, sha1sum, try_action


# Create new types to avoid mis-usage
Email = NewType('Email', str)
Username = NewType('Username', str)
PubKey = NewType('PubKey', str)
Url = NewType('Url', str)
Uuid = NewType('Uuid', str)
Clone = NewType('Clone', Path)
Branch = NewType('Branch', str)
Ref = NewType('Ref', str)
ExternalScheme = NewType('ExternalScheme', str)

fetch_head = Ref('FETCH_HEAD')
meta_config = Ref('refs/meta/config')
meta_external_ids = Ref('refs/meta/external-ids')
meta_group_names = Ref('refs/meta/group-names')
scheme_gerrit = ExternalScheme('gerrit')
scheme_keycloak = ExternalScheme('keycloak-oauth')
scheme_username = ExternalScheme('username')
scheme_mail = ExternalScheme('mailto')

def is_mine(directory: Path) -> bool:
    return os.stat(directory).st_uid == os.getuid()

def parse_url(url: str) -> Url:
    if urlparse(url).scheme not in ('http', 'https', 'git'):
        raise RuntimeError("%s: expected url" % url)
    return Url(url)

def parse_path(url: str) -> Path:
    path = Path(url).resolve()
    if not path.exists() or not is_mine(path):
        raise RuntimeError("%s: expected writable directory" % url)
    return path

def parse_url_or_path(url: str) -> Union[Url, Path]:
    try:
        return parse_url(url)
    except RuntimeError:
        return parse_path(url)

def strip_git_suffix(url: str) -> str:
    return url[:-4] if url.endswith(".git") else url

def mk_clone(url: Union[Url, Path]) -> Clone:
    """Clone a project to ~/.cache/pynotedb/"""
    path = Path("~/.cache/pynotedb/" + strip_git_suffix(str(url)).split('/')[-1]).expanduser()
    if not path.exists():
        path.mkdir(parents=True)
        execute(["git", "clone", str(url), str(path)])
    else:
        execute(["git", "remote", "set-url", "origin", str(url)], cwd=path)
    return Clone(path)

def git(clone: Clone, args: List[str]) -> None:
    """A convenient wrapper around git commands"""
    execute(["git"] + args, cwd=clone)

def git_read(clone: Clone, args: List[str]) -> str:
    """A convenient reader around git commands"""
    return pread(["git"] + args, cwd=clone).decode('utf-8')

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

def mk_group_ref(group: Uuid) -> Ref:
    """Create a group ref"""
    return mk_ref("groups")(group)

def invert_ref_id(ref: Ref) -> Ref:
    """Invert a gerrit ref

    >>> invert_ref_id("refs/groups/CD/ABCD")
    'refs/groups/AB/ABCD'
    """
    r, g, _, i = ref.split('/')
    return Ref('/'.join([r, g, i[:2], i]))

def read_items(lines: List[str]) -> List[Tuple[str, str]]:
    """Read key values of git config file

    >>> read_items(["[group]", "  name = un name=avec ", "uuid=4242"])
    [('name', 'un name=avec'), ('uuid', '4242')]
    """
    return [(elems[0], elems[1])
            for elems in map(lambda s: list(map(str.strip, s.split("=", 1))), lines)
            if len(elems) == 2]

def read_group_name_uid(group_file: Path) -> Optional[Tuple[str, Uuid]]:
    """Return the name and uuid of a group config file"""
    name, uid = None, None
    for k, v in read_items(group_file.read_text().split('\n')):
        if k == "name":
            name = v
        elif k == "uuid":
            uid = v
    if name and uid:
        return (name, Uuid(uid))
    return None

def read_user_name(user_file: Path) -> Optional[str]:
    for k, v in read_items(user_file.read_text().split('\n')):
        if k == 'fullName':
            return v
    return None

def get_group_id(all_users: Clone, group_name: str) -> Optional[Tuple[Path, Uuid]]:
    """Return the file path and uid of a group name"""
    fetch_checkout(all_users, Branch("group_names"), meta_group_names)
    for fn in filter(lambda fp: fp.is_file(), ls(all_users)):
        group_info = read_group_name_uid(fn)
        if group_info:
            name, uid = group_info
            if name == group_name:
                return (fn, uid)
    return None

def get_user_id(user_ref: Ref) -> str:
    return user_ref.split('/')[-1]

def get_users_ref(all_users: Clone) -> Iterator[Ref]:
    """Return the list of user git refs"""
    return map(Ref,
               filter(lambda s: s.startswith("refs/users/") and s != "refs/users/self",
                      map(lambda s: s and s.split()[-1],
                          git_read(all_users, ["ls-remote"]).split('\n'))))

def get_user_ref(all_users: Clone, user: str) -> Optional[Ref]:
    """Return the user git ref"""
    for user_ref in get_users_ref(all_users):
        fetch_checkout(all_users, Branch("user_" + get_user_id(user_ref)), user_ref)
        if read_user_name(all_users / "account.config") == user:
            return user_ref
    return None

def lookup_sha_nest(root: Clone, sha: str, acc: int) -> Optional[int]:
    """Count nesting level for a given sha"""
    if sha == "":
        # The sha was not found
        return None
    if (root / sha).exists():
        return acc
    return lookup_sha_nest(root / sha[:2], sha[2:], acc + 1)

def nest_sha(root: Path, sha: str, nest: int) -> Path:
    """Split a sha for a given nesting level"""
    if nest == 0:
        return root / sha
    return nest_sha(root / sha[:2], sha[2:], nest - 1)

def write_obj(file_path : Path, file_content : List[str]) -> None:
    """Write a file and ensure parent directory exists"""
    if not file_path.parent.exists():
        file_path.parent.mkdir(parents=True)
    file_path.write_text("\n".join(file_content))

def write_sha_obj(root: Path, sha: str, nest: int, file_content: List[str]) -> None:
    """Write a sha object by respecting a nest level"""
    write_obj(nest_sha(root, sha, nest), file_content)

def show_external_id(scheme: ExternalScheme, username: str, account_id: str) -> List[str]:
    """Return an external id file content"""
    return [
        "[externalId \"" + scheme + ":" + username + "\"]",
        "\taccountId = " + account_id,
        ""
    ]

def write_gerrit_username_id_files(all_users: Clone, username: str, account_id: str, scheme: ExternalScheme) -> None:
    """Create an external id scheme for a given user"""
    # Lookup if the http external id is already created and get the current nest level
    http_sha = sha1sum(scheme_username + ":" + username)
    nest = lookup_sha_nest(all_users, http_sha, 0)
    if nest is None:
        nest = 1
        write_sha_obj(all_users, http_sha, nest, show_external_id(scheme_username, username, account_id))
    # Then write the desired external id scheme
    write_sha_obj(all_users, sha1sum(scheme + ":" + username), nest, show_external_id(scheme, username, account_id))

def add_account_external_id(all_users: Clone, username: str, account_id: str, scheme: ExternalScheme) -> None:
    """Create an account external id"""
    fetch_checkout(all_users, Branch("ids"), meta_external_ids)
    write_gerrit_username_id_files(all_users, username, account_id, scheme)
    git(all_users, ["add", "."])
    commit_and_push(all_users, "Add externalId for user " + username, meta_external_ids)

def delete_group(all_users_path: Path, group: str) -> None:
    all_users = mk_clone(all_users_path)
    group_path_id = get_group_id(all_users, group)
    if not group_path_id:
        raise RuntimeError("%s: group doesn't exists!" % group)
    group_path, group_id = group_path_id
    git(all_users, ["push", "--delete", "origin", invert_ref_id(mk_group_ref(group_id))])
    git(all_users, ["rm", str(group_path)])
    commit_and_push(all_users, "Remove group " + group, meta_group_names)

def list_external_ids(all_users: Clone) -> List[Path]:
    if not try_action(lambda: fetch_checkout(all_users, Branch("external_ids"), meta_external_ids)):
        return []
    return list(filter(lambda fp: fp.is_file(), lsR(all_users)))

def ext_id_match(headers: List[str], ext_id_file: Path) -> bool:
    ext_id_file_content = ext_id_file.read_text().split('\n')
    return any(filter(lambda h: h in ext_id_file_content, headers))

def get_user_external_id(all_users: Clone, user: Username, email: Email) -> List[Path]:
    headers = list(map(lambda sn: external_id_header(sn[0], sn[1]),
                       [(scheme_mail, email), (scheme_gerrit, user), (scheme_username, user)]))
    return [ext_id_file for ext_id_file in list_external_ids(all_users)
            if ext_id_match(headers, ext_id_file)]

def delete_user(all_users_path: Path, user: Username, email: Email) -> None:
    all_users = mk_clone(all_users_path)
    # Remove external id
    for user_external_id_file in get_user_external_id(all_users, user, email):
        git(all_users, ["rm", str(user_external_id_file)])
    commit_and_push(all_users, "Removing external id for user %s" % user, meta_external_ids)
    # Delete user ref
    user_ref = get_user_ref(all_users, user)
    if not user_ref:
        raise RuntimeError("%s: user doesn't exists!" % user)
    # TODO: delete group membership too?
    git(all_users, ["push", "--delete", "origin", user_ref])

def create_admin_user(email: Email, pubkey: PubKey, all_users_url: Union[Url, Path], scheme: ExternalScheme) -> None:
    """Ensure the admin user is created"""
    all_users = mk_clone(all_users_url)
    admin_ref = mk_user_ref("1")
    if not try_action(lambda: fetch(all_users, admin_ref)):
        # Add user to admin group
        admin_group_id = get_group_id(all_users, "Administrators")
        if not admin_group_id:
            raise RuntimeError("%s: Administrators group doesn't exists!" % all_users)
        admin_group_ref = mk_group_ref(admin_group_id[1])
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
        write_gerrit_username_id_files(all_users, "admin", "1", scheme)
        write_sha_obj(all_users, sha1sum("mailto:" + email), 1, [
            "[externalId \"mailto:" + email + "\"]",
            "\taccountId = 1",
            "\temail = " + email,
            ""
        ])
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

def create_gerrit_external_id(filename: Path) -> None:
    """Create a gerrit external id scheme for username scheme"""
    filecontent = filename.read_text()
    is_username = [fileline
                   for fileline in filecontent.split('\n')
                   if fileline.startswith("[externalId \"username:")]
    if is_username:
        extid = is_username[0].split("\"")[1]
        _scheme, name = extid.split(":", 1)
        newfilename = filename.parent / sha1sum("gerrit:" + name)
        newfilename.write_text(filecontent.replace(
            "[externalId \"username:",
            "[externalId \"gerrit:"))

def external_id_header(scheme: ExternalScheme, name: str) -> str:
    return "[externalId \"%s:%s\"]" % (scheme, name)

def migrate(all_projects_url: Union[Url, Path], all_users_url: Union[Url, Path]) -> None:
    """Migrate software factory notedb data from gerrit 2.x"""
    # Ensure admin can push notedb ref
    all_projects = mk_clone(all_projects_url)
    git(all_projects, ["config", "-f", "project.config", "access.refs/*.push",
                       "group Administrators", ".*group Administrators"])
    commit_and_push(all_projects, "Enable admin to push refs", meta_config)
    # Update externalId to use `gerrit` scheme instead of `username`
    all_users = mk_clone(all_users_url)
    if list(map(create_gerrit_external_id, list_external_ids(all_users))):
        git(all_users, ["add", "."])
        commit_and_push(all_users, "Update external id to gerrit scheme", meta_external_ids)

def migrate_su_group(repo_url: Union[Url, Path]) -> None:
    doc = "Rename 'Non-Interactive Users' group into 'Service Users', as per update to gerrit 3.4"
    niu = "Non-Interactive Users"
    su = "Service Users"
    repo = mk_clone(repo_url)
    fetch_checkout(repo, Branch("config"), meta_config)
    dirty = False

    groups = (repo / "groups").read_text()
    if niu in groups and su not in groups:
        (repo / "groups").write_text(groups.replace(niu, su))
        git(repo, ["add", "groups"])
        dirty = True

    acl = (repo / "project.config").read_text()
    if niu in acl:
        (repo / "project.config").write_text(acl.replace(niu, su))
        git(repo, ["add", "project.config"])
        dirty = True

    if dirty:
        commit_and_push(repo, doc, meta_config)

def gerrit_to_kc_external_id(filename: Path) -> None:
    filecontent = filename.read_text()
    is_username = [fileline
                   for fileline in filecontent.split('\n')
                   if fileline.startswith("[externalId \"gerrit:")]
    if is_username:
        extid = is_username[0].split("\"")[1]
        _scheme, name = extid.split(":", 1)
        newfilename = filename.parent / sha1sum(scheme_keycloak + ":" + name)
        newfilename.write_text(filecontent.replace(
            "[externalId \"gerrit:",
            "[externalId \"keycloak-oauth:"))

def migrate_to_keycloak(all_users_url: Union[Url, Path]) -> None:
    """Migrate users from cauth to keycloak."""
    all_users = mk_clone(all_users_url)
    if list(map(gerrit_to_kc_external_id, list_external_ids(all_users))):
       # stage new files, deleted files
       git(all_users, ["add", "-u", "."])
       git(all_users, ["add", "."])
       commit_and_push(all_users, "Migrate auth scheme to keycloak", meta_external_ids)

def list_users(all_users_url: Union[Url, Path]) -> List[Dict[Any, Any]]:
    """List all users currently known to Gerrit."""
    all_users = mk_clone(all_users_url)

    def extract_user_info(users_dict: Dict[Any, Any], filename: Path) -> Dict[Any, Any]:
        filecontent = filename.read_text()
        is_email = [fileline
                    for fileline in filecontent.split('\n')
                    if fileline.startswith('\temail = ')]
        is_accountId = [fileline
                        for fileline in filecontent.split('\n')
                        if fileline.startswith('\taccountId = ')]
        is_username = [fileline
                       for fileline in filecontent.split('\n')
                       if fileline.startswith('[externalId "username:')]
        if is_accountId:
            accountId = is_accountId[0].split(' = ')[1]
            if accountId not in users_dict:
                users_dict[accountId] = {}
            if is_email:
                email = is_email[0].split(' = ')[1]
                users_dict[accountId]['email'] = email
            if is_username:
                externalId = is_username[0].split('"')[1]
                _, username = externalId.split(':', 1)
                users_dict[accountId]['username'] = username
        return users_dict

    users_by_id: Dict[Any, Any] = reduce(extract_user_info, list_external_ids(all_users), {})
    return [
        {'id': id,
        'username': users_by_id[id].get('username'),
        'email': users_by_id[id].get('email')
        } for id in users_by_id
    ]



def main() -> None:
    """The CLI entrypoint"""
    def usage(argv: List[str]) -> argparse.Namespace:
        parser = argparse.ArgumentParser(description="notedb-tools")
        parser.add_argument("action", choices=["create-admin-user", "migrate",
                                               "delete-group", "delete-user",
                                               "cauth-to-keycloak",
                                               "migrate-group-su",
                                               "list-users"])
        parser.add_argument("--email", help="The user email address")
        parser.add_argument("--pubkey", help="The user SSH public key content")
        parser.add_argument("--repo", help="The name of the repo to migrate")
        parser.add_argument("--all-users", help="URL of the All-Users project")
        parser.add_argument("--all-projects", help="URL of the All-Projects project")
        parser.add_argument("--name", help="The name of the things to delete")
        parser.add_argument("--scheme", help='the auth scheme to use when creating the admin user',
                            choices=['gerrit', 'keycloak-oauth'],
                            default='gerrit')
        return parser.parse_args(argv)
    main_do(usage(argv[1:]))

def main_do(args: argparse.Namespace) -> None:
    if args.action == "create-admin-user":
        if not args.email or not args.pubkey or not args.all_users:
            raise RuntimeError("create-admin-user: needs email, pubkey and all-users argument")
        if not args.scheme or args.scheme == 'gerrit':
            scheme = scheme_gerrit
        else:
            scheme = scheme_keycloak
        create_admin_user(Email(args.email), PubKey(args.pubkey), parse_url_or_path(args.all_users), scheme)
    elif args.action == "migrate":
        if not args.all_projects or not args.all_users:
            raise RuntimeError("migrate: needs all-projects and all-users argument")
        migrate(parse_url_or_path(args.all_projects), parse_url_or_path(args.all_users))
    elif args.action == "migrate-group-su":
        if not args.repo:
            raise RuntimeError("migrate-group-su: needs repo argument")
        migrate_su_group(parse_url_or_path(args.repo))
    elif args.action == "cauth-to-keycloak":
        if not args.all_users:
            raise RuntimeError("cauth-to-keycloak: needs all-users argument")
        migrate_to_keycloak(parse_url_or_path(args.all_users))
    elif args.action == "delete-group":
        if not args.all_users or not args.name:
            raise RuntimeError("delete-group: needs all-users and name arguments")
        delete_group(parse_path(args.all_users), args.name)
    elif args.action == "delete-user":
        if not args.all_users or not args.name or not args.email:
            raise RuntimeError("delete-user: needs all-users, name and email arguments")
        delete_user(parse_path(args.all_users), Username(args.name), Email(args.email))
    elif args.action == "list-users":
        if not args.all_users:
            raise RuntimeError('list-users: needs all-users argument')
        print(
            json.dumps(
                list_users(parse_path(args.all_users)),
                indent=2
            )
        )
