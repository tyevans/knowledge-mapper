/**
 * Frontend Observability for Knowledge Mapper
 *
 * Configures OpenTelemetry browser tracing with:
 * - Automatic fetch/XHR instrumentation
 * - Document load timing
 * - Trace context propagation to backend
 * - Export to Tempo via OTLP HTTP
 *
 * Environment Variables (via Vite):
 *   VITE_OTEL_SERVICE_NAME: Service name for traces (default: "frontend")
 *   VITE_OTEL_EXPORTER_OTLP_ENDPOINT: Tempo OTLP HTTP endpoint
 *
 * Usage:
 *   import { initObservability } from './observability'
 *   initObservability()
 */

import { WebTracerProvider } from '@opentelemetry/sdk-trace-web'
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-web'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { resourceFromAttributes } from '@opentelemetry/resources'
import { ATTR_SERVICE_NAME } from '@opentelemetry/semantic-conventions'
import { ZoneContextManager } from '@opentelemetry/context-zone'
import { registerInstrumentations } from '@opentelemetry/instrumentation'
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch'
import { DocumentLoadInstrumentation } from '@opentelemetry/instrumentation-document-load'
import { trace } from '@opentelemetry/api'

// =============================================================================
// Configuration
// =============================================================================

const SERVICE_NAME = import.meta.env.VITE_OTEL_SERVICE_NAME || 'frontend'

// OTLP HTTP endpoint for browser tracing
// Tempo exposes port 4318 for OTLP HTTP (browsers can't use gRPC)
const OTLP_ENDPOINT =
  import.meta.env.VITE_OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318'

// =============================================================================
// Trace Provider Setup
// =============================================================================

let initialized = false

/**
 * Initialize OpenTelemetry tracing for the browser.
 *
 * This sets up:
 * 1. A WebTracerProvider with service name resource
 * 2. OTLP HTTP exporter to send traces to Tempo
 * 3. Automatic fetch instrumentation with trace context propagation
 * 4. Document load instrumentation for page timing
 *
 * Call this once at application startup, before any other code runs.
 */
export function initObservability(): void {
  if (initialized) {
    console.warn('Observability already initialized')
    return
  }

  // Skip in test environments
  if (import.meta.env.MODE === 'test') {
    console.log('Skipping observability in test mode')
    return
  }

  try {
    // Create resource identifying this service
    const resource = resourceFromAttributes({
      [ATTR_SERVICE_NAME]: SERVICE_NAME,
    })

    // Configure OTLP HTTP exporter for Tempo
    const exporter = new OTLPTraceExporter({
      url: `${OTLP_ENDPOINT}/v1/traces`,
    })

    // Create the tracer provider with resource and span processors
    // SDK v2 uses spanProcessors in config instead of addSpanProcessor method
    const provider = new WebTracerProvider({
      resource,
      spanProcessors: [new BatchSpanProcessor(exporter)],
    })

    // Register the provider globally
    provider.register({
      // ZoneContextManager maintains trace context across async operations
      contextManager: new ZoneContextManager(),
    })

    // Register automatic instrumentations
    registerInstrumentations({
      instrumentations: [
        // Automatically trace all fetch requests
        new FetchInstrumentation({
          // Propagate trace context to these URLs (backend API)
          propagateTraceHeaderCorsUrls: [
            // Match the backend API URL
            /\/api\//,
            // Match localhost for development
            /localhost/,
            // Match any same-origin requests
            new RegExp(`^${window.location.origin}`),
          ],
          // Clear timing resources after collecting to avoid memory leaks
          clearTimingResources: true,
        }),
        // Trace document load timing (navigation, resources, etc.)
        new DocumentLoadInstrumentation(),
      ],
    })

    initialized = true
    console.log(
      `OpenTelemetry initialized for "${SERVICE_NAME}" (exporting to ${OTLP_ENDPOINT})`
    )
  } catch (error) {
    // Fail open - don't break the app if tracing fails
    console.error('Failed to initialize OpenTelemetry:', error)
  }
}

// =============================================================================
// Tracer Export for Custom Spans
// =============================================================================

/**
 * Get a tracer for creating custom spans.
 *
 * Usage:
 *   import { getTracer } from './observability'
 *
 *   const tracer = getTracer()
 *   const span = tracer.startSpan('my-operation')
 *   try {
 *     // ... do work ...
 *   } finally {
 *     span.end()
 *   }
 */
export function getTracer() {
  return trace.getTracer(SERVICE_NAME)
}
