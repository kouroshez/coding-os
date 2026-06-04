"""Laravel contract extraction tests (TASK-069 P1)."""

from __future__ import annotations

from graph_os.extractors import contracts


def _routes(src, path="routes/web.php"):
    r = contracts.extract(path, src)
    return [n for n in r.nodes if n.kind == "cos:route"]


def _labels(src, path="routes/web.php"):
    return {n.label for n in _routes(src, path)}


class TestLaravelRoutes:
    def test_basic_get_post(self):
        src = (
            "<?php\nuse Illuminate\\Support\\Facades\\Route;\n"
            "Route::get('/users', [UserController::class, 'index']);\n"
            "Route::post('/users', [UserController::class, 'store']);\n"
        )
        labels = _labels(src)
        assert "GET /users" in labels
        assert "POST /users" in labels

    def test_handler_array_form_edge(self):
        src = "<?php\nRoute::get('/u', [App\\Http\\UserController::class, 'index']);\n"
        r = contracts.extract("routes/web.php", src)
        assert any(
            n.metadata.get("handler") == "UserController@index"
            for n in r.nodes
            if n.kind == "cos:route"
        )
        # Cross-file controller handler → resolvable phproute stub (link_php_handlers
        # binds it to the real method during reindex).
        assert any(
            e.edge_type == "calls"
            and e.target_uid == "code:external:phproute:UserController.index"
            for e in r.edges
        )

    def test_handler_string_form(self):
        src = "<?php\nRoute::get('/u', 'UserController@show');\n"
        r = contracts.extract("routes/web.php", src)
        assert any(
            n.metadata.get("handler") == "UserController@show"
            for n in r.nodes
            if n.kind == "cos:route"
        )

    def test_invokable_controller(self):
        src = "<?php\nRoute::get('/dash', DashboardController::class);\n"
        r = contracts.extract("routes/web.php", src)
        assert any(
            n.metadata.get("handler") == "DashboardController@__invoke"
            for n in r.nodes
            if n.kind == "cos:route"
        )

    def test_middleware_only_group_no_prefix(self):
        # A group with middleware but no prefix leaves the inner path as-is.
        src = (
            "<?php\nRoute::middleware('auth')->group(function () {\n"
            "    Route::get('/profile', [ProfileController::class, 'show']);\n"
            "});\n"
        )
        assert "GET /profile" in _labels(src)


class TestLaravelGroupPrefix:
    def test_fluent_prefix_group(self):
        src = (
            "<?php\nRoute::prefix('api')->group(function () {\n"
            "    Route::get('/users', [UserController::class, 'index']);\n"
            "});\n"
        )
        assert "GET /api/users" in _labels(src, "routes/api.php")

    def test_array_prefix_group(self):
        src = (
            "<?php\nRoute::group(['prefix' => 'admin'], function () {\n"
            "    Route::get('/dash', [DashController::class, 'index']);\n"
            "});\n"
        )
        assert "GET /admin/dash" in _labels(src)

    def test_nested_group_prefix(self):
        src = (
            "<?php\nRoute::prefix('api')->group(function () {\n"
            "    Route::prefix('v1')->group(function () {\n"
            "        Route::get('/users', [UserController::class, 'index']);\n"
            "    });\n"
            "});\n"
        )
        assert "GET /api/v1/users" in _labels(src, "routes/api.php")

    def test_route_outside_group_not_prefixed(self):
        src = (
            "<?php\nRoute::get('/health', [HealthController::class, 'check']);\n"
            "Route::prefix('api')->group(function () {\n"
            "    Route::get('/users', [UserController::class, 'index']);\n"
            "});\n"
        )
        labels = _labels(src, "routes/api.php")
        assert "GET /health" in labels  # not /api/health
        assert "GET /api/users" in labels

    def test_resource_in_group_prefixed(self):
        src = (
            "<?php\nRoute::prefix('api')->group(function () {\n"
            "    Route::apiResource('posts', PostController::class);\n"
            "});\n"
        )
        assert "GET /api/posts" in _labels(src, "routes/api.php")


class TestLaravelResource:
    def test_api_resource_five_routes(self):
        src = "<?php\nRoute::apiResource('posts', PostController::class);\n"
        r = contracts.extract("routes/api.php", src)
        routes = [n for n in r.nodes if n.metadata.get("derivation") == "laravel_apiResource"]
        assert len(routes) == 5
        labels = {n.label for n in routes}
        assert "GET /posts" in labels
        assert "GET /posts/{id}" in labels
        assert "DELETE /posts/{id}" in labels
        assert "GET /posts/create" not in labels  # api has no create/edit

    def test_resource_seven_routes(self):
        src = "<?php\nRoute::resource('photos', PhotoController::class);\n"
        routes = [
            n
            for n in contracts.extract("routes/web.php", src).nodes
            if n.metadata.get("derivation") == "laravel_resource"
        ]
        assert len(routes) == 7
        assert "GET /photos/create" in {n.label for n in routes}


class TestArtisan:
    def test_command_signature(self):
        src = (
            "<?php\nclass SendEmails extends Command {\n"
            "    protected $signature = 'mail:send {user}';\n}\n"
        )
        r = contracts.extract("app/Console/Commands/SendEmails.php", src)
        assert any(
            n.metadata.get("kind") == "cli" and n.metadata.get("path") == "mail:send"
            for n in r.nodes
        )


class TestNegative:
    def test_plain_php_no_routes(self):
        src = "<?php\nclass Foo { public function bar() { return 1; } }\n"
        assert _routes(src, "app/Foo.php") == []
