from . import cleanup_router, index_router, logs_router, recycle_router, scan_router


ROUTERS = (
    index_router.router,
    scan_router.router,
    cleanup_router.router,
    recycle_router.router,
    logs_router.router,
)
