// frontend/src/types/neuralops.ts
// Canonical TypeScript type definitions for NeuralOps
// Aligned with backend shared/schemas.py

export type Severity = 'P1' | 'P2' | 'P3' | 'P4';
export type IncidentStatus =
    | 'detected'
    | 'investigating'
    | 'remediating'
    | 'resolved'
    | 'post_mortem'
    | 'false_positive';

export interface BlastRadius {
    directly_affected_services: string[];
    at_risk_services: string[];
    total_services_impacted: number;
    estimated_user_impact_percentage?: number;
    slo_breached: boolean;
    slo_names_breached: string[];
}

export interface Incident {
    incident_id: string;
    title: string;
    description?: string;
    severity: Severity;
    status: IncidentStatus;
    primary_service: string;
    affected_services: string[];
    environment: string;
    cloud_provider: string;
    region?: string;
    detected_at: string;
    resolved_at?: string;
    peak_anomaly_score: number;
    ml_confidence: number;
    blast_radius?: BlastRadius | null;
    assigned_to?: string;
    rca_id?: string;
    mttr_minutes?: number;
    is_false_positive: boolean;
    labels: Record<string, string>;
}

export interface Anomaly {
    anomaly_id: string;
    service_name: string;
    environment: string;
    anomaly_score: number;
    lstm_score: number;
    isolation_forest_score: number;
    severity: Severity;
    detected_at: string;
    metrics: Record<string, number>;
    is_forecasted?: boolean;
}

export interface RemediationStep {
    step_number: number;
    action: string;
    rationale: string;
    risk_level: 'low' | 'medium' | 'high';
    estimated_duration_minutes?: number;
    automation_eligible: boolean;
    action_type?: string | null;
    action_parameters: Record<string, unknown>;
}

export interface SimilarIncident {
    incident_id: string;
    title: string;
    similarity_score: number;
    detected_at: string;
    resolved_at?: string | null;
    root_cause_summary?: string | null;
    resolution_summary?: string | null;
    mttr_minutes?: number | null;
}

export interface RCAResult {
    rca_id: string;
    incident_id: string;
    root_cause_summary: string;
    root_cause_confidence: number;
    primary_contributing_factor: string;
    secondary_contributing_factors: string[];
    affected_components: string[];
    remediation_steps: RemediationStep[];
    estimated_resolution_minutes?: number;
    recurrence_risk: 'low' | 'medium' | 'high';
    recurrence_reasoning?: string;
    similar_incidents: SimilarIncident[];
    logs_analyzed_count: number;
    deployments_checked_count: number;
    runbook_markdown?: string;
    created_at: string;
    llm_provider_used: string;
}

export interface AuditRecord {
    audit_id: string;
    action_id: string;
    incident_id: string;
    action_type: string;
    status:
    | 'pending_approval'
    | 'approved'
    | 'executing'
    | 'succeeded'
    | 'failed'
    | 'rolled_back'
    | 'skipped';
    executed_by: string;
    approved_by?: string;
    started_at?: string;
    completed_at?: string;
    duration_seconds?: number;
    output?: string;
    error?: string;
    rolled_back: boolean;
}

export interface DashboardSummary {
    incidents_by_status: Record<string, number>;
    active_incidents_by_severity: Record<string, number>;
    avg_mttr_7d_minutes?: number;
    top_anomalies: Anomaly[];
    generated_at: string;
}

export interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    timestamp?: string;
}
