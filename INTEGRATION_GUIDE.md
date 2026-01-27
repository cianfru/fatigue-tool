# Connecting Backend to Lovable Frontend - Step by Step Guide

## ✅ BACKEND IS ALREADY RUNNING
Your Python backend is running at: http://localhost:8000

---

## STEP 1: Open Your Lovable Project

1. Go to: https://lovable.dev/projects/
2. Find and open: **fatigue-insight-hub**
3. You should see your project files on the left sidebar

---

## STEP 2: Create the API Client File

In Lovable:

1. **Click the "+" button** next to the `src/lib` folder (create folder if it doesn't exist)
2. **Name the file**: `api-client.ts`
3. **Copy and paste** the entire contents from the file below:

```typescript
// src/lib/api-client.ts

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ============================================================================
// TYPES (matching your existing types in src/types/fatigue.ts)
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
  
  min_performance: number;
  avg_performance: number;
  landing_performance: number | null;
  
  sleep_debt: number;
  wocl_hours: number;
  prior_sleep: number;
  
  risk_level: 'low' | 'moderate' | 'high' | 'critical' | 'extreme';
  is_reportable: boolean;
  pinch_events: number;
}

export interface AnalysisResult {
  analysis_id: string;
  roster_id: string;
  pilot_id: string;
  month: string;
  
  total_duties: number;
  total_sectors: number;
  total_duty_hours: number;
  total_block_hours: number;
  
  high_risk_duties: number;
  critical_risk_duties: number;
  total_pinch_events: number;
  
  avg_sleep_per_night: number;
  max_sleep_debt: number;
  
  worst_duty_id: string;
  worst_performance: number;
  
  duties: Duty[];
}

export interface Statistics {
  totalDuties: number;
  totalSectors: number;
  highRiskDuties: number;
  criticalRiskDuties: number;
  totalPinchEvents: number;
  avgSleepPerNight: number;
  maxSleepDebt: number;
}

// ============================================================================
// API FUNCTIONS
// ============================================================================

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
    const error = await response.json();
    throw new Error(error.detail || 'Analysis failed');
  }
  
  return response.json();
}

export async function getDutyDetail(
  analysisId: string,
  dutyId: string
) {
  
  const response = await fetch(
    `${API_BASE_URL}/api/duty/${analysisId}/${dutyId}`
  );
  
  if (!response.ok) {
    throw new Error('Failed to fetch duty detail');
  }
  
  return response.json();
}

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

export async function healthCheck(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}
```

---

## STEP 3: Update Your FileUpload Component

Find `src/components/fatigue/FileUpload.tsx` in Lovable and update it:

**ADD** this state at the top of the component (after existing useState lines):

```typescript
const [actualFile, setActualFile] = useState<File | null>(null);
```

**MODIFY** the `handleFileChange` function to store the actual File:

```typescript
const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
  const files = e.target.files;
  if (files && files[0]) {
    const file = files[0];
    
    // Store actual file for API call
    setActualFile(file);
    
    // Store metadata for display
    onFileUpload({
      name: file.name,
      size: file.size,
      type: file.type.includes('pdf') ? 'PDF' : 'CSV',
    });
  }
};
```

**PASS** actualFile to parent component by updating the interface:

```typescript
interface FileUploadProps {
  onFileUpload: (file: UploadedFile, actualFile: File) => void;
  uploadedFile: UploadedFile | null;
  onRemoveFile: () => void;
}
```

And update the call:

```typescript
onFileUpload({
  name: file.name,
  size: file.size,
  type: file.type.includes('pdf') ? 'PDF' : 'CSV',
}, file);  // Pass the actual File object
```

---

## STEP 4: Update Your Index.tsx (Main Page)

Find `src/pages/Index.tsx` and make these changes:

**ADD** the import at the top:

```typescript
import { analyzeRoster } from '@/lib/api-client';
import { toast } from 'sonner';
import { format } from 'date-fns';
```

**ADD** state to store the actual file:

```typescript
const [actualFileObject, setActualFileObject] = useState<File | null>(null);
```

**UPDATE** handleFileUpload:

```typescript
const handleFileUpload = (file: UploadedFile, actualFile: File) => {
  setUploadedFile(file);
  setActualFileObject(actualFile);  // Store the actual File
  setAnalysisResults(null);
  setSelectedDuty(null);
};
```

**REPLACE** the handleRunAnalysis function:

```typescript
const handleRunAnalysis = async () => {
  if (!uploadedFile || !actualFileObject) {
    toast.error('Please upload a roster file first');
    return;
  }
  
  setIsAnalyzing(true);
  
  try {
    console.log('Starting analysis...');
    
    const result = await analyzeRoster(
      actualFileObject,
      settings.pilotId,
      format(settings.selectedMonth, 'yyyy-MM'),
      settings.homeBase,
      'Asia/Qatar',  // You can make this dynamic based on homeBase
      settings.configPreset
    );
    
    console.log('Analysis complete:', result);
    
    // Convert API response to match your frontend types
    setAnalysisResults({
      duties: result.duties.map(duty => ({
        dutyId: duty.duty_id,
        date: new Date(duty.date),
        reportTime: duty.report_time_utc,
        releaseTime: duty.release_time_utc,
        dutyHours: duty.duty_hours,
        sectors: duty.sectors,
        minPerformance: duty.min_performance,
        avgPerformance: duty.avg_performance,
        landingPerformance: duty.landing_performance || 0,
        sleepDebt: duty.sleep_debt,
        woclHours: duty.wocl_hours,
        priorSleep: duty.prior_sleep,
        riskLevel: duty.risk_level,
        segments: duty.segments,
      })),
      statistics: {
        totalDuties: result.total_duties,
        totalSectors: result.total_sectors,
        highRiskDuties: result.high_risk_duties,
        criticalRiskDuties: result.critical_risk_duties,
        totalPinchEvents: result.total_pinch_events,
        avgSleepPerNight: result.avg_sleep_per_night,
        maxSleepDebt: result.max_sleep_debt,
      }
    });
    
    toast.success('Analysis complete!');
    
  } catch (error) {
    console.error('Analysis failed:', error);
    toast.error('Analysis failed: ' + (error as Error).message);
  } finally {
    setIsAnalyzing(false);
  }
};
```

---

## STEP 5: Test It!

1. **Make sure backend is running** (it already is at http://localhost:8000)
2. **In Lovable, click "Preview"** button (top right)
3. **Upload a roster file** (PDF or CSV)
4. **Click "Run Fatigue Analysis"**
5. **Watch the magic happen!** 🎉

---

## Troubleshooting

### If you see CORS errors:
- The backend already has CORS configured for localhost:5173 and localhost:8080
- Just make sure your Lovable preview is running on one of these ports

### If analysis fails:
1. Check browser console (F12) for errors
2. Check backend terminal for errors
3. Make sure the roster file is valid (PDF or CSV format)

### If you get "module not found" errors:
- Lovable should auto-install dependencies
- If not, you can add them in Lovable's package manager

---

## Need Help?

Just ask me! I can:
- Show you exactly where to click in Lovable
- Help debug any errors you see
- Create more detailed examples

The backend is ready and waiting for your frontend to connect! 🚀
