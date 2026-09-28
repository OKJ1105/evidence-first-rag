"""`deploy-v0.1` Section 8.1: the deployed cases read off Azure's own resource state.

`DP-014`, the registry and its role assignments, and the app-settings half of
`DP-003`, run by the deploy job after the template is applied. Every read goes
through `az`, which takes the Azure CLI's arguments and returns its parsed JSON
output; the job passes the real one and the tests a stand-in.

Each case returns `(passed, detail)` and never raises for a failed expectation.
A detail names roles, setting names and tags, never a setting's value, a
principal's identifier or a host.
"""

import argparse
import json
import subprocess
import sys

ACR_PULL = "AcrPull"
ACR_PUSH = "AcrPush"
PUSH_CAPABLE = {ACR_PUSH, "Owner", "Contributor", "AcrImageSigner"}
REGISTRY_CREDENTIAL_SETTINGS = {
    "DOCKER_REGISTRY_SERVER_USERNAME",
    "DOCKER_REGISTRY_SERVER_PASSWORD",
}
MUTABLE_TAGS = {"latest"}


def run_az(*arguments):
    """The real `az`: one call, JSON out, an error raised with its message."""
    completed = subprocess.run(
        ["az", *arguments, "--output", "json"], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(f"az {arguments[0]} {arguments[1] if len(arguments) > 1 else ''} failed")
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


def dp014_roles(az, group, registry, surface, relay, deploy_identity):
    """The only assignments on the registry are the three registered ones."""
    scope = az("acr", "show", "--resource-group", group, "--name", registry)["id"]
    principals = {
        "surface": az("webapp", "identity", "show", "--resource-group", group, "--name", surface)["principalId"],
        "relay": az("webapp", "identity", "show", "--resource-group", group, "--name", relay)["principalId"],
        "deploy": az("identity", "show", "--resource-group", group, "--name", deploy_identity)["principalId"],
    }
    names = {principal: name for name, principal in principals.items()}
    assignments = az("role", "assignment", "list", "--scope", scope)
    found = sorted(
        (names.get(entry.get("principalId"), "another principal"), entry.get("roleDefinitionName"))
        for entry in assignments
        if entry.get("scope") == scope
    )
    expected = sorted([("deploy", ACR_PUSH), ("relay", ACR_PULL), ("surface", ACR_PULL)])
    pushing_apps = [name for name, role in found if name in ("surface", "relay") and role in PUSH_CAPABLE]
    passed = found == expected and not pushing_apps
    return passed, f"assignments on the registry: {found}"


def _settings(az, group, app):
    return {entry["name"] for entry in az("webapp", "config", "appsettings", "list", "--resource-group", group, "--name", app)}


def dp014_settings(az, group, surface, relay):
    """No app setting carries a registry user name, password or token."""
    carried = {
        app: sorted(_settings(az, group, app) & REGISTRY_CREDENTIAL_SETTINGS) for app in (surface, relay)
    }
    passed = not any(carried.values())
    return passed, "no registry credential setting" if passed else f"registry credential settings: {carried}"


def dp014_image(az, group, app, commit):
    """The app's configured image names this commit's tag, not a mutable one."""
    fx = az("webapp", "config", "show", "--resource-group", group, "--name", app).get("linuxFxVersion") or ""
    tag = fx.rsplit(":", 1)[-1] if ":" in fx else ""
    passed = fx.startswith("DOCKER|") and tag == commit and tag not in MUTABLE_TAGS
    return passed, f"tag {tag or '(none)'}"


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
        "DP-014 roles": (dp014_roles, az, group, registry, surface, relay, deploy_identity),
        "DP-014 settings": (dp014_settings, az, group, surface, relay),
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
    results = run(
        run_az, arguments.group, arguments.registry, arguments.surface,
        arguments.relay, arguments.deploy_identity, arguments.commit,
    )
    with open(arguments.out, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    for case, result in results.items():
        print(("ok  " if result["passed"] else "FAIL"), case, "-", result["detail"])
    return 0 if all(result["passed"] for result in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
