"""`deploy-v0.1` `DP-014` and the settings half of `DP-003`, against a stand-in `az`."""

import copy
import unittest

from evidence_first_rag.deploy import azure_checks as checks

COMMIT = "a" * 40
SCOPE = "/subscriptions/s/resourceGroups/g/providers/Microsoft.ContainerRegistry/registries/r"
LOGIN_SERVER = "acr.example"
SURFACE_HOST = "surface-host.example"


def vault_reference(secret):
    return f"@Microsoft.KeyVault(SecretUri=https://vault.example/secrets/{secret}/)"


def good_state():
    return {
        "registry": {
            "id": SCOPE,
            "loginServer": LOGIN_SERVER,
            "adminUserEnabled": False,
            "anonymousPullEnabled": False,
        },
        # `az acr token list` answers with an empty list when no repository-scoped
        # token exists, which is the passing state.
        "tokens": [],
        "principals": {"surface": "p-surface", "relay": "p-relay", "deploy": "p-deploy"},
        "assignments": [
            {"scope": SCOPE, "principalId": "p-surface", "roleDefinitionName": "AcrPull"},
            {"scope": SCOPE, "principalId": "p-relay", "roleDefinitionName": "AcrPull"},
            {"scope": SCOPE, "principalId": "p-deploy", "roleDefinitionName": "AcrPush"},
        ],
        "settings": {
            "surface": {
                "WEBSITES_PORT": "8000",
                "MVP_RUNTIME_PASSWORD": vault_reference("mvp-runtime-password"),
                "EFR_MCP_ALLOWED_HOSTS": SURFACE_HOST,
            },
            "relay": {
                "WEBSITES_PORT": "8000",
                "ANTHROPIC_API_KEY": vault_reference("anthropic-api-key"),
                "EFR_RELAY_MCP_URL": f"https://{SURFACE_HOST}/mcp",
            },
        },
        "image": {
            "surface": {"linuxFxVersion": f"DOCKER|{LOGIN_SERVER}/evidence-first-rag:{COMMIT}", "acrUseManagedIdentityCreds": True},
            "relay": {"linuxFxVersion": f"DOCKER|{LOGIN_SERVER}/evidence-first-rag:{COMMIT}", "acrUseManagedIdentityCreds": True},
        },
    }


def stand_in(state):
    def az(*arguments):
        name = arguments[arguments.index("--name") + 1] if "--name" in arguments else None
        if arguments[:2] == ("acr", "show"):
            return state["registry"]
        if arguments[:3] == ("acr", "token", "list"):
            return state["tokens"]
        if arguments[:3] == ("acr", "credential", "show"):
            # The real `az` refuses while the admin user is disabled.
            if not state["registry"]["adminUserEnabled"]:
                raise RuntimeError("admin user is disabled for this registry")
            # The payload is never read by the case, only its existence.
            return {"username": "example-user", "passwords": [{"name": "example", "value": "example-value"}]}
        if arguments[:3] == ("webapp", "identity", "show"):
            return {"principalId": state["principals"][name]}
        if arguments[:2] == ("identity", "show"):
            return {"principalId": state["principals"]["deploy"]}
        if arguments[:3] == ("role", "assignment", "list"):
            return state["assignments"]
        if arguments[:4] == ("webapp", "config", "appsettings", "list"):
            return [{"name": setting, "value": value} for setting, value in state["settings"][name].items()]
        if arguments[:3] == ("webapp", "config", "show"):
            return state["image"][name]
        raise AssertionError(arguments)

    return az


def results(state):
    return checks.run(stand_in(state), "g", "r", "surface", "relay", "id-deploy", COMMIT)


class TheGoodState(unittest.TestCase):
    def test_every_case_passes(self):
        self.assertTrue(all(result["passed"] for result in results(good_state()).values()), results(good_state()))

    def test_no_detail_carries_a_value_or_a_principal(self):
        text = repr(results(good_state()))
        leaks = ["p-surface", "p-relay", "p-deploy", LOGIN_SERVER, SURFACE_HOST, "vault.example"]
        for app in good_state()["settings"].values():
            leaks.extend(app.values())
        for leaked in leaks:
            self.assertNotIn(leaked, text)

    def test_a_registry_shaped_name_holding_a_key_vault_reference_passes(self):
        state = good_state()
        state["settings"]["surface"]["EFR_ACR_NOTE"] = vault_reference("some-secret")
        self.assertTrue(results(state)["DP-014 settings"]["passed"], results(state)["DP-014 settings"])


class EachDeviationFails(unittest.TestCase):
    def failing(self, change, case):
        state = copy.deepcopy(good_state())
        change(state)
        outcome = results(state)
        self.assertFalse(outcome[case]["passed"], outcome[case])
        others = [name for name, result in outcome.items() if name != case and not result["passed"]]
        return others

    def test_admin_user_enabled(self):
        self.failing(lambda s: s["registry"].update(adminUserEnabled=True), "DP-014 registry")

    def test_anonymous_pull_enabled(self):
        self.failing(lambda s: s["registry"].update(anonymousPullEnabled=True), "DP-014 registry")

    def test_a_repository_scoped_token(self):
        self.failing(lambda s: s["tokens"].append({"name": "push-token"}), "DP-014 credential")

    def test_a_readable_admin_credential(self):
        # The admin user enabled is what makes `az acr credential show` answer.
        others = self.failing(lambda s: s["registry"].update(adminUserEnabled=True), "DP-014 credential")
        self.assertIn("DP-014 registry", others)

    def test_an_app_given_push(self):
        self.failing(lambda s: s["assignments"][0].update(roleDefinitionName="AcrPush"), "DP-014 roles")

    def test_an_extra_principal(self):
        self.failing(lambda s: s["assignments"].append({"scope": SCOPE, "principalId": "someone", "roleDefinitionName": "AcrPull"}), "DP-014 roles")

    def test_a_missing_pull(self):
        self.failing(lambda s: s["assignments"].pop(1), "DP-014 roles")

    def test_a_registry_password_setting(self):
        self.failing(lambda s: s["settings"]["relay"].update(DOCKER_REGISTRY_SERVER_PASSWORD="written"), "DP-014 settings")

    def test_a_setting_carrying_the_registry_under_another_name(self):
        self.failing(lambda s: s["settings"]["relay"].update(EFR_PULL_FROM=f"{LOGIN_SERVER}/evidence-first-rag"), "DP-014 settings")

    def test_a_registry_shaped_name_holding_its_own_value(self):
        self.failing(lambda s: s["settings"]["surface"].update(EFR_ACR_TOKEN="written"), "DP-014 settings")

    def test_an_unreadable_login_server(self):
        # One of the three setting clauses cannot be decided without it.
        self.failing(lambda s: s["registry"].pop("loginServer"), "DP-014 settings")

    def test_a_latest_tag(self):
        self.failing(lambda s: s["image"]["surface"].update(linuxFxVersion=f"DOCKER|{LOGIN_SERVER}/evidence-first-rag:latest"), "DP-014 surface image")

    def test_another_commit(self):
        self.failing(lambda s: s["image"]["relay"].update(linuxFxVersion=f"DOCKER|{LOGIN_SERVER}/evidence-first-rag:" + "b" * 40), "DP-014 relay image")

    def test_the_image_pulled_with_a_stored_credential(self):
        self.failing(lambda s: s["image"]["surface"].update(acrUseManagedIdentityCreds=False), "DP-014 surface image")

    def test_surface_holding_the_anthropic_key(self):
        self.failing(lambda s: s["settings"]["surface"].update(ANTHROPIC_API_KEY=vault_reference("anthropic-api-key")), "DP-003 settings")

    def test_relay_holding_a_database_credential(self):
        self.failing(lambda s: s["settings"]["relay"].update(MVP_RUNTIME_PASSWORD=vault_reference("mvp-runtime-password")), "DP-003 settings")


class AFaultInOneCase(unittest.TestCase):
    def test_fails_only_that_case(self):
        state = good_state()
        real = stand_in(state)

        def az(*arguments):
            if arguments[:3] == ("role", "assignment", "list"):
                raise RuntimeError("throttled")
            return real(*arguments)

        outcome = checks.run(az, "g", "r", "surface", "relay", "id-deploy", COMMIT)
        self.assertFalse(outcome["DP-014 roles"]["passed"])
        self.assertTrue(outcome["DP-014 registry"]["passed"])


class TheTokenReadFailing(unittest.TestCase):
    def test_fails_closed(self):
        """A registry whose token list cannot be read is not recorded as clean."""
        real = stand_in(good_state())

        def az(*arguments):
            if arguments[:3] == ("acr", "token", "list"):
                raise RuntimeError("throttled")
            return real(*arguments)

        outcome = checks.run(az, "g", "r", "surface", "relay", "id-deploy", COMMIT)
        self.assertFalse(outcome["DP-014 credential"]["passed"])



class TheTier(unittest.TestCase):
    def test_a_tier_without_tokens_has_none(self):
        """Where the tier offers no tokens, none can exist (#241 N7)."""
        real = stand_in(good_state())

        def az(*arguments):
            if arguments[:3] == ("acr", "token", "list"):
                raise checks.AzError("az acr token failed", "The operation is not supported for the registry SKU Basic.")
            return real(*arguments)

        outcome = checks.run(az, "g", "r", "surface", "relay", "id-deploy", COMMIT)
        self.assertTrue(outcome["DP-014 credential"]["passed"], outcome["DP-014 credential"])

    def test_any_other_az_failure_still_fails(self):
        real = stand_in(good_state())

        def az(*arguments):
            if arguments[:3] == ("acr", "token", "list"):
                raise checks.AzError("az acr token failed", "Too many requests")
            return real(*arguments)

        outcome = checks.run(az, "g", "r", "surface", "relay", "id-deploy", COMMIT)
        self.assertFalse(outcome["DP-014 credential"]["passed"])


class TheFailureDetail(unittest.TestCase):
    """Run 36662412772 recorded `DP-014 roles` as `AzError` alone. The detail
    now names the failed command and Azure's error code, never the message."""

    def test_a_failed_call_is_named_with_its_code_and_not_its_message(self):
        real = stand_in(good_state())
        message = (
            "ERROR: (AuthorizationFailed) The client 'SAMPLE_CLIENT' does not have authorization"
            " to perform action over scope '/subscriptions/SAMPLE_SUBSCRIPTION'."
        )

        def az(*arguments):
            if arguments[:3] == ("role", "assignment", "list"):
                raise checks.AzError(f"az {checks._command(arguments)} failed", message)
            return real(*arguments)

        detail = checks.run(az, "g", "r", "surface", "relay", "id-deploy", COMMIT)["DP-014 roles"]
        self.assertFalse(detail["passed"])
        self.assertIn("az role assignment list failed", detail["detail"])
        self.assertIn("(AuthorizationFailed)", detail["detail"])
        self.assertNotIn("SAMPLE_", detail["detail"])

    def test_the_command_stops_at_its_first_option(self):
        self.assertEqual(checks._command(("identity", "show", "--resource-group", "SAMPLE_GROUP")), "identity show")

    def test_output_without_a_code_says_so(self):
        self.assertEqual(checks.error_code("SAMPLE plain failure"), "no error code in the output")


class TheRoleScopes(unittest.TestCase):
    def test_a_scope_differing_only_in_case_is_the_same_scope(self):
        """ARM identifiers compare without case (#241 N5)."""
        state = copy.deepcopy(good_state())
        for entry in state["assignments"]:
            entry["scope"] = entry["scope"].replace("resourceGroups", "resourcegroups")
        self.assertTrue(results(state)["DP-014 roles"]["passed"], results(state)["DP-014 roles"])

    def test_an_inherited_push_capable_role_on_an_app_fails(self):
        """Contributor on the group lets an app push (#241 N6)."""
        state = copy.deepcopy(good_state())
        state["assignments"].append({"scope": "/subscriptions/s/resourceGroups/g", "principalId": "p-surface", "roleDefinitionName": "Contributor"})
        outcome = results(state)["DP-014 roles"]
        self.assertFalse(outcome["passed"])
        self.assertNotIn("p-surface", outcome["detail"])

    def test_inherited_assignments_are_read(self):
        calls = []
        real = stand_in(good_state())

        def az(*arguments):
            calls.append(arguments)
            return real(*arguments)

        checks.run(az, "g", "r", "surface", "relay", "id-deploy", COMMIT)
        listing = [call for call in calls if call[:3] == ("role", "assignment", "list")]
        self.assertTrue(listing and all("--include-inherited" in call for call in listing))


if __name__ == "__main__":
    unittest.main()
