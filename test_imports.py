import warnings
warnings.filterwarnings('ignore')

import traceback
import sys

print("Testing imports...")

try:
    print("1. Testing connection...")
    from aegis.database.connection import Base
    print("   Connection OK")
except Exception as e:
    print(f"   Connection FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    print("2. Testing models...")
    from aegis.database.models import BehavioralSession
    print("   Models OK")
except Exception as e:
    print(f"   Models FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    print("3. Testing repositories...")
    from aegis.database.repositories import BehavioralSessionRepository
    print("   Repositories OK")
except Exception as e:
    print(f"   Repositories FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    print("4. Testing intelligence routes...")
    from aegis.api.routes.intelligence import router
    print("   Intelligence routes OK")
except Exception as e:
    print(f"   Intelligence routes FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\nAll imports OK!")
