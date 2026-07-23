"""OpenTelemetry tracing bootstrap: FastAPI, SQLAlchemy, and Redis auto-instrumentation."""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def configure_tracing(app) -> None:  # noqa: ANN001
    resource = Resource.create(
        {SERVICE_NAME: settings.OTEL_SERVICE_NAME, "environment": settings.ENVIRONMENT}
    )
    provider = TracerProvider(resource=resource)

    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    elif settings.DEBUG:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
    logger.info("tracing.configured", endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT or "console")


def get_tracer(name: str):  # noqa: ANN201
    return trace.get_tracer(name)