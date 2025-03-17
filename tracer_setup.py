from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

def setup_tracing():
    # Настройка провайдера трассировки
    trace.set_tracer_provider(TracerProvider())

    # Экспорт данных в консоль
    span_processor = SimpleSpanProcessor(ConsoleSpanExporter())
    trace.get_tracer_provider().add_span_processor(span_processor)

    # Инструментация логирования
    LoggingInstrumentor().instrument(set_logging_format=True)
