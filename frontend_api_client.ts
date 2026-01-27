/**
 * api-client.ts - React/TypeScript API Client for Fatigue Analysis Backend
 * =========================================================================
 * 
 * Drop this into your Lovable project's /src/lib folder.
 * 
 * Usage in your React components:
 *   import { analyzeRoster, getChronogram, getDutyDetail } from '@/lib/api-client'
 */

// Configure this to point to your backend
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ============================================================================
// TYPES
// ============================================================================

export interface DutySegment {
  flight_number: string;
  departure: string;
  arrival: string;
  departure_time: string;
  arrival_time: string;
  block_hours: number;
}

export interface Duty {
  duty_id: string;
  date: string;
  report_time_utc: string;
  release_time_utc: string;
  duty_hours: number;
  sectors: number;
  segments: DutySegment[];
  
  // Performance metrics
  min_performance: number;
  avg_performance: number;
  landing_performance: number | null;
  
  // Fatigue metrics
  sleep_debt: number;
  wocl_hours: number;
  prior_sleep: number;
  
  // Risk
  risk_level: 'low' | 'moderate' | 'high' | 'critical' | 'extreme' | 'unknown';
  is_reportable: boolean;
  pinch_events: number;
}

export interface AnalysisResult {
  analysis_id: string;
  roster_id: string;
  pilot_id: string;
  month: string;
  
  // Summary
  total_duties: number;
  total_sectors: number;
  total_duty_hours: number;
  total_block_hours: number;
  
  // Risk summary
  high_risk_duties: number;
  critical_risk_duties: number;
  total_pinch_events: number;
  
  // Sleep metrics
  avg_sleep_per_night: number;
  max_sleep_debt: number;
  
  // Worst case
  worst_duty_id: string;
  worst_performance: number;
  
  // Detailed duties
  duties: Duty[];
}

export interface TimelinePoint {
  timestamp: string;
  timestamp_local: string;
  performance: number;
  sleep_pressure: number;
  circadian: number;
  flight_phase: string | null;
  is_critical: boolean;
}

export interface PinchEvent {
  timestamp: string;
  performance: number;
  phase: string | null;
  cause: string;
}

export interface DutyDetail {
  duty_id: string;
  timeline: TimelinePoint[];
  summary: {
    min_performance: number;
    avg_performance: number;
    landing_performance: number | null;
    wocl_hours: number;
    prior_sleep: number;
    sleep_debt: number;
  };
  pinch_events: PinchEvent[];
}

export interface Statistics {
  analysis_id: string;
  summary: {
    total_duties: number;
    total_sectors: number;
    total_duty_hours: number;
    total_block_hours: number;
  };
  risk: {
    high_risk_duties: number;
    critical_risk_duties: number;
    total_pinch_events: number;
  };
  performance: {
    average_landing_performance: number | null;
    min_landing_performance: number | null;
    max_landing_performance: number | null;
    worst_duty_id: string;
    worst_performance: number;
  };
  sleep: {
    avg_sleep_per_night: number;
    max_sleep_debt: number;
  };
}

// ============================================================================
// API FUNCTIONS
// ============================================================================

/**
 * Upload and analyze a roster file
 */
export async function analyzeRoster(
  file: File,
  pilotId: string,
  month: string,
  homeBase: string,
  homeTimezone: string,
  configPreset: string = 'default'
): Promise<AnalysisResult> {
  
  const formData = new FormData();
  formData.append('file', file);
  formData.append('pilot_id', pilotId);
  formData.append('month', month);
  formData.append('home_base', homeBase);
  formData.append('home_timezone', homeTimezone);
  formData.append('config_preset', configPreset);
  
  const response = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: 'POST',
    body: formData,
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Analysis failed' }));
    throw new Error(error.detail || 'Analysis failed');
  }
  
  return response.json();
}

/**
 * Get a stored analysis by ID
 */
export async function getAnalysis(analysisId: string): Promise<AnalysisResult> {
  const response = await fetch(`${API_BASE_URL}/api/analysis/${analysisId}`);
  
  if (!response.ok) {
    throw new Error('Analysis not found');
  }
  
  return response.json();
}

/**
 * Get detailed timeline data for a single duty
 */
export async function getDutyDetail(
  analysisId: string,
  dutyId: string
): Promise<DutyDetail> {
  
  const response = await fetch(
    `${API_BASE_URL}/api/duty/${analysisId}/${dutyId}`
  );
  
  if (!response.ok) {
    throw new Error('Failed to fetch duty detail');
  }
  
  return response.json();
}

/**
 * Generate a chronogram image (returns base64 data URL)
 */
export async function getChronogram(
  analysisId: string,
  mode: 'risk' | 'state' | 'hybrid' = 'risk',
  theme: 'light' | 'dark' = 'light',
  showAnnotations: boolean = true
): Promise<string> {
  
  const response = await fetch(`${API_BASE_URL}/api/visualize/chronogram`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      analysis_id: analysisId,
      mode,
      theme,
      show_annotations: showAnnotations,
    }),
  });
  
  if (!response.ok) {
    throw new Error('Failed to generate chronogram');
  }
  
  const data = await response.json();
  return data.image; // Returns "data:image/png;base64,..."
}

/**
 * Generate an aviation calendar image (returns base64 data URL)
 */
export async function getCalendar(
  analysisId: string,
  theme: 'light' | 'dark' = 'light'
): Promise<string> {
  
  const response = await fetch(`${API_BASE_URL}/api/visualize/calendar`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      analysis_id: analysisId,
      theme,
    }),
  });
  
  if (!response.ok) {
    throw new Error('Failed to generate calendar');
  }
  
  const data = await response.json();
  return data.image;
}

/**
 * Get summary statistics for the analysis
 */
export async function getStatistics(analysisId: string): Promise<Statistics> {
  const response = await fetch(`${API_BASE_URL}/api/statistics/${analysisId}`);
  
  if (!response.ok) {
    throw new Error('Failed to fetch statistics');
  }
  
  return response.json();
}

/**
 * Check if the backend is healthy
 */
export async function healthCheck(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Get risk level color for styling
 */
export function getRiskColor(riskLevel: string): string {
  switch (riskLevel) {
    case 'low': return 'text-green-600';
    case 'moderate': return 'text-yellow-600';
    case 'high': return 'text-orange-600';
    case 'critical': return 'text-red-600';
    case 'extreme': return 'text-red-800';
    default: return 'text-gray-600';
  }
}

/**
 * Get risk level background color
 */
export function getRiskBgColor(riskLevel: string): string {
  switch (riskLevel) {
    case 'low': return 'bg-green-100';
    case 'moderate': return 'bg-yellow-100';
    case 'high': return 'bg-orange-100';
    case 'critical': return 'bg-red-100';
    case 'extreme': return 'bg-red-200';
    default: return 'bg-gray-100';
  }
}

/**
 * Format performance score with color
 */
export function formatPerformance(performance: number | null): {
  value: string;
  color: string;
} {
  if (performance === null) {
    return { value: '-', color: 'text-gray-400' };
  }
  
  const value = performance.toFixed(0);
  
  if (performance >= 75) return { value, color: 'text-green-600' };
  if (performance >= 65) return { value, color: 'text-yellow-600' };
  if (performance >= 55) return { value, color: 'text-orange-600' };
  if (performance >= 45) return { value, color: 'text-red-600' };
  return { value, color: 'text-red-800' };
}
