import os
import logging


logger = logging.getLogger(__name__)


def init_tracing(app, service_name: str):
    enabled = os.environ.get("OTEL_ENABLED", "").strip() in {"1", "true", "TRUE", "yes", "YES"}
    enabled = enabled or bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))
    if not enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    except Exception as e:
        logger.warning(f"Tracing disabled: {e}")
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    try:
        HTTPXClientInstrumentor().instrument()
    except Exception:
        pass
