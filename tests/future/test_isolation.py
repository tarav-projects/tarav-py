"""The experimental engine is opt-in and cannot initialize the normal runtime."""

import subprocess
import sys


def test_normal_runtime_and_future_namespace_do_not_import_rdf_engine():
    result = subprocess.run([sys.executable, "-c", """
import sys
from tarav.l3.runtime import create_runtime
runtime = create_runtime()
assert not any(name.startswith('tarav.l1._future') for name in sys.modules)
assert 'rdflib' not in sys.modules
from tarav.l1._future import future
from tarav.l1._future.conversations import UserTurn
assert future(UserTurn).obj is UserTurn
assert 'rdflib' not in sys.modules
assert not any(name.startswith('Tarav.Future.') for name in runtime.records._types)
print('normal runtime isolated; namespace does not import RDFLib')
"""], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "normal runtime isolated; namespace does not import RDFLib"
