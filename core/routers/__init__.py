from . import app_scan_router, cleanup_router, duplicates_router, index_router, logs_router, recycle_router, registry_router, scan_router, tools_router, user_directory_router


ROUTERS = (
    index_router.router,
    scan_router.router,
    duplicates_router.router,
    cleanup_router.router,
    recycle_router.router,
    logs_router.router,
    tools_router.router,
    registry_router.router,
    user_directory_router.router,
    app_scan_router.router,
)
