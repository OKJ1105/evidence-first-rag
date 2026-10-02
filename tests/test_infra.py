"""`deploy-v0.1` Sections 4.1, 4.3, 4.5 and 4.6, read off `infra/main.bicep`.

The provisioning definitions are text this repository commits, so the
obligations that text alone decides are asserted here, in every job, with no
Azure and no Bicep compiler: CI has neither. What only the deployed resources
can show -- that the platform honours these settings -- is `DP-003` and
`DP-014`'s, on the first deploy.

Each assertion reads one resource's block, found by its symbolic name, so a
setting that moved to the wrong resource fails rather than passes.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BICEP = (ROOT / "infra" / "main.bicep").read_text(encoding="utf-8")

ROLE_ACR_PULL = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
ROLE_ACR_PUSH = "8311e382-0749-4cb8-b61a-304f252e45ec"
ROLE_KV_SECRETS_USER = "4633458b-17de-408a-b874-0445c86b69e6"


def code(source: str) -> str:
    """The source with `//` comments removed, so prose cannot satisfy a check.

    A comment's `//` opens a line or follows whitespace. The `//` of a URL in a
    setting's value follows `:`, so the value survives and is asserted on.
    """
    return "\n".join(re.split(r"(?:^|(?<=\s))//", line, maxsplit=1)[0] for line in source.splitlines())


CODE = code(BICEP)


def block(symbol: str) -> str:
    """The text of `resource <symbol> ... = { ... }` or `var <symbol> = ...`,
    up to its closing brace or bracket at column 0."""
    match = re.search(rf"^(resource|var) {symbol}\b.*?^[}}\)\]]\s*$", CODE, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"no top-level `{symbol}` in infra/main.bicep")
    return match.group(0)


def setting_names(symbol: str) -> set:
    """The keys of a settings object, which the app settings resource takes as
    a map of name to value."""
    return set(re.findall(r"\b([A-Z][A-Z_]+): ", block(symbol)))


class TheTopology(unittest.TestCase):
    """Section 4.1."""

    def test_the_registry_is_basic_with_no_admin_user_and_no_anonymous_pull(self):
        registry = block("registry")
        self.assertIn("name: 'Basic'", registry)
        self.assertIn("adminUserEnabled: false", registry)
        self.assertIn("anonymousPullEnabled: false", registry)

    def test_the_server_is_postgresql_17_burstable_without_high_availability(self):
        server = block("server")
        self.assertIn("version: '17'", server)
        self.assertIn("tier: 'Burstable'", server)
        self.assertIn("mode: 'Disabled'", server)
        self.assertIn("geoRedundantBackup: 'Disabled'", server)

    def test_one_plan_and_exactly_two_apps(self):
        self.assertEqual(len(re.findall(r"^resource \w+ 'Microsoft.Web/serverfarms@", CODE, re.M)), 1)
        self.assertEqual(len(re.findall(r"^resource \w+ 'Microsoft.Web/sites@", CODE, re.M)), 2)

    def test_no_other_compute(self):
        for kind in ("Microsoft.App/", "Microsoft.Compute/", "Microsoft.ContainerInstance/"):
            with self.subTest(kind=kind):
                self.assertNotIn(kind, CODE)
        self.assertNotIn("functionapp", CODE.lower())

    def test_the_key_vault_and_the_deploy_identity_are_referenced_not_created(self):
        self.assertRegex(block("vault"), r"\bexisting\b")
        self.assertRegex(block("deployIdentity"), r"\bexisting\b")

    def test_both_apps_run_the_one_image_by_its_commit_tag(self):
        self.assertIn("var image = '${registry.properties.loginServer}/evidence-first-rag:${commit}'", CODE)
        self.assertIn("linuxFxVersion: 'DOCKER|${image}'", block("commonSiteConfig"))
        self.assertNotIn(":latest", CODE)

    def test_each_app_runs_its_own_entry_point(self):
        self.assertIn("evidence_first_rag.api.serve:build", block("surface"))
        self.assertIn("evidence_first_rag.relay.serve:build", block("relay"))

    def test_neither_app_writes_uvicorns_access_line(self):
        """#273: the access line carries the full request target, query string
        included; each app writes its own `deploy-v0.1` Section 4.7 record."""
        for name in ("surface", "relay"):
            with self.subTest(app=name):
                self.assertIn("--no-access-log", block(name))


class TheIdentitiesAndSecrets(unittest.TestCase):
    """Section 4.3."""

    def test_the_apps_pull_under_their_own_identity(self):
        self.assertIn("acrUseManagedIdentityCreds: true", block("commonSiteConfig"))
        for app in ("surface", "relay"):
            with self.subTest(app=app):
                self.assertIn("type: 'SystemAssigned'", block(app))

    def test_the_apps_hold_acr_pull_and_the_deploy_identity_acr_push(self):
        self.assertIn(f"var roleAcrPull = '{ROLE_ACR_PULL}'", CODE)
        self.assertIn(f"var roleAcrPush = '{ROLE_ACR_PUSH}'", CODE)
        for name, principal, role in (
            ("surfacePull", "surface.identity.principalId", "roleAcrPull"),
            ("relayPull", "relay.identity.principalId", "roleAcrPull"),
            ("deployPush", "deployIdentity.properties.principalId", "roleAcrPush"),
        ):
            with self.subTest(assignment=name):
                assignment = block(name)
                self.assertIn("scope: registry", assignment)
                self.assertIn(principal, assignment)
                self.assertIn(f"'Microsoft.Authorization/roleDefinitions', {role})", assignment)

    def test_no_app_is_given_push_or_a_broad_role(self):
        """Push is the deploy identity's alone, and no assignment here hands
        out Contributor, Owner or a data-writer role."""
        pushes = re.findall(r"roleDefinitions', roleAcrPush\)", CODE)
        self.assertEqual(len(pushes), 1)
        assignments = re.findall(r"^resource \w+ 'Microsoft.Authorization/roleAssignments@", CODE, re.M)
        self.assertEqual(len(assignments), 5)
        for guid in (
            "b24988ac-6180-42a0-ab88-20f7382dd24c",  # Contributor
            "8e3af657-a8ff-443c-a75c-2fe8c4bcb635",  # Owner
        ):
            self.assertNotIn(guid, CODE)

    def test_each_app_reads_only_its_own_secret(self):
        """Scoped to one secret, not the vault: the vault enforces
        `relay-v0.1` Section 4.8, not a convention."""
        self.assertIn(f"var roleKeyVaultSecretsUser = '{ROLE_KV_SECRETS_USER}'", CODE)
        surface_secret, relay_secret = block("surfaceSecret"), block("relaySecret")
        self.assertIn("scope: runtimePassword", surface_secret)
        self.assertIn("surface.identity.principalId", surface_secret)
        self.assertIn("scope: anthropicKey", relay_secret)
        self.assertIn("relay.identity.principalId", relay_secret)
        self.assertNotRegex(CODE, r"scope: vault\b")

    def test_no_secret_is_a_literal(self):
        self.assertRegex(CODE, r"@secure\(\)\s*\n@description\([^)]*\)\s*\nparam adminSecret string\n")
        self.assertNotRegex(CODE, r"param adminSecret string =")
        self.assertNotRegex(CODE, r"(?i)(password|key)'?\s*[:=]\s*'[^'$@{]")


class TheNetworking(unittest.TestCase):
    """Section 4.5."""

    def test_both_apps_are_https_only_and_the_database_admits_azure_services(self):
        for app in ("surface", "relay"):
            with self.subTest(app=app):
                self.assertIn("httpsOnly: true", block(app))
        rule = block("allowAzureServices")
        self.assertIn("startIpAddress: '0.0.0.0'", rule)
        self.assertIn("endIpAddress: '0.0.0.0'", rule)
        self.assertIn("minTlsVersion: '1.2'", block("commonSiteConfig"))


class TheConfiguration(unittest.TestCase):
    """Section 4.6: every key a deployed process reads, and nothing else.

    `WEBSITES_PORT` is read by the platform, not by the process.
    """

    def test_surface_reads_its_column(self):
        self.assertEqual(
            setting_names("surfaceSettings"),
            {
                "WEBSITES_PORT",
                "PGHOST",
                "PGPORT",
                "MVP_DATABASE",
                "PGSSLMODE",
                "MVP_RUNTIME_PASSWORD",
                "EFR_MCP_ALLOWED_HOSTS",
                "EFR_CORS_ORIGIN",
            },
        )
        self.assertIn("PGSSLMODE: 'require'", block("surfaceSettings"))

    def test_relay_reads_its_column(self):
        self.assertEqual(
            setting_names("relaySettings"),
            {
                "WEBSITES_PORT",
                "ANTHROPIC_API_KEY",
                "EFR_RELAY_MCP_URL",
                "EFR_RELAY_DAILY_CEILING",
                "EFR_CORS_ORIGIN",
            },
        )

    def test_neither_app_is_given_the_others_secret(self):
        self.assertNotIn("ANTHROPIC", block("surfaceSettings"))
        for name in ("MVP_RUNTIME_PASSWORD", "PGHOST", "PGPASSWORD"):
            self.assertNotIn(name, block("relaySettings"))

    def test_secrets_are_key_vault_references(self):
        """Each app's secret arrives as a Key Vault reference to that app's own
        entry, never as a literal. The reference is built in a variable and the
        setting interpolates it, so the value beside a name like
        `MVP_RUNTIME_PASSWORD` names the variable instead of carrying a value --
        which is also what `scripts/checks/scan_sensitive_strings.py` requires
        of a value in that position."""
        self.assertIn(
            "var surfaceVaultReference = "
            "'@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=${surfaceVaultEntry})'",
            CODE,
        )
        self.assertIn(
            "var relayVaultReference = "
            "'@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=${relayVaultEntry})'",
            CODE,
        )
        self.assertIn(
            "MVP_RUNTIME_PASSWORD: '${surfaceVaultReference}'", block("surfaceSettings")
        )
        self.assertIn(
            "ANTHROPIC_API_KEY: '${relayVaultReference}'", block("relaySettings")
        )

    def test_the_cors_origin_and_the_ceiling_are_absent_while_empty(self):
        """An unset origin allows no cross-origin call, and an unset ceiling
        refuses every request: neither is ever defaulted to a value."""
        self.assertIn("param corsOrigin string = ''", CODE)
        self.assertIn("param relayDailyCeiling string = ''", CODE)
        self.assertIn("empty(corsOrigin) ? {} :", block("surfaceSettings"))
        self.assertIn("empty(relayDailyCeiling) ? {} :", block("relaySettings"))
        self.assertNotIn("'*'", CODE)

    def test_the_host_name_is_read_from_the_app_and_never_constructed(self):
        """The platform assigns each app its default host name, and a name this
        file builds from the app's name can address a host that does not
        resolve. `/mcp` matches the request's `Host` header against
        `EFR_MCP_ALLOWED_HOSTS` exactly, so a wrong host refuses every call
        (`DP-010`, `DP-012`), and the relay's URL and the two outputs would
        address that host too. Every one of them reads `defaultHostName`.
        """
        self.assertNotIn("azurewebsites.net", BICEP)
        self.assertIn(
            "EFR_MCP_ALLOWED_HOSTS: surface.properties.defaultHostName",
            block("surfaceSettings"),
        )
        self.assertIn(
            "EFR_RELAY_MCP_URL: 'https://${surface.properties.defaultHostName}/mcp'",
            block("relaySettings"),
        )
        self.assertIn("output surfaceHost string = surface.properties.defaultHostName", CODE)
        self.assertIn("output relayHost string = relay.properties.defaultHostName", CODE)

    def test_each_apps_settings_are_a_child_resource_declared_once(self):
        """A site's own `siteConfig` cannot read the host name the platform
        assigned that site, so the settings are a child `appsettings` resource,
        which can read its parent's. `siteConfig` carries none, so the two
        cannot fight over them."""
        self.assertNotIn("appSettings", CODE)
        for resource, settings in (
            ("surfaceAppSettings", "surfaceSettings"),
            ("relayAppSettings", "relaySettings"),
        ):
            with self.subTest(resource=resource):
                child = block(resource)
                self.assertIn("name: 'appsettings'", child)
                self.assertIn(f"properties: {settings}", child)

    def test_settings_are_written_after_the_secret_grant(self):
        """A Key Vault reference written before the app may read the secret
        does not resolve, and the process receives the reference string."""
        for resource, grant in (
            ("surfaceAppSettings", "surfaceSecret"),
            ("relayAppSettings", "relaySecret"),
        ):
            with self.subTest(resource=resource):
                self.assertIn(f"dependsOn: [{grant}]", block(resource))


class TheLogs(unittest.TestCase):
    """Section 4.7: the platform's log store."""

    def test_each_sites_config_writes_run_one_after_the_other(self):
        """App Service refuses a second config write to a site while one is in
        flight, so the logs wait for the settings (#231 N2)."""
        for logs, settings in (("surfaceLogs", "surfaceAppSettings"), ("relayLogs", "relayAppSettings")):
            with self.subTest(logs=logs):
                self.assertIn(f"dependsOn: [{settings}]", block(logs))

    def test_neither_app_enables_the_platforms_http_log(self):
        """#279: that log records each request line, query string included, and
        Section 4.7 binds a request's URL and query string as well as its body.
        Off explicitly, not by the platform's default, because an earlier deploy
        of this template turned it on. With it off, no log here sets
        `retentionInDays`: Section 4.7's 7 days is the platform's own retention
        of the standard-output stream, its default, which the first deploy
        settles (#231 N1)."""
        for logs in ("surfaceLogs", "relayLogs"):
            with self.subTest(logs=logs):
                http = re.search(r"httpLogs: \{.*?\n    \}", block(logs), re.DOTALL)
                self.assertIsNotNone(http, "no `httpLogs` block, so the log is left at a default")
                self.assertIn("enabled: false", http.group(0))
                self.assertNotIn("enabled: true", http.group(0))
                self.assertNotIn("retentionInDays", block(logs))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
