"""Process-wide environment for the backend suite.

`arm_backend.config` builds its `Settings` singleton at import, and the two
required variables must exist before the first test module imports the
package. pytest loads this conftest before it imports any module under this
directory, whichever way the suite is invoked (the testpaths-driven root run,
a single file, any subset or order), so the values are defined here once and
nowhere else. Test modules hard-code "tok-service" in their service-token
headers, so the assignment is unconditional: a value exported by the
developer's shell must not reach the singleton either.
"""

import os

os.environ["DATABASE_URL"] = "postgresql://x:x@localhost/x"
os.environ["ARM_SERVICE_TOKEN"] = "tok-service"
