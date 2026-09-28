"""`deploy-v0.1` `DP-014` and the settings half of `DP-003`, against a stand-in `az`."""

import copy
import unittest

from evidence_first_rag.deploy import azure_checks as checks

COMMIT = "a" * 40
SCOPE = "/subscriptions/s/resourceGroups/g/providers/Microsoft.ContainerRegistry/registries/r"


def good_state():
    return {
        "registry": {"id": SCOPE, "adminUserEnabled": False, "anonymousPullEnabled": False},
        "principals": {"surface": "p-surface", "relay": "p-relay", "deploy": "p-deploy"},
        "assignments": [
            {"scope": SCOPE, "principalId": "p-surface", "roleDefinitionName": "AcrPull"},
            {"scope": SCOPE, "principalId": "p-relay", "roleDefinitionName": "AcrPull"},
            {"scope": SCOPE, "principalId": "p-deploy", "roleDefinitionName": "AcrPush"},
        ],
        "settings": {
            "surface": ["WEBSITES_PORT", "MVP_RUNTIME_PASSWORD", "EFR_MCP_ALLOWED_HOSTS"],
            "relay": ["WEBSITES_PORT", "ANTHROPIC_API_KEY", "EFR_RELAY_MCP_URL"],
        },
        "image": {"surface": f"DOCKER|acr.example/evidence-first-rag:{COMMIT}", "relay": f"DOCKER|acr.example/evidence-first-rag:{COMMIT}"},
    }


def stand_in(state):
    def az(*arguments):
        name = arguments[arguments.index("--name") + 1] if "--name" in arguments else None
        if arguments[:2] == ("acr", "show"):
            return state["registry"]
        if arguments[:3] == ("webapp", "identity", "show"):
            return {"principalId": state["principals"][name]}
        if arguments[:2] == ("identity", "show"):
            return {"principalId": state["principals"]["deploy"]}
        if arguments[:3] == ("role", "assignment", "list"):
            return state["assignments"]
        if arguments[:4] == ("webapp", "config", "appsettings", "list"):
            return [{"name": setting, "value": "not read"} for setting in state["settings"][name]]
        if arguments[:3] == ("webapp", "config", "show"):
            return {"linuxFxVersion": state["image"][name]}
        raise AssertionError(arguments)

    return az


def results(state):
    return checks.run(stand_in(state), "g", "r", "surface", "relay", "id-deploy", COMMIT)


class TheGoodState(unittest.TestCase):
    def test_every_case_passes(self):
        self.assertTrue(all(result["passed"] for result in results(good_state()).values()), results(good_state()))

    def test_no_detail_carries_a_value_or_a_principal(self):
        text = repr(results(good_state()))
        for leaked in ("p-surface", "p-relay", "p-deploy", "not read", "acr.example"):
            self.assertNotIn(leaked, text)


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

    def test_an_app_given_push(self):
        self.failing(lambda s: s["assignments"][0].update(roleDefinitionName="AcrPush"), "DP-014 roles")

    def test_an_extra_principal(self):
        self.failing(lambda s: s["assignments"].append({"scope": SCOPE, "principalId": "someone", "roleDefinitionName": "AcrPull"}), "DP-014 roles")

    def test_a_missing_pull(self):
        self.failing(lambda s: s["assignments"].pop(1), "DP-014 roles")

    def test_a_registry_password_setting(self):
        self.failing(lambda s: s["settings"]["relay"].append("DOCKER_REGISTRY_SERVER_PASSWORD"), "DP-014 settings")

    def test_a_latest_tag(self):
        self.failing(lambda s: s["image"].update(surface="DOCKER|acr.example/evidence-first-rag:latest"), "DP-014 surface image")

    def test_another_commit(self):
        self.failing(lambda s: s["image"].update(relay="DOCKER|acr.example/evidence-first-rag:" + "b" * 40), "DP-014 relay image")

    def test_surface_holding_the_anthropic_key(self):
        self.failing(lambda s: s["settings"]["surface"].append("ANTHROPIC_API_KEY"), "DP-003 settings")

    def test_relay_holding_a_database_credential(self):
        self.failing(lambda s: s["settings"]["relay"].append("MVP_RUNTIME_PASSWORD"), "DP-003 settings")


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


if __name__ == "__main__":
    unittest.main()
