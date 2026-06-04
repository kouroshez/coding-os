"""WordPress contract extraction tests (TASK-069 P2)."""

from __future__ import annotations

from graph_os.extractors import contracts


def _nodes(src, path="wp-content/plugins/x/plugin.php"):
    return contracts.extract(path, src).nodes


def _by_framework(src, fw, path="wp-content/plugins/x/plugin.php"):
    return [
        n
        for n in _nodes(src, path)
        if n.kind in ("cos:route",) and n.metadata.get("framework") == fw
    ]


class TestHooks:
    def test_add_action_event(self):
        src = "<?php\nadd_action('init', 'my_init');\n"
        n = _by_framework(src, "wp_action")
        assert n and n[0].metadata.get("path") == "init"
        assert n[0].metadata.get("handler") == "my_init"

    def test_add_filter_event(self):
        src = "<?php\nadd_filter('the_content', 'my_filter');\n"
        assert any(n.metadata.get("path") == "the_content" for n in _by_framework(src, "wp_filter"))

    def test_do_action_fire_site(self):
        src = "<?php\ndo_action('my_custom_hook', $arg);\n"
        fired = [n for n in _nodes(src) if n.metadata.get("derivation") == "wp_fire"]
        assert any(n.metadata.get("path") == "my_custom_hook" for n in fired)


class TestAjax:
    def test_wp_ajax_route(self):
        src = "<?php\nadd_action('wp_ajax_save_data', 'save_data_cb');\n"
        n = _by_framework(src, "wp_ajax")
        assert n and "action=save_data" in n[0].metadata.get("path", "")

    def test_wp_ajax_nopriv_strips_prefix(self):
        src = "<?php\nadd_action('wp_ajax_nopriv_load', 'load_cb');\n"
        n = _by_framework(src, "wp_ajax")
        assert n and n[0].metadata.get("path", "").endswith("action=load")


class TestShortcodeCptRest:
    def test_shortcode(self):
        src = "<?php\nadd_shortcode('my_button', 'render_button');\n"
        assert any(
            n.metadata.get("path") == "my_button" for n in _by_framework(src, "wp_shortcode")
        )

    def test_register_post_type(self):
        src = "<?php\nregister_post_type('product', array('public' => true));\n"
        assert any(n.metadata.get("path") == "product" for n in _by_framework(src, "wp_cpt"))

    def test_rest_route(self):
        src = (
            "<?php\nregister_rest_route('myplugin/v1', '/items', array(\n"
            "  'methods' => 'GET',\n  'callback' => 'get_items',\n));\n"
        )
        n = _by_framework(src, "wp_rest")
        assert n and n[0].metadata.get("path") == "/wp-json/myplugin/v1/items"
        assert n[0].metadata.get("method") == "get"


class TestNegative:
    def test_non_wp_php_no_nodes(self):
        src = "<?php\nclass Foo { public function bar() {} }\n"
        assert _by_framework(src, "wp_action", path="app/Foo.php") == []
