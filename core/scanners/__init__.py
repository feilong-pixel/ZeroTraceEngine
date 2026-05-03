import pkgutil
import importlib

SCANNERS = []

for module in pkgutil.iter_modules(__path__):
    mod = importlib.import_module(f"{__name__}.{module.name}")
    if hasattr(mod, "Scanner"):
        SCANNERS.append(mod.Scanner())
