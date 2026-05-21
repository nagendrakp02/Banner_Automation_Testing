export interface Banner {
  id: string; url_id: string; name: string; url: string;
  client?: string; dimensions?: string; is_active: boolean; created_at: string;
}
export interface CheckResult {
  id: string; check_id: string; check_name: string; agent_name: string;
  status: 'pending'|'running'|'pass'|'fail'|'error'|'skipped'|'not_applicable';
  raw_data?: Record<string, unknown>; llm_reasoning?: string;
  llm_verdict?: string; final_verdict?: string; screenshot_path?: string;
  duration_ms?: number; error_message?: string; executed_at?: string;
}
export interface TestRun {
  id: string; banner_id: string;
  status: 'pending'|'running'|'completed'|'failed'|'cancelled';
  triggered_by: string; total_checks: number;
  passed_checks: number; failed_checks: number; error_checks: number;
  started_at?: string; completed_at?: string;
  orchestrator_reasoning?: string; created_at: string;
  check_results: CheckResult[];
}
export interface CheckDef { id: string; name: string; agent: string; }
export interface LogEntry { run_id: string; level: string; agent?: string; message: string; timestamp: string; }
export interface HealthStatus { status: string; version: string; vision_api: string; }
