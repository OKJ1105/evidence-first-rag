"""`deploy-v0.1` Section 8.1: the deployed cases read off Azure's own resource state.

`DP-014`, the registry and its role assignments, and the app-settings half of
`DP-003`, run by the deploy job after the template is applied. Every read goes
through `az`, which takes the Azure CLI's arguments and returns its parsed JSON
output; the job passes the real one and the tests a stand-in.

Each case returns `(passed, detail)` and never raises for a failed expectation.
A detail names roles, setting names, token names and tags, never a setting's
value, a registry user name or password, a principal's identifier or a host.
"""

import argparse
import json
import re
import subprocess
import sys

ACR_PULL = "AcrPull"
ACR_PUSH = "AcrPush"
PUSH_CAPABLE = {ACR_PUSH, "Owner", "Contributor", "AcrImageSigner"}
REGISTRY_CREDENTIAL_SETTINGS = {
    "DOCKER_REGISTRY_SERVER_USERNAME",
    "DOCKER_REGISTRY_SERVER_PASSWORD",
}
# A registry credential is a credential whatever it is named, so a setting is
# matched on what it carries as well as on the two platform names above.
REGISTRY_SHAPED_NAME = re.compile(r"REGISTRY|ACR|DOCKER", re.IGNORECASE)
KEY_VAULT_REFERENCE = re.compile(r"^@Microsoft\.KeyVault\(", re.IGNORECASE)
MUTABLE_TAGS = {"latest"}


class AzError(RuntimeError):
    """An `az` call that failed. `output` is its error text, read only to
    classify the failure and never written to a record."""

    def __init__(self, message, output=""):
        super().__init__(message)
        self.output = output or ""


# How Azure answers a feature the registry's tier does not offer. Where tokens
# cannot exist, none does (#241 N7); the wording is unverified until the first
# deploy, which is why any other failure still fails the case.
UNSUPPORTED_ON_TIER = ("sku", "not supported", "premium")


def run_az(*arguments):
    """The real `az`: one call, JSON out, an error raised with its message."""
    completed = subprocess.run(
        ["az", *arguments, "--output", "json"], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise AzError(f"az {arguments[0]} {arguments[1] if len(arguments) > 1 else ''} failed", completed.stderr)
    return json.loads(completed.stdout or "null")


def _guarded(case, *arguments):
    try:
        return case(*arguments)
    except Exception as error:  # noqa: BLE001 - one case failing must not hide the rest
        return False, f"the check itself failed: {type(error).__name__}"


def dp014_registry(az, group, registry):
    """The admin user and anonymous pull are both disabled."""
    shown = az("acr", "show", "--resource-group", group, "--name", registry)
    admin = shown.get("adminUserEnabled")
    anonymous = shown.get("anonymousPullEnabled")
    passed = admin is False and anonymous is False
    return passed, f"adminUserEnabled={admin}, anonymousPullEnabled={anonymous}"


def dp014_credential(az, group, registry):
    """No credential exists for the registry: no token, and no admin credential.

    A repository-scoped token is available on the Basic tier and carries a
    generated push password, so a disabled admin user does not on its own settle
    Section 4.3's "no password or token exists". Both are read here. `az acr
    credential show` refuses while the admin user is disabled; a refusal is
    therefore the passing answer, and success means a credential is readable.
    A refusal for some other reason — throttling, a role not yet effective —
    reads the same way, which is why it is not the only evidence for that
    clause: `dp014_registry` reads `adminUserEnabled` directly. The token read
    has no second reader, so a failure there fails this case closed.
    The detail names token names only, never a user name or a password.
    """
    try:
        listed = az("acr", "token", "list", "--registry", registry) or []
        tier_note = ""
    except AzError as error:
        if not any(term in error.output.lower() for term in UNSUPPORTED_ON_TIER):
            raise
        listed, tier_note = [], " (tokens are not offered on this tier)"
    tokens = sorted(entry.get("name") or "(unnamed)" for entry in listed)
    try:
        az("acr", "credential", "show", "--resource-group", group, "--name", registry)
    except Exception:  # noqa: BLE001 - a refusal is the expected, passing answer
        admin_credential = False
    else:
        admin_credential = True
    passed = not tokens and not admin_credential
    return passed, (
        f"tokens: {tokens or 'none'}{tier_note}; "
        f"admin credential: {'readable' if admin_credential else 'none'}"
    )


def dp014_roles(az, group, registry, surface, relay, deploy_identity):
    """The only assignments on the registry are the three registered ones."""
    scope = az("acr", "show", "--resource-group", group, "--name", registry)["id"]
    principals = {
        "surface": az("webapp", "identity", "show", "--resource-group", group, "--name", surface)["principalId"],
        "relay": az("webapp", "identity", "show", "--resource-group", group, "--name", relay)["principalId"],
        "deploy": az("identity", "show", "--resource-group", group, "--name", deploy_identity)["principalId"],
    }
    names = {principal: name for name, principal in principals.items()}
    # ARM identifiers compare without case (#241 N5).
    scope_key = scope.lower()
    assignments = az("role", "assignment", "list", "--scope", scope, "--include-inherited")
    found = sorted(
        (names.get(entry.get("principalId"), "another principal"), entry.get("roleDefinitionName"))
        for entry in assignments
        if (entry.get("scope") or "").lower() == scope_key
    )
    expected = sorted([("deploy", ACR_PUSH), ("relay", ACR_PULL), ("surface", ACR_PULL)])
    # A push-capable role an app inherits from any scope above the registry
    # counts as one on it (#241 N6).
    pushing_apps = sorted(
        (names[entry.get("principalId")], entry.get("roleDefinitionName"))
        for entry in assignments
        if names.get(entry.get("principalId")) in ("surface", "relay")
        and entry.get("roleDefinitionName") in PUSH_CAPABLE
    )
    passed = found == expected and not pushing_apps
    detail = f"assignments on the registry: {found}"
    if pushing_apps:
        detail += f"; push-capable roles held by an app: {pushing_apps}"
    return passed, detail


def _setting_entries(az, group, app):
    return az("webapp", "config", "appsettings", "list", "--resource-group", group, "--name", app)


def _settings(az, group, app):
    return {entry["name"] for entry in _setting_entries(az, group, app)}


def dp014_settings(az, group, registry, surface, relay):
    """No app setting carries a registry user name, password or token.

    Matched on what a setting carries, not only on the two platform names: a
    value naming the registry's login server, and a registry-shaped name whose
    value is not a Key Vault reference, are both a registry credential under
    whatever name they were written. Only the setting's name reaches the detail.
    """
    login_server = (
        az("acr", "show", "--resource-group", group, "--name", registry).get("loginServer") or ""
    ).lower()
    if not login_server:
        # Without it one of the three clauses cannot be decided, so the case
        # fails rather than reporting what the other two found.
        return False, "the registry's login server could not be read"
    carried = {}
    for app in (surface, relay):
        names = []
        for entry in _setting_entries(az, group, app):
            name = entry["name"]
            value = entry.get("value") or ""
            if name in REGISTRY_CREDENTIAL_SETTINGS:
                names.append(name)
            elif login_server in value.lower():
                names.append(name)
            elif REGISTRY_SHAPED_NAME.search(name) and not KEY_VAULT_REFERENCE.match(value):
                names.append(name)
        if names:
            carried[app] = sorted(names)
    passed = not carried
    return passed, "no registry credential setting" if passed else f"registry credential settings: {carried}"


def dp014_image(az, group, app, commit):
    """The app's configured image names this commit's tag, pulled by identity.

    The same payload carries `acrUseManagedIdentityCreds`, which is how the
    platform records that the pull is by role rather than by a stored registry
    credential, so it is asserted here rather than read a second time.
    """
    configuration = az("webapp", "config", "show", "--resource-group", group, "--name", app)
    fx = configuration.get("linuxFxVersion") or ""
    managed = configuration.get("acrUseManagedIdentityCreds")
    tag = fx.rsplit(":", 1)[-1] if ":" in fx else ""
    passed = (
        fx.startswith("DOCKER|") and tag == commit and tag not in MUTABLE_TAGS and managed is True
    )
    return passed, f"tag {tag or '(none)'}, acrUseManagedIdentityCreds={managed}"


def dp003_settings(az, group, surface, relay):
    """Neither app holds the other's credential (`DP-003`, the settings half)."""
    surface_names = _settings(az, group, surface)
    relay_names = _settings(az, group, relay)
    problems = []
    if "ANTHROPIC_API_KEY" in surface_names:
        problems.append("surface names ANTHROPIC_API_KEY")
    if relay_names & {"MVP_RUNTIME_PASSWORD", "MVP_PROVISIONING_PASSWORD", "PGPASSWORD"}:
        problems.append("relay names a database credential")
    return (not problems), "; ".join(problems) or "neither app names the other's credential"


def run(az, group, registry, surface, relay, deploy_identity, commit):
    cases = {
        "DP-014 registry": (dp014_registry, az, group, registry),
        "DP-014 credential": (dp014_credential, az, group, registry),
        "DP-014 roles": (dp014_roles, az, group, registry, surface, relay, deploy_identity),
        "DP-014 settings": (dp014_settings, az, group, registry, surface, relay),
        "DP-014 surface image": (dp014_image, az, group, surface, commit),
        "DP-014 relay image": (dp014_image, az, group, relay, commit),
        "DP-003 settings": (dp003_settings, az, group, surface, relay),
    }
    results = {}
    for name, (case, *arguments) in cases.items():
        passed, detail = _guarded(case, *arguments)
        results[name] = {"passed": passed, "detail": detail}
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("group", "registry", "surface", "relay", "deploy-identity", "commit"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--out", default="azure-checks.json")
    arguments = parser.parse_args(argv)
    results = {}
    try:
        results.update(run(
            run_az, arguments.group, arguments.registry, arguments.surface,
            arguments.relay, arguments.deploy_identity, arguments.commit,
        ))
    finally:
        # The record is the evidence, so it is written however the run ended.
        with open(arguments.out, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2)
    for case, result in results.items():
        print(("ok  " if result["passed"] else "FAIL"), case, "-", result["detail"])
    return 0 if all(result["passed"] for result in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
