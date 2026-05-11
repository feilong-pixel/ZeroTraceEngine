from app import PAGE_FILES, app


FEATURE_PAGE_PATHS = {
    "/scan",
    "/duplicates",
    "/registry",
    "/cleanup",
    "/recycle",
    "/logs",
    "/tools",
    "/user-directory",
    "/app-scan",
}


def _methods_for(path: str) -> set[str]:
    methods: set[str] = set()
    for route in app.routes:
        if getattr(route, "path", None) == path:
            methods.update(getattr(route, "methods", set()) or set())
    return methods


def test_feature_pages_are_registered_for_no_cache():
    assert FEATURE_PAGE_PATHS <= set(PAGE_FILES)


def test_clear_result_mutations_have_post_routes():
    assert "POST" in _methods_for("/scan/clearResults")
    assert "POST" in _methods_for("/duplicates/results/clear")
    assert "POST" in _methods_for("/registry/results/clear")
    assert "POST" in _methods_for("/app-scan/results/clear")
    assert "POST" in _methods_for("/user-directory/results/clear")


def test_legacy_delete_clear_routes_are_compatibility_only():
    assert "DELETE" in _methods_for("/registry/results")
    assert "DELETE" in _methods_for("/app-scan/results")
    assert "DELETE" in _methods_for("/user-directory/results")
