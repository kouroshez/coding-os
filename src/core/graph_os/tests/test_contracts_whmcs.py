"""WHMCS contract extraction tests (TASK-069 P3)."""

from __future__ import annotations

from graph_os.extractors import contracts


def _events(src, path):
    return [n for n in contracts.extract(path, src).nodes if n.kind == "cos:route"]


class TestAddHook:
    def test_add_hook_event(self):
        src = "<?php\nadd_hook('ClientAreaPage', 1, 'my_cb');\n"
        n = _events(src, "includes/hooks/mine.php")
        assert any(
            x.metadata.get("framework") == "whmcs_hook"
            and x.metadata.get("path") == "ClientAreaPage"
            for x in n
        )

    def test_add_hook_handler_resolves_same_file(self):
        # Bare same-file callback resolves to the real function node.
        src = "<?php\nadd_hook('ClientAreaPage', 1, 'my_cb');\nfunction my_cb($vars) {}\n"
        r = contracts.extract("includes/hooks/mine.php", src)
        assert any(
            e.edge_type == "calls"
            and e.target_uid == "code:function:includes/hooks/mine.php::my_cb"
            for e in r.edges
        )


class TestModuleFunctions:
    def test_provisioning_module(self):
        src = "<?php\nfunction mymod_ConfigOptions() {}\nfunction mymod_CreateAccount($params) {}\n"
        n = _events(src, "modules/servers/mymod/mymod.php")
        fws = {x.metadata.get("framework") for x in n}
        actions = {x.metadata.get("note") for x in n}
        assert "whmcs_provisioning" in fws
        assert {"ConfigOptions", "CreateAccount"} <= actions

    def test_registrar_module(self):
        src = "<?php\nfunction myreg_RegisterDomain($params) {}\n"
        n = _events(src, "modules/registrars/myreg/myreg.php")
        assert any(x.metadata.get("framework") == "whmcs_registrar" for x in n)

    def test_gateway_module(self):
        src = "<?php\nfunction paypal_link($params) {}\nfunction paypal_config() {}\n"
        n = _events(src, "modules/gateways/paypal.php")
        assert any(x.metadata.get("framework") == "whmcs_gateway" for x in n)

    def test_addon_module(self):
        src = "<?php\nfunction myaddon_activate() {}\nfunction myaddon_output($vars) {}\n"
        n = _events(src, "modules/addons/myaddon/myaddon.php")
        assert any(x.metadata.get("framework") == "whmcs_addon" for x in n)

    def test_prefix_must_match_stem(self):
        # A function whose prefix != file stem is NOT a module function.
        src = "<?php\nfunction other_Foo() {}\n"
        n = _events(src, "modules/servers/mymod/mymod.php")
        assert all(x.metadata.get("derivation") != "whmcs_module" for x in n)


class TestNegative:
    def test_non_whmcs_no_nodes(self):
        src = "<?php\nfunction app_helper() {}\n"
        assert _events(src, "app/helpers.php") == []
