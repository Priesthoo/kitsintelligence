"""
Connector package. Importing this package registers every concrete
connector implementation with ConnectorRegistry via the @register_connector
decorator on each class.

Critical: any code path that needs the registry populated (the Hydration
Engine, the Data Sources admin API, Celery workers) MUST trigger this
import. Previously, only `app.connectors.base` was ever imported directly
by callers (`from app.connectors.base import ConnectorRegistry`), which
loads the base module but never executed weather.py's decorator -- meaning
ConnectorRegistry was silently empty at runtime and every data source
creation/hydration call would fail with "Unknown connector_key".

Because Python imports a package's __init__.py before resolving any
submodule access, this file being populated with imports of every
connector module means the fix applies automatically to every existing
`from app.connectors.base import ...` call site -- no other file needs to
change.
"""
from __future__ import annotations

from app.connectors import (  
    base,
    cyber_intelligence,
    financial_intelligence,
    maritime_intelligence,
    news_intelligence,
    osint,
    socmint,
    threat_intelligence,
    weather,
)
from app.connectors.base import ConnectorRegistry

__all__ = ["ConnectorRegistry"]