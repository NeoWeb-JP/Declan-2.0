"""Swap a module's imported collaborators for attributes of a test double."""
import types
from unittest.mock import patch


def patch_module_collaborators(testcase, module, double):
    """Replace every imported module global in `module` with `getattr(double, name)`."""
    for name, value in list(vars(module).items()):
        if isinstance(value, types.ModuleType):
            patcher = patch.object(module, name, getattr(double, name))
            patcher.start()
            testcase.addCleanup(patcher.stop)
