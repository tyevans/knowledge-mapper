/**
 * Entity Consolidation Components
 *
 * This module exports all components for the entity consolidation feature,
 * which enables identifying and merging duplicate entities in the knowledge graph.
 */

// Core display components
export { KmConfidenceScore } from './km-confidence-score'
export { KmEntityComparison } from './km-entity-comparison'
export { KmMergeCandidateCard } from './km-merge-candidate-card'

// List and queue components
export { KmReviewQueueList } from './km-review-queue-list'
export { KmMergeHistory } from './km-merge-history'

// Configuration and dashboard
export { KmConsolidationConfig } from './km-consolidation-config'
export { KmConsolidationDashboard } from './km-consolidation-dashboard'
