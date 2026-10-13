import os
import sys
import asyncio

# Set a harmless test-only value for SECRET_KEY before any test imports the app/settings
os.environ.setdefault("SECRET_KEY", "test-only-secret-not-for-production")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def pytest_collection_modifyitems(items):
    """Sort Qt-dependent tests to run after async TestClient tests on Windows.

    Prevents Windows IOCP / AnyIO blocking portal access violations caused by
    PySide6 QApplication thread affinity and COM initialization in Python 3.13.
    """
    def is_qt_test(item):
        path_str = str(item.fspath).replace("\\", "/").lower()
        return "desktop" in path_str or "pipeline" in path_str

    items.sort(key=is_qt_test)
