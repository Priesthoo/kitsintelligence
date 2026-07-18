from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
import structlog

from app.core.config import settings


request_id_ctx : ContextVar[str] = ContextVar("request_id", default="-")
user_id_ctx : ContextVar[str] = ContextVar("user_id", default="-")
org_id_ctx : ContextVar[str] = ContextVar("org_id", default="-")

def _inject_context(logger:logging.Logger, methdo_name: str, event_dict: dict)-> dict :
    event_dict["request_id"] = request_id_ctx.get()
    event_dict["user_id"] = user_id_ctx.get()
    event_dict["org_id"] = org_id_ctx.get()
    event_dict["service"] = settings.OTEL_SERVICE_NAME
    event_dict["environment"] = settings.ENVIRONMENT
    return event_dict

def configure_logging() -> None :
    logging.basicConfig(
        format="%(message)s",
        stream = sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL.upper(),logging.INFO),
    )
    
    shared_processors : list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _inject_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    if settings.LOG_JSON:
        renderer = structlog.processors.JSONRenderer()
    else :
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    structlog.configure(
        processors= shared_processors+ [renderer],
        wrapper_class= structlog.make_filtering_bound_logger(
            getattr(logging,settings.LOG_LEVEL.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory= structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
        
    )
    
    for noisy_logger in ("uvicorn.access", "httpx","aio_pika"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
        

def get_logger(name:str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
