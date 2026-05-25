# --- FILE: types/payroll.types.ts ---
import { Rule, Allowance, Holiday } from '@prisma/client';
import { ShiftDefinition } from '@/types/shiftDefinition.types';

export type TenantConfig = {
  tenantId: string;
  shiftDefinitions: ShiftDefinition[];
  rules: Rule[];
  allowances: Allowance[];
  holidays: Holiday[];
  sleepoverConfiguration?: {
    enabled: boolean;
    enableDisturbance?: boolean;
  };
  timezone?: string;
};

export type CalendarDayType = 'PUBLIC_HOLIDAY' | 'SUNDAY' | 'SATURDAY' | 'WEEKDAY';

export type ShiftType =
  | 'DAY'
  | 'AFTERNOON'
  | 'NIGHT'
  | 'SLEEPOVER'
  | 'SATURDAY'
  | 'SUNDAY'
  | 'PUBLIC_HOLIDAY'
  | 'OVERTIME'
  | 'OVERTIME_L2'
  | 'PAID_GAP_TIME';

export type ShiftSegment = {
  id: string;
  start: Date;
  end: Date;
  durationMinutes: number;
  dayOfWeek: number;
  calendarDayType: CalendarDayType;
  shiftType?: ShiftType;
  isOvernight: boolean;
  isSleepover: boolean;
  isDisturbance?: boolean;
  isGap?: boolean;
  disturbanceId?: string;
  originalShiftStart: Date;
  originalShiftEnd: Date;
  overtimeReason?: string; // Reason for overtime assignment
  sleepoverDefinitionEnd?: Date; // Full sleepover window end time from definition
};

export type ShiftSegmentationResult = {
  segments: ShiftSegment[];
  totalDurationMinutes: number;
  crossesMidnight: boolean;
  spansDays: number;
};

export type SegmentPay = {
  segment: ShiftSegment;
  pay: number;
  rate: number;
  shiftType: ShiftType;
};

export type PaySummary = {
  basePay: number;
  overtimePay: number;
  allowances: number;
  kmTravelPay?: number;
  laundryPay?: number;
  uniformPay?: number;
  sleepDisturbancePay?: number;
  totalPay: number;
  totalPaidMinutes: number;
};

export type ShiftPayResult = {
  segmentPayments: SegmentPay[];
  summary: PaySummary;
  sleepoverFlatRateApplied: boolean;
  allowanceDetails?: AllowanceCalculation[];
  sleepDisturbances?: {
    count: number;
    totalChargedMinutes: number;
    totalPay: number;
  };
};

export type NormalizedTimeRange = {
  start: Date;
  end: Date;
};

export type SleepoverSegment = {
  start: Date;
  end: Date;
  durationHours: number;
  hasContinuousRest: boolean;
  disturbances: SleepDisturbance[];
};

export type SleepDisturbance = {
  timestamp: Date;
  durationMinutes: number;
  reason: string;
};

export type SegmentRate = {
  segment: ShiftSegment;
  baseRate: number;
  multiplier: number;
  calculatedRate: number;
  totalPay: number;
};

export type AuditTrail = {
  timestamp: Date;
  action: string;
  details: Record<string, unknown>;
};

export type PayrollResponse = {
  summary: PaySummary;
  auditTrail: AuditTrail[];
  metadata: {
    tenantId: string;
    calculatedAt: Date;
  };
};

export type AllowanceCalculation = {
  type: 'MEAL' | 'LAUNDRY' | 'KM_TRAVEL' | 'UNIFORM' | 'SLEEPOVER';
  amount: number;
  isEligible: boolean;
  reason?: string;
};

export type HttpHeaders = Record<string, string | string[] | undefined>;

# --- FILE: types/shiftDefinition.types.ts ---
import { ShiftType } from '@prisma/client';

export interface ShiftDefinition {
  id: string;
  tenantId: string;
  year: number;
  type: ShiftType;
  name: string;
  startTime?: string | null;
  endTime?: string | null;
  description?: string | null;
  casualRate?: number | null;
  fullTimeRate?: number | null;
  partTimeRate?: number | null;
  remoteCasualRate?: number | null;
  remoteFullTimeRate?: number | null;
  remotePartTimeRate?: number | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface CreateShiftDefinitionInput {
  year: number;
  type: ShiftType;
  name: string;
  startTime?: string | null;
  endTime?: string | null;
  description?: string | null;
  casualRate?: number | null;
  fullTimeRate?: number | null;
  partTimeRate?: number | null;
  remoteCasualRate?: number | null;
  remoteFullTimeRate?: number | null;
  remotePartTimeRate?: number | null;
  tenantId: string;
}

export type UpdateShiftDefinitionInput = Partial<CreateShiftDefinitionInput>;

export interface ShiftOverlapInput {
  tenantId: string;
  year: number;
  startTime: string; // HH:mm
  endTime: string; // HH:mm
  isSleepover: boolean;
}

export interface ShiftOverlapResult {
  startTime: string;
  endTime: string;
  type: ShiftType;
}

# --- FILE: service/payroll/core/timeUtils.ts ---
/**
 * Parse time string (HH:MM, HH:MM:SS, or ISO timestamp) to minutes since midnight.
 * Handles database time columns which return as ISO timestamps like '1970-01-01T06:00:00.000Z'
 * Uses UTC time so that midnight boundaries align with incoming ISO timestamps (often Z)
 */
export function parseTimeToMinutes(time: string): number {
  if (!time) return 0;

  // Check if this is an ISO timestamp (contains 'T')
  if (time.includes('T')) {
    const date = new Date(time);
    return date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60;
  }

  // Otherwise parse as HH:MM:SS format
  const parts = time.split(':').map(Number);
  const hours = parts[0] || 0;
  const minutes = parts[1] || 0;
  const seconds = parts[2] || 0;

  return hours * 60 + minutes + seconds / 60;
}

/**
 * Calculate duration in minutes between two dates
 */
export function calculateSegmentDuration(segment: { start: Date; end: Date }): number {
  const diffMs = segment.end.getTime() - segment.start.getTime();
  return Math.round(diffMs / (1000 * 60));
}

/**
 * Check if shift crosses midnight (spans multiple days)
 */
export function crossesMidnight(start: Date, end: Date): boolean {
  const startDay = new Date(start).setUTCHours(0, 0, 0, 0);
  const endDay = new Date(end).setUTCHours(0, 0, 0, 0);
  return endDay > startDay;
}

/**
 * Get hour from Date for precision comparison
 */
export function getPreciseHour(date: Date): number {
  return date.getUTCHours() + date.getUTCMinutes() / 60;
}

/**
 * Extract hour (0-23) from a time string (HH:MM, HH:MM:SS, or ISO timestamp)
 */
export function extractHourFromTimeString(time: string): number {
  if (!time) return 0;

  if (time.includes('T')) {
    const date = new Date(time);
    return date.getUTCHours();
  }

  return parseInt(time.split(':')[0]) || 0;
}

/**
 * Extract minute (0-59) from a time string (HH:MM, HH:MM:SS, or ISO timestamp)
 */
export function extractMinuteFromTimeString(time: string): number {
  if (!time) return 0;

  if (time.includes('T')) {
    const date = new Date(time);
    return date.getUTCMinutes();
  }

  return parseInt(time.split(':')[1]) || 0;
}

# --- FILE: util/calendar/calendarUtils.ts ---
import { Holiday } from '@prisma/client';
import { CalendarDayType } from '@/types/payroll.types';

function toLocalDateString(d: Date, timezone?: string): string {
  if (!timezone || timezone === 'UTC') return d.toISOString().slice(0, 10);
  return d.toLocaleDateString('en-CA', { timeZone: timezone }); // YYYY-MM-DD
}

function getLocalDayOfWeek(date: Date, timezone?: string): number {
  if (!timezone || timezone === 'UTC') return date.getUTCDay();
  const dayName = date.toLocaleDateString('en-US', { timeZone: timezone, weekday: 'short' });
  return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(dayName);
}

export function isPublicHoliday(date: Date, holidays: Holiday[], timezone?: string): boolean {
  const dateKey = toLocalDateString(date, timezone);
  return holidays.some((h) => toLocalDateString(h.date, timezone) === dateKey);
}

export function isSaturday(date: Date, timezone?: string): boolean {
  return getLocalDayOfWeek(date, timezone) === 6;
}

export function isSunday(date: Date, timezone?: string): boolean {
  return getLocalDayOfWeek(date, timezone) === 0;
}

export function isWeekday(date: Date, timezone?: string): boolean {
  const day = getLocalDayOfWeek(date, timezone);
  return day >= 1 && day <= 5;
}

/**
 * High-level helper for later stages
 */
export function resolveCalendarDayType(date: Date, holidays: Holiday[], timezone?: string): CalendarDayType {
  if (isPublicHoliday(date, holidays, timezone)) return 'PUBLIC_HOLIDAY';
  if (isSunday(date, timezone)) return 'SUNDAY';
  if (isSaturday(date, timezone)) return 'SATURDAY';
  return 'WEEKDAY';
}

# --- FILE: util/week.util.ts ---
/**
 * Returns the UTC instant corresponding to 00:00:00 in the given timezone on the
 * first day of the work week that contains `date`.
 *
 * When `timezone` is omitted (or UTC), the original UTC-midnight behaviour is preserved
 * so all existing callers remain correct.
 */
export const getWeekStart = (date: Date, startDayIndex: number, timezone?: string): Date => {
  if (!timezone || timezone === 'UTC') {
    // Legacy UTC path — unchanged behaviour
    const d = new Date(date);
    const day = d.getUTCDay();
    const diff = (day - startDayIndex + 7) % 7;
    d.setUTCDate(d.getUTCDate() - diff);
    d.setUTCHours(0, 0, 0, 0);
    return d;
  }

  // Timezone-aware path: find which local calendar day `date` falls on, walk back
  // to the nearest start-of-week day, then return the UTC equivalent of local midnight.
  const localDateStr = date.toLocaleDateString('en-CA', { timeZone: timezone }); // YYYY-MM-DD
  const localDayOfWeek = new Date(localDateStr + 'T12:00:00Z').getUTCDay(); // calendar day of week (UTC on noon avoids DST edge)

  // Adjust using the local calendar date's day-of-week, not UTC
  const diff = (localDayOfWeek - startDayIndex + 7) % 7;

  // Walk back `diff` days from the local date string
  const [y, m, d] = localDateStr.split('-').map(Number);
  const weekStartLocalDate = new Date(Date.UTC(y, m - 1, d - diff));
  const weekStartLocalStr = weekStartLocalDate.toISOString().slice(0, 10); // YYYY-MM-DD

  // Compute UTC offset at noon UTC on that day (avoids DST ambiguity)
  const noonUTC = new Date(weekStartLocalStr + 'T12:00:00Z');
  const localHourAtNoon = parseInt(
    noonUTC.toLocaleString('en-US', { timeZone: timezone, hour: 'numeric', hour12: false })
  );
  const localMinAtNoon = parseInt(
    noonUTC.toLocaleString('en-US', { timeZone: timezone, minute: 'numeric' })
  );
  const utcOffsetMinutes = localHourAtNoon * 60 + localMinAtNoon - 720; // local - UTC at noon

  const [wy, wm, wd] = weekStartLocalStr.split('-').map(Number);
  return new Date(Date.UTC(wy, wm - 1, wd) - utcOffsetMinutes * 60000);
};

export const getWeekEnd = (weekStart: Date): Date => {
  const end = new Date(weekStart);
  end.setUTCDate(end.getUTCDate() + 7);
  end.setUTCMilliseconds(-1);
  return end;
};

/** Fortnight = 2 weeks aligned to START_OF_WEEK. Fixed to employer's roster/pay cycle (e.g. Mon 1 Feb–Sun 14 Feb). */
export const getFortnightStart = (date: Date, startDayIndex: number): Date => {
  const weekStart = getWeekStart(date, startDayIndex);
  const msPerWeek = 7 * 24 * 60 * 60 * 1000;
  const weekNum = Math.floor(weekStart.getTime() / msPerWeek);
  const weeksIntoFortnight = weekNum % 2;
  const fortnightStart = new Date(weekStart);
  fortnightStart.setUTCDate(fortnightStart.getUTCDate() - weeksIntoFortnight * 7);
  return fortnightStart;
};

export const getFortnightEnd = (fortnightStart: Date): Date => {
  const end = new Date(fortnightStart);
  end.setUTCDate(end.getUTCDate() + 14); // 14-day block
  end.setUTCMilliseconds(-1);
  return end;
};

/** Month = calendar month (1st to last day). */
export const getMonthStart = (date: Date): Date => {
  const d = new Date(date);
  d.setUTCDate(1);
  d.setUTCHours(0, 0, 0, 0);
  return d;
};

export const getMonthEnd = (monthStart: Date): Date => {
  const end = new Date(monthStart);
  end.setUTCMonth(end.getUTCMonth() + 1);
  end.setUTCMilliseconds(-1);
  return end;
};

# --- FILE: controller/payroll.controller.ts ---
import { Request, Response } from 'express';
import { catchAsync } from '@/util/catchAsync';
import { HTTP_STATUS } from '@/constant';
import { processShift } from '@/service/payroll/engine/payrollEngine';
import { adjustEndIfCrossesMidnight } from '@/util/time/timeNormalization';
import { buildTenantConfig, buildPrevShiftConfig } from '@/service/payroll/tenantConfig.service';
// Import enums as string literals since Prisma client exports may vary
// Using string literals for better compatibility
import { prisma } from '@/prisma';
import { getTenantIdFromHeader } from '@/service/payroll/tenantConfig.service';
import { SleepDisturbanceInput } from '@/service/payroll/sleepDisturbance.service';
import { calculateBrokenShiftsForStaffOnDate } from '@/service/brokenShift.service';
import {
  calculatePayoutTax,
  formatTaxBreakdown,
  AllowancesInput,
} from '@/service/payroll/taxCalculation.service';

import { getWeeklyHoursForStaff, calculateWeeklyHours } from '@/service/weeklyHours.service';
import {
  calculateWeeklyOvertimeData,
  calculateWeeklyOvertimePay,
  calculateFortnightlyOvertimeData,
  calculateFortnightlyOvertimePay,
  calculateMonthlyOvertimeData,
  calculateMonthlyOvertimePay,
  getEffectiveBaseRate,
} from '@/util/weeklyOvertime.util';
import { buildShiftSegments } from '@/service/payroll/shiftSegmentation.service';
import { getWeekStart } from '@/util/week.util';
import { persistShiftPayroll } from '@/service/payroll/shiftPayrollPersistence.service';
import type { TaxCalculationResult } from '@/service/payroll/taxCalculation.service';

/**
 * calculatePayroll
 *
 * 1. Creates a Shift record in the DB (per user request).
 * 2. Runs the payroll engine.
 * 3. Returns the full calculation result.
 */

const roundCurrency = (value: number): number => Math.round((value + Number.EPSILON) * 100) / 100;

export const calculatePayroll = catchAsync(async (req: Request, res: Response): Promise<void> => {
  const tenantId = getTenantIdFromHeader(req.headers);
  const {
    shiftId: externalShiftId,
    staffId,
    staffName,
    employmentType,
    baseRate,
    start,
    end,
    sleepDisturbances,
    isSleepover,
    kmTravelled,
    isRemote,
    year,
    enabledAllowances,
    timezone,
  } = req.body;

  // Validate year presence explicitly
  if (!year) {
    res.status(400).json({
      success: false,
      message: 'Year is required',
    });
    return;
  }

  if (!externalShiftId || typeof externalShiftId !== 'string') {
    res.status(400).json({
      success: false,
      message: 'shiftId (external shift identifier) is required',
    });
    return;
  }

  // Validate that start/end are valid dates
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
    res.status(400).json({ message: 'Invalid start or end datetime' });
    return;
  }

  // Convert string to boolean if needed
  const sleepoverEnabled = isSleepover === true || isSleepover === 'true';
  const remoteEnabled = isRemote === true || isRemote === 'true';

  const adjustedEnd = adjustEndIfCrossesMidnight(startDate, endDate);
  const startTime = startDate;
  const endTime = adjustedEnd;

  const normalizedDisturbances: SleepDisturbanceInput[] = (sleepDisturbances || []).map(
    (
      d: SleepDisturbanceInput & {
        timestamp?: string | Date;
        durationMinutes?: number;
        duration?: number;
      }
    ) => {
      const distStart = new Date(d.timestamp ?? d.startTime);
      const durationMin = Number(d.durationMinutes ?? d.duration ?? 0);
      const distEnd = new Date(distStart.getTime() + durationMin * 60000);

      return {
        startTime: distStart,
        endTime: distEnd,
        reason: d.reason,
      };
    }
  );

  // 1. Fetch Configuration
  const tenantConfig = await buildTenantConfig(tenantId, year, startTime, endTime, timezone);

  // 2. Initial Payroll Calculation (to get segments)
  // We need to run this first to get the segments so we can save them to the DB?
  // Or we can just create a single WORK segment for now as the 'raw' input if not provided.
  // The seed example creates a single WORK segment spanning the whole shift.

  // Build segments (splits sleepover into work/sleepover/work based on definitions)
  const builtSegments = buildShiftSegments(startTime, endTime, tenantConfig, {
    allowSleepover: isSleepover,
    forceSleepover: isSleepover,
  }).segments;

  // Merge adjacent/overlapping segments with the same mapped segment type (WORK vs SLEEPOVER)
  const mergedSegments = builtSegments
    .map((seg) => ({
      ...seg,
      mappedType: (seg.shiftType === 'SLEEPOVER' ? 'SLEEPOVER' : 'WORK') as 'SLEEPOVER' | 'WORK',
    }))
    .sort((a, b) => a.start.getTime() - b.start.getTime())
    .reduce(
      (acc, seg) => {
        const last = acc[acc.length - 1];
        if (
          last &&
          last.mappedType === seg.mappedType &&
          last.end.getTime() >= seg.start.getTime()
        ) {
          // Merge by extending end to the max of both
          if (seg.end.getTime() > last.end.getTime()) {
            last.end = seg.end;
          }
          return acc;
        }
        acc.push(seg);
        return acc;
      },
      [] as Array<(typeof builtSegments)[number] & { mappedType: 'WORK' | 'SLEEPOVER' }>
    );

  const prismaSegments = mergedSegments.map((seg) => {
    const type = seg.mappedType === 'SLEEPOVER' ? 'SLEEPOVER' : 'WORK';

    return {
      type,
      startTime: seg.start,
      endTime: seg.end,
    };
  });

  // 3. Get Hours for Overtime Calculation based on Payment Frequency
  // IMPORTANT: Refresh the cache BEFORE the current shift exists in the DB so that
  // priorPeriodicHours reflects only previously-completed shifts (handles historical imports
  // and first-run scenarios where the cache may be stale or absent).
  await calculateWeeklyHours(tenantId, year, startTime, tenantConfig.timezone);

  const freqRule = await prisma.rule.findFirst({
    where: { tenantId, year, type: 'PAYMENT_FREQUENCY' },
  });
  const frequencyValue = parseInt(freqRule?.value?.toString() || '2'); // Default Weekly (2)

  const payrollHoursRecord = await getWeeklyHoursForStaff(tenantId, staffId, year, startTime, tenantConfig.timezone);

  // Define applicable thresholds and their priority chain
  const weeklyRule = await prisma.rule.findFirst({
    where: { tenantId, year, type: 'MAX_WEEKLY_HOURS' },
  });
  const fortnightlyRule = await prisma.rule.findFirst({
    where: { tenantId, year, type: 'MAX_FORTNIGHT_HOURS' },
  });
  const monthlyRule = await prisma.rule.findFirst({
    where: { tenantId, year, type: 'MAX_MONTHLY_HOURS' },
  });

  const weeklyThreshold = Number(weeklyRule?.value || 38);
  const fortnightlyThresh = Number(fortnightlyRule?.value || 76);
  const monthlyThresh = Number(monthlyRule?.value || 152);

  const currentWeeklyWork = payrollHoursRecord?.weeklyHours || 0;
  const currentFortnightlyWork = payrollHoursRecord?.fortnightlyHours || 0;
  const currentMonthlyWork = payrollHoursRecord?.monthlyHours || 0;

  const gaps: Array<{ reason: string; gap: number; prior: number; limit: number }> = [];

  gaps.push({
    reason: 'Weekly',
    gap: weeklyThreshold - currentWeeklyWork,
    prior: currentWeeklyWork,
    limit: weeklyThreshold,
  });

  if (frequencyValue >= 3) {
    gaps.push({
      reason: 'Fortnightly',
      gap: fortnightlyThresh - currentFortnightlyWork,
      prior: currentFortnightlyWork,
      limit: fortnightlyThresh,
    });
  }
  if (frequencyValue >= 4) {
    gaps.push({
      reason: 'Monthly',
      gap: monthlyThresh - currentMonthlyWork,
      prior: currentMonthlyWork,
      limit: monthlyThresh,
    });
  }

  const minGapItem = gaps.reduce((min, item) => (item.gap < min.gap ? item : min), gaps[0]);

  let primaryFreq = 'Weekly';
  let primaryPrior = currentWeeklyWork;
  let primaryLimit = weeklyThreshold;

  if (frequencyValue === 3) {
    primaryFreq = 'Fortnightly';
    primaryPrior = currentFortnightlyWork;
    primaryLimit = fortnightlyThresh;
  } else if (frequencyValue === 4) {
    primaryFreq = 'Monthly';
    primaryPrior = currentMonthlyWork;
    primaryLimit = monthlyThresh;
  }

  let priorPeriodicHours = primaryPrior;
  let periodicOvertimeThreshold = primaryPrior + minGapItem.gap;
  let periodicThresholdReason = minGapItem.reason;
  let priorPeriodicHoursForSummary = primaryPrior;
  let periodicOvertimeThresholdForSummary = primaryLimit;

  // 4. Process Payroll (Logic Engine)
  const prevShift = await buildPrevShiftConfig(tenantId, staffId, startTime);

  // Calculate prior daily hours using local-timezone midnight so that shifts on the same
  // local calendar day are correctly included regardless of their UTC date.
  const tz = tenantConfig.timezone || 'UTC';
  const localDateStr = startTime.toLocaleDateString('en-CA', { timeZone: tz });
  // Derive UTC equivalent of local midnight: sample the UTC offset at noon UTC on that date
  const noonUTC = new Date(localDateStr + 'T12:00:00Z');
  const localHourAtNoon = parseInt(noonUTC.toLocaleString('en-US', { timeZone: tz, hour: 'numeric', hour12: false }));
  const localMinAtNoon = parseInt(noonUTC.toLocaleString('en-US', { timeZone: tz, minute: 'numeric' }));
  const utcOffsetMinutes = localHourAtNoon * 60 + localMinAtNoon - 720; // offset vs UTC noon
  const [ldY, ldM, ldD] = localDateStr.split('-').map(Number);
  const startOfDay = new Date(Date.UTC(ldY, ldM - 1, ldD) - utcOffsetMinutes * 60000);

  const priorShiftsOfDay = await prisma.shift.findMany({
    where: {
      tenantId,
      staffId,
      startTime: { gte: startOfDay, lt: startTime },
    },
    include: { segments: true },
  });

  let priorDailyHours = 0;
  for (const s of priorShiftsOfDay) {
    for (const seg of s.segments) {
      if (seg.type === 'WORK') {
        const segStart = new Date(seg.startTime);
        const segEnd = new Date(seg.endTime);
        priorDailyHours += (segEnd.getTime() - segStart.getTime()) / (1000 * 60 * 60);
      }
    }
  }

  // Create Shift in DB (after weekly/daily prior-hours are locked in)
  const shiftData = {
    tenantId,
    staffId,
    staffName: staffName || 'Test User',
    employmentType: employmentType,
    year,
    startTime,
    endTime,
    baseRate: Number(baseRate),
    isPublicHoliday: false,
    segments: {
      create: prismaSegments,
    },
  };

  const createdShift = await prisma.shift.create({
    data: shiftData,
    include: { segments: true },
  });

  // Map employment type string to service logic string
  let serviceEmploymentType: 'casual' | 'fullTime' | 'partTime' = 'partTime'; // Default fallback

  if (employmentType === 'CASUAL') serviceEmploymentType = 'casual';
  else if (employmentType === 'FULL_TIME') serviceEmploymentType = 'fullTime';
  else if (employmentType === 'PART_TIME') serviceEmploymentType = 'partTime';

  console.log('[OVERTIME DEBUG]', JSON.stringify({
    staffId,
    startTime: startTime.toISOString(),
    timezone: tenantConfig.timezone,
    payrollHoursRecord: payrollHoursRecord ? {
      weekStart: payrollHoursRecord.weekStart,
      weeklyHours: payrollHoursRecord.weeklyHours,
    } : null,
    priorPeriodicHours,
    periodicOvertimeThreshold,
    periodicThresholdReason,
    weeklyThreshold,
    priorDailyHours,
  }));

  const result = await processShift(startTime, endTime, tenantConfig, {
    staffId,
    employmentType: serviceEmploymentType,
    baseRate: Number(baseRate),
    prevShiftEnd: prevShift?.endTime,
    priorPeriodicHours,
    periodicOvertimeThreshold,
    periodicThresholdReason,
    priorDailyHours,
    sleepOver: sleepoverEnabled,
    sleepDisturbances: normalizedDisturbances,
    kmTravelled: kmTravelled ? Number(kmTravelled) : undefined,
    isRemote: remoteEnabled,
    year,
    enabledAllowances,
  });

  // Persist disturbance segments only if sleepover flat rate applied
  if (sleepoverEnabled && result.sleepoverFlatRateApplied && normalizedDisturbances.length > 0) {
    await prisma.shiftSegment.createMany({
      data: normalizedDisturbances.map((d) => ({
        shiftId: createdShift.id,
        type: 'DISTURBANCE',
        startTime: d.startTime,
        endTime: d.endTime,
      })),
    });
  }

  // 5. Update Weekly Hours Table (force update even if locked)

  await calculateWeeklyHours(tenantId, year, startTime, tenantConfig.timezone);

  // If week was locked, unlock it temporarily and recalculate
  const weeklyHoursCheck = await getWeeklyHoursForStaff(tenantId, staffId, year, startTime, tenantConfig.timezone);
  if (weeklyHoursCheck?.isLocked) {
    const freqRule = await prisma.rule.findFirst({
      where: { tenantId, year, type: 'PAYMENT_FREQUENCY' },
    });
    const freqVal = parseInt(freqRule?.value?.toString() || '2');
    const paymentFrequency =
      freqVal === 1
        ? 'DAILY'
        : freqVal === 2
          ? 'WEEKLY'
          : freqVal === 3
            ? 'FORTNIGHTLY'
            : 'MONTHLY';

    await prisma.payrollHours.update({
      where: {
        tenantId_year_staffId_weekStart_paymentFrequency: {
          tenantId,
          year,
          staffId,
          weekStart: weeklyHoursCheck.weekStart,
          paymentFrequency,
        },
      },
      data: { isLocked: false },
    });

    // Recalculate with unlocked week
    await calculateWeeklyHours(tenantId, year, startTime, tenantConfig.timezone);
  }

  // 6. Get Weekly Hours Summary for Response
  const weeklyHoursAfter = await getWeeklyHoursForStaff(tenantId, staffId, year, startTime, tenantConfig.timezone);

  // 7. Get Broken Shift Details for this date (calculated on-demand)
  const brokenShiftCalculation = await calculateBrokenShiftsForStaffOnDate(
    tenantId,
    staffId,
    year,
    startTime
  );

  // Get employment type for utility functions
  const serviceEmpType = employmentType as string;

  // Get effective base rate using utility function
  const rateData = await getEffectiveBaseRate(
    tenantId,
    serviceEmpType,
    baseRate as string,
    [createdShift],
    remoteEnabled
  );
  const { effectiveBaseRate, dayShiftMultiplier, rawBaseRate } = rateData;

  // Calculate weekly overtime data using utility function
  const totalWeeklyHours = weeklyHoursAfter?.weeklyHours || 0;
  const overtimeData = await calculateWeeklyOvertimeData(
    tenantId,
    serviceEmpType,
    totalWeeklyHours,
    undefined,
    remoteEnabled,
    year
  );
  const {
    weeklyNormalHours: normalHours,
    weeklyOvertimeL1Hours,
    weeklyOvertimeL2Hours,
    weeklyOvertimeHours,
    weeklyOvertimeMultiplier,
    weeklyOvertimeL2Multiplier,
  } = overtimeData;

  // Calculate weekly overtime pay using utility function
  const payData = calculateWeeklyOvertimePay(
    normalHours,
    weeklyOvertimeL1Hours,
    weeklyOvertimeL2Hours,
    rawBaseRate, // Use raw base rate for summary calculations to avoid double-multiplication
    dayShiftMultiplier, // Use casual/full-time multiplier for normal pay calculation
    weeklyOvertimeMultiplier,
    weeklyOvertimeL2Multiplier
  );
  const {
    weeklyNormalPay: normalPay,
    weeklyOvertimePay,
    weeklyOvertimeL1Pay,
    weeklyOvertimeL2Pay,
  } = payData;

  // Calculate total allowances (will be used in all summaries)
  const baseAllowances = roundCurrency(
    result.allowanceDetails?.reduce((sum, a) => sum + a.amount, 0) || 0
  );
  const brokenShiftAmount = brokenShiftCalculation.totalAllowanceAmount || 0;
  const totalAllowances = roundCurrency(baseAllowances + brokenShiftAmount);

  // Add broken shift allowance to allowance details if applicable
  const allAllowanceDetails = [...(result.allowanceDetails || [])];
  if (
    brokenShiftCalculation.brokenShiftCount > 0 &&
    (brokenShiftCalculation.totalAllowanceAmount || 0) > 0
  ) {
    for (const detail of brokenShiftCalculation.brokenShiftDetails) {
      if (detail.amount > 0) {
        allAllowanceDetails.push({
          type: detail.allowanceType as any,
          amount: detail.amount,
          isEligible: true,
          reason: `Broken shift occurrence ${detail.brokenShiftNumber} at shift ${detail.position}. Shifts sequence: ${brokenShiftCalculation.shiftSequence.map((s) => `${s.position}${s.type === 'broken' ? '(broken)' : '(normal)'}`).join(', ')}`,
          shiftCount: brokenShiftCalculation.shiftCount,
          brokenShiftCount: brokenShiftCalculation.brokenShiftCount,
          brokenShiftOccurrence: detail.brokenShiftNumber,
          shiftPosition: detail.position,
        } as any);
      }
    }
  }

  // Add human-readable day names to segment payments
  const WEEKDAY_NAMES = [
    'Sunday',
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
  ] as const;
  const mappedCalculation = {
    ...result,
    segmentPayments: result.segmentPayments?.map((p) => ({
      ...p,
      segment: {
        ...p.segment,
        dayOfWeekName: WEEKDAY_NAMES[p.segment.dayOfWeek] ?? String(p.segment.dayOfWeek),
      },
    })),
    summary: {
      ...result.summary,
      allowances: totalAllowances, // Updated to include broken shift allowance
      totalPay: roundCurrency((result.summary?.totalPay || 0) + brokenShiftAmount), // Updated total pay
    },
    allowanceDetails: allAllowanceDetails, // Updated to include broken shift allowance
  };

  // Extract frequency rules for summary
  const maxFortnightly = tenantConfig.rules.find((r) => r.type === 'MAX_FORTNIGHT_HOURS')?.value;
  const maxMonthly = tenantConfig.rules.find((r) => r.type === 'MAX_MONTHLY_HOURS')?.value;

  // Derive gross salary (non-overtime) and overtime from segment payments locally first
  const grossSalary = roundCurrency(
    result.segmentPayments
      .filter((p) => p.shiftType !== 'OVERTIME' && p.shiftType !== 'OVERTIME_L2')
      .reduce((sum, p) => sum + p.pay, 0)
  );
  const grossOvertime = roundCurrency(
    result.segmentPayments
      .filter((p) => p.shiftType === 'OVERTIME' || p.shiftType === 'OVERTIME_L2')
      .reduce((sum, p) => sum + p.pay, 0)
  );

  // Calculate fortnightly overtime data
  const totalFortnightlyHours = roundCurrency(weeklyHoursAfter?.fortnightlyHours || 0);
  const fortnightlyOvertimeData = await calculateFortnightlyOvertimeData(
    tenantId,
    serviceEmpType,
    totalFortnightlyHours,
    maxFortnightly as number,
    remoteEnabled,
    year
  );
  const {
    fortnightlyNormalHours: fortnightlyNormal,
    fortnightlyOvertimeL1Hours,
    fortnightlyOvertimeL2Hours,
    fortnightlyOvertimeHours: fortnightlyOvertime,
    fortnightlyOvertimeMultiplier: fortnightlyMultiplier,
    fortnightlyOvertimeL2Multiplier,
  } = fortnightlyOvertimeData;

  // Since ShiftSegments don't store dollar amounts in the DB (only hours),
  // we use the aggregated historical normal hours (excluding current shift) and multiply by base rate
  const historicalFortnightlyNormalHours = Math.max(0, fortnightlyNormal - normalHours);
  const historicalFortnightlyNormalPay = historicalFortnightlyNormalHours * effectiveBaseRate;
  const trueFortnightlyNormalPayAmount = roundCurrency(
    historicalFortnightlyNormalPay + grossSalary
  );

  const fortnightlyPayData = calculateFortnightlyOvertimePay(
    fortnightlyNormal,
    fortnightlyOvertimeL1Hours,
    fortnightlyOvertimeL2Hours,
    rawBaseRate,
    dayShiftMultiplier,
    fortnightlyMultiplier,
    fortnightlyOvertimeL2Multiplier
  );
  const {
    fortnightlyOvertimePay: fortnightlyOvertimePayAmount,
    fortnightlyOvertimeL1Pay,
    fortnightlyOvertimeL2Pay,
  } = fortnightlyPayData;
  const fortnightlyNormalPayAmount = trueFortnightlyNormalPayAmount;

  // Calculate monthly overtime data
  const totalMonthlyHours = roundCurrency(weeklyHoursAfter?.monthlyHours || 0);
  const monthlyOvertimeData = await calculateMonthlyOvertimeData(
    tenantId,
    serviceEmpType,
    totalMonthlyHours,
    maxMonthly as number,
    remoteEnabled,
    year
  );
  const {
    monthlyNormalHours: monthlyNormal,
    monthlyOvertimeL1Hours,
    monthlyOvertimeL2Hours,
    monthlyOvertimeHours: monthlyOvertime,
    monthlyOvertimeMultiplier: monthlyMultiplier,
    monthlyOvertimeL2Multiplier,
  } = monthlyOvertimeData;

  // Since ShiftSegments don't store dollar amounts in the DB (only hours),
  // we use the aggregated historical normal hours (excluding current shift) and multiply by base rate
  const historicalMonthlyNormalHours = Math.max(0, monthlyNormal - normalHours);
  const historicalMonthlyNormalPay = historicalMonthlyNormalHours * effectiveBaseRate;
  const trueMonthlyNormalPayAmount = roundCurrency(historicalMonthlyNormalPay + grossSalary);

  // Calculate monthly overtime pay
  const monthlyPayData = calculateMonthlyOvertimePay(
    monthlyNormal,
    monthlyOvertimeL1Hours,
    monthlyOvertimeL2Hours,
    rawBaseRate,
    dayShiftMultiplier,
    monthlyMultiplier,
    monthlyOvertimeL2Multiplier
  );
  const {
    monthlyOvertimePay: monthlyOvertimePayAmount,
    monthlyOvertimeL1Pay,
    monthlyOvertimeL2Pay,
  } = monthlyPayData;
  const monthlyNormalPayAmount = trueMonthlyNormalPayAmount;

  // ─── Tax Calculation ──────────────────────────────────────────────────────
  // Map pay frequency value to the ATO frequency key

  // Map allowance details to the tax service input shape
  const taxAllowancesInput: AllowancesInput = {};
  for (const allowance of allAllowanceDetails) {
    const rawType = (allowance as { type: string }).type || '';
    const type = String(rawType).toUpperCase();
    const amount = allowance.amount;
    if (!amount || amount <= 0) continue;

    if (type === 'LAUNDRY' || type === 'UNIFORM') {
      taxAllowancesInput.laundry = roundCurrency((taxAllowancesInput.laundry ?? 0) + amount);
    } else if (type === 'KM_TRAVEL') {
      taxAllowancesInput.kmTravel = {
        totalAmount: roundCurrency((taxAllowancesInput.kmTravel?.totalAmount ?? 0) + amount),
        kmsTravelled: kmTravelled ? Number(kmTravelled) : 0,
      };
    } else if (type === 'MEAL') {
      taxAllowancesInput.overtimeMeal = {
        totalAmount: roundCurrency((taxAllowancesInput.overtimeMeal?.totalAmount ?? 0) + amount),
        occasions: (taxAllowancesInput.overtimeMeal?.occasions ?? 0) + 1,
      };
    } else if (type.includes('BROKEN') || type.includes('BROKENSHIFT')) {
      // Prioritize broken shift for its own line item in the breakdown
      taxAllowancesInput.brokenShift = roundCurrency(
        (taxAllowancesInput.brokenShift ?? 0) + amount
      );
    } else {
      // Catch-all for other award allowances (First Aid, Height, Lead Hand, etc.)
      taxAllowancesInput.taskSkill = roundCurrency((taxAllowancesInput.taskSkill ?? 0) + amount);
    }
  }

  // Run PAYG withholding calculation (force WEEKLY frequency for pro-rata shift estimate)
  const taxResult = await calculatePayoutTax({
    frequency: 'WEEKLY',
    year: Number(year),
    tenantId,
    wages: {
      salary: grossSalary,
      overtime: grossOvertime > 0 ? grossOvertime : undefined,
    },
    allowances: Object.keys(taxAllowancesInput).length > 0 ? taxAllowancesInput : undefined,
  });
  const taxBreakdown = formatTaxBreakdown(taxResult);
  // ─────────────────────────────────────────────────────────────────────────

  // Determine the relevant periodic summary to return as the top-level "summary"
  let summary: any = {};
  let periodTaxResult: TaxCalculationResult | undefined;
  let periodNormalHours = 0;
  let periodOvertimeHours = 0;
  let periodNormalPay = 0;
  let periodOvertimePay = 0;
  let periodTotalHours = 0;

  if (primaryFreq === 'Weekly') {
    const weeklyPeriodTaxResult = await calculatePayoutTax({
      frequency: 'WEEKLY',
      year: Number(year),
      tenantId,
      wages: {
        salary: normalPay,
        overtime: weeklyOvertimePay > 0 ? weeklyOvertimePay : undefined,
      },
      allowances: Object.keys(taxAllowancesInput).length > 0 ? taxAllowancesInput : undefined,
    });

    summary = {
      periodType: 'Weekly',
      threshold: periodicOvertimeThresholdForSummary,
      priorHours: priorPeriodicHoursForSummary,
      totalHours: totalWeeklyHours,
      normalHours: roundCurrency(normalHours),
      overtimeHours: roundCurrency(weeklyOvertimeHours),
      normalPay: roundCurrency(normalPay),
      overtimePay: roundCurrency(weeklyOvertimePay),
      totalPay: roundCurrency(normalPay + weeklyOvertimePay + totalAllowances),
      overtimeRate: weeklyOvertimeMultiplier,
      formula: {
        threshold: `${periodicOvertimeThresholdForSummary} hours per week`,
        overtimeRule:
          periodicThresholdReason !== 'Weekly'
            ? `Hours > ${periodicOvertimeThresholdForSummary} are overtime (Triggered by ${periodicThresholdReason} limit)`
            : `Hours > ${periodicOvertimeThresholdForSummary} are overtime`,
        rate: `Normal: ${dayShiftMultiplier}x, Overtime: ${weeklyOvertimeMultiplier}x${weeklyOvertimeL2Hours > 0 ? ` / ${weeklyOvertimeL2Multiplier}x` : ''}`,
        calculation: `Total Hours: ${totalWeeklyHours}h = Normal: ${roundCurrency(normalHours)}h + Overtime: ${roundCurrency(weeklyOvertimeHours)}h`,
        payBreakdown: `Base Rate: $${rawBaseRate}, Multiplier: ${dayShiftMultiplier}x (Effective: $${effectiveBaseRate}), Normal Pay: $${roundCurrency(normalPay)}, Overtime: $${roundCurrency(weeklyOvertimePay)}, Allowances: $${totalAllowances}, Total Gross: $${roundCurrency(normalPay + weeklyOvertimePay + totalAllowances)}, Tax Withheld: $${roundCurrency(weeklyPeriodTaxResult.totalTaxWithheld)}, Net Pay: $${roundCurrency(weeklyPeriodTaxResult.netPay)}`,
      },
      tax: formatTaxBreakdown(weeklyPeriodTaxResult),
    };
    periodTaxResult = weeklyPeriodTaxResult;
    periodNormalHours = roundCurrency(normalHours);
    periodOvertimeHours = roundCurrency(weeklyOvertimeHours);
    periodNormalPay = roundCurrency(normalPay);
    periodOvertimePay = roundCurrency(weeklyOvertimePay);
    periodTotalHours = totalWeeklyHours;
  } else if (primaryFreq === 'Fortnightly') {
    const fortnightlyGrossRaw =
      fortnightlyNormalPayAmount + fortnightlyOvertimePayAmount + totalAllowances;
    const fortnightlyPeriodTaxResult = await calculatePayoutTax({
      frequency: 'FORTNIGHTLY',
      year: Number(year),
      tenantId,
      wages: {
        salary: roundCurrency(fortnightlyNormalPayAmount),
        overtime:
          fortnightlyOvertimePayAmount > 0
            ? roundCurrency(fortnightlyOvertimePayAmount)
            : undefined,
      },
      allowances: Object.keys(taxAllowancesInput).length > 0 ? taxAllowancesInput : undefined,
    });
    const fortnightlyAllowanceTax = roundCurrency(
      fortnightlyPeriodTaxResult.lineItems
        .filter((i) => i.category === 'ALLOWANCES')
        .reduce((s, i) => s + i.taxWithheld, 0)
    );

    summary = {
      periodType: 'Fortnightly',
      threshold: periodicOvertimeThresholdForSummary,
      priorHours: priorPeriodicHoursForSummary,
      totalHours: totalFortnightlyHours,
      normalHours: roundCurrency(fortnightlyNormal),
      overtimeHours: roundCurrency(fortnightlyOvertime),
      normalPay: roundCurrency(fortnightlyNormalPayAmount),
      overtimePay: roundCurrency(fortnightlyOvertimePayAmount),
      totalPay: roundCurrency(
        fortnightlyNormalPayAmount + fortnightlyOvertimePayAmount + totalAllowances
      ),
      overtimeRate: fortnightlyMultiplier,
      formula: {
        threshold: `${periodicOvertimeThresholdForSummary} hours per fortnight`,
        overtimeRule:
          periodicThresholdReason !== 'Fortnightly'
            ? `Hours > ${periodicOvertimeThresholdForSummary} are overtime (Triggered by ${periodicThresholdReason} limit)`
            : `Hours > ${periodicOvertimeThresholdForSummary} are overtime`,
        rate: `Normal: ${dayShiftMultiplier}x, Overtime: ${fortnightlyMultiplier}x${fortnightlyOvertimeL2Hours > 0 ? ` / ${fortnightlyOvertimeL2Multiplier}x` : ''}`,
        calculation: `Total Hours: ${totalFortnightlyHours}h = Normal: ${roundCurrency(fortnightlyNormal)}h + Overtime: ${roundCurrency(fortnightlyOvertime)}h`,
        payBreakdown: `Base Rate: $${rawBaseRate}, Multiplier: ${dayShiftMultiplier}x (Effective: $${effectiveBaseRate}), Normal Pay: $${roundCurrency(fortnightlyNormalPayAmount)}, Overtime: ${roundCurrency(fortnightlyOvertimeL1Hours)}h × $${rawBaseRate} × ${fortnightlyMultiplier} ($${roundCurrency(fortnightlyOvertimeL1Pay)})${fortnightlyOvertimeL2Hours > 0 ? ` + ${roundCurrency(fortnightlyOvertimeL2Hours)}h × $${rawBaseRate} × ${fortnightlyOvertimeL2Multiplier} ($${roundCurrency(fortnightlyOvertimeL2Pay)})` : ''} = $${roundCurrency(fortnightlyOvertimePayAmount)}, Allowances: $${totalAllowances} (Tax: $${fortnightlyAllowanceTax}), Total Gross: $${roundCurrency(fortnightlyGrossRaw)}, Tax Withheld: $${roundCurrency(fortnightlyPeriodTaxResult.totalTaxWithheld)}, Net Pay: $${roundCurrency(fortnightlyPeriodTaxResult.netPay)}`,
      },
      tax: formatTaxBreakdown(fortnightlyPeriodTaxResult),
    };
    periodTaxResult = fortnightlyPeriodTaxResult;
    periodNormalHours = roundCurrency(fortnightlyNormal);
    periodOvertimeHours = roundCurrency(fortnightlyOvertime);
    periodNormalPay = roundCurrency(fortnightlyNormalPayAmount);
    periodOvertimePay = roundCurrency(fortnightlyOvertimePayAmount);
    periodTotalHours = totalFortnightlyHours;
  } else if (primaryFreq === 'Monthly') {
    const monthlyGrossRaw = monthlyNormalPayAmount + monthlyOvertimePayAmount + totalAllowances;
    const monthlyPeriodTaxResult = await calculatePayoutTax({
      frequency: 'MONTHLY',
      year: Number(year),
      tenantId,
      wages: {
        salary: roundCurrency(monthlyNormalPayAmount),
        overtime:
          monthlyOvertimePayAmount > 0 ? roundCurrency(monthlyOvertimePayAmount) : undefined,
      },
      allowances: Object.keys(taxAllowancesInput).length > 0 ? taxAllowancesInput : undefined,
    });
    const monthlyAllowanceTax = roundCurrency(
      monthlyPeriodTaxResult.lineItems
        .filter((i) => i.category === 'ALLOWANCES')
        .reduce((s, i) => s + i.taxWithheld, 0)
    );

    summary = {
      periodType: 'Monthly',
      threshold: periodicOvertimeThresholdForSummary,
      priorHours: priorPeriodicHoursForSummary,
      totalHours: totalMonthlyHours,
      normalHours: roundCurrency(monthlyNormal),
      overtimeHours: roundCurrency(monthlyOvertime),
      normalPay: roundCurrency(monthlyNormalPayAmount),
      overtimePay: roundCurrency(monthlyOvertimePayAmount),
      totalPay: roundCurrency(monthlyNormalPayAmount + monthlyOvertimePayAmount + totalAllowances),
      overtimeRate: monthlyMultiplier,
      formula: {
        threshold: `${periodicOvertimeThresholdForSummary} hours per month`,
        overtimeRule:
          periodicThresholdReason !== 'Monthly'
            ? `Hours > ${periodicOvertimeThresholdForSummary} are overtime (Triggered by ${periodicThresholdReason} limit)`
            : `Hours > ${periodicOvertimeThresholdForSummary} are overtime`,
        rate: `Normal: ${dayShiftMultiplier}x, Overtime: ${monthlyMultiplier}x${monthlyOvertimeL2Hours > 0 ? ` / ${monthlyOvertimeL2Multiplier}x` : ''}`,
        calculation: `Total Hours: ${totalMonthlyHours}h = Normal: ${roundCurrency(monthlyNormal)}h + Overtime: ${roundCurrency(monthlyOvertime)}h`,
        payBreakdown: `Base Rate: $${rawBaseRate}, Multiplier: ${dayShiftMultiplier}x (Effective: $${effectiveBaseRate}), Normal Pay: $${roundCurrency(monthlyNormalPayAmount)}, Overtime: ${roundCurrency(monthlyOvertimeL1Hours)}h × $${rawBaseRate} × ${monthlyMultiplier} ($${roundCurrency(monthlyOvertimeL1Pay)})${monthlyOvertimeL2Hours > 0 ? ` + ${roundCurrency(monthlyOvertimeL2Hours)}h × $${rawBaseRate} × ${monthlyOvertimeL2Multiplier} ($${roundCurrency(monthlyOvertimeL2Pay)})` : ''} = $${roundCurrency(monthlyOvertimePayAmount)}, Allowances: $${totalAllowances} (Tax: $${monthlyAllowanceTax}), Total Gross: $${roundCurrency(monthlyGrossRaw)}, Tax Withheld: $${roundCurrency(monthlyPeriodTaxResult.totalTaxWithheld)}, Net Pay: $${roundCurrency(monthlyPeriodTaxResult.netPay)}`,
      },
      tax: formatTaxBreakdown(monthlyPeriodTaxResult),
    };
    periodTaxResult = monthlyPeriodTaxResult;
    periodNormalHours = roundCurrency(monthlyNormal);
    periodOvertimeHours = roundCurrency(monthlyOvertime);
    periodNormalPay = roundCurrency(monthlyNormalPayAmount);
    periodOvertimePay = roundCurrency(monthlyOvertimePayAmount);
    periodTotalHours = totalMonthlyHours;
  }

  // Add shared fields to summary
  summary = {
    ...summary,
    weekStart: weeklyHoursAfter?.weekStart,
    weekEnd: weeklyHoursAfter?.weekEnd,
    sleepoverHours: weeklyHoursAfter?.sleepovrHours || 0,
    disturbanceHours: weeklyHoursAfter?.disturbanceHours || 0,
    allowances: totalAllowances,
    allowanceDetails: allAllowanceDetails,
  };

  // Override or merge fields into mappedCalculation.summary
  if (mappedCalculation.summary && summary) {
    mappedCalculation.summary = {
      ...mappedCalculation.summary,
      ...summary,
    };
  }

  const { segmentPayments, allowanceDetails, sleepoverFlatRateApplied, ...restOfCalculation } =
    mappedCalculation;

  // ─── Persist the calculation snapshot ──────────────────────────────────────
  const paymentFrequencyEnum: 'DAILY' | 'WEEKLY' | 'FORTNIGHTLY' | 'MONTHLY' =
    frequencyValue === 1
      ? 'DAILY'
      : frequencyValue === 3
        ? 'FORTNIGHTLY'
        : frequencyValue === 4
          ? 'MONTHLY'
          : 'WEEKLY';

  const taxFrequencyEnum = (taxResult?.frequency || 'WEEKLY') as
    | 'WEEKLY'
    | 'FORTNIGHTLY'
    | 'MONTHLY';
  const totalTaxWithheld = roundCurrency(taxResult?.totalTaxWithheld ?? 0);
  const grossPayPersisted = roundCurrency(grossSalary + grossOvertime + totalAllowances);
  const netPayPersisted = roundCurrency(grossPayPersisted - totalTaxWithheld);

  const bracket = taxResult?.bracket;
  const bracketLabel = bracket
    ? bracket.lessThan !== null
      ? `< $${bracket.lessThan} (a=${bracket.a}, b=${bracket.b})`
      : `> $3,653.00 (a=${bracket.a}, b=${bracket.b})`
    : 'N/A';

  const segmentPaymentsForDb = (result.segmentPayments || []).map((p, idx) => ({
    segmentIndex: idx,
    startTime: new Date(p.segment.start),
    endTime: new Date(p.segment.end),
    durationMinutes: p.segment.durationMinutes,
    resolvedShiftType: p.shiftType as any,
    rateMultiplier: Number(p.rate),
    pay: roundCurrency(p.pay),
    isSleepover: !!p.segment.isSleepover,
    isFlatRate: !!(sleepoverFlatRateApplied && p.segment.isSleepover),
  }));

  const allowancesForDb = allAllowanceDetails
    .filter((a) => (a.amount ?? 0) > 0)
    .map((a) => ({
      type: a.type as any,
      amount: roundCurrency(a.amount),
      taxableAmount: 0,
      taxFreeAmount: 0,
      reason: (a as { reason?: string }).reason ?? '',
    }));

  const responsePayload = {
    shiftId: createdShift.id,
    calculation: {
      segmentPayments,
      sleepoverFlatRateApplied,
      allowanceDetails,
      tax: taxBreakdown,
      ...restOfCalculation,
    },
  };

  let persistedPayroll: Awaited<ReturnType<typeof persistShiftPayroll>> | null = null;
  try {
    persistedPayroll = await persistShiftPayroll({
      tenantId,
      year: Number(year),
      shiftId: createdShift.id,
      externalShiftId,

      staffId,
      staffName: staffName || 'Test User',
      employmentType: employmentType as any,

      baseRate: Number(baseRate),
      isRemote: remoteEnabled,
      kmTravelled: kmTravelled !== undefined && kmTravelled !== null ? Number(kmTravelled) : null,

      shiftStart: startTime,
      shiftEnd: endTime,
      durationMinutes: result.summary?.totalPaidMinutes ?? 0,

      paymentFrequency: paymentFrequencyEnum as any,
      periodThresholdHours: Number(periodicOvertimeThresholdForSummary),
      priorPeriodHours: Number(priorPeriodicHoursForSummary),
      totalPeriodHours: Number(periodTotalHours),
      weekStart: weeklyHoursAfter?.weekStart ?? startTime,
      weekEnd: weeklyHoursAfter?.weekEnd ?? endTime,

      normalHours: normalHours,
      overtimeHours: roundCurrency((result.summary?.totalPaidMinutes ?? 0) / 60 - normalHours),
      basePay: grossSalary,
      overtimePay: grossOvertime,
      allowancesTotal: totalAllowances,
      grossPay: grossPayPersisted,

      taxWithheld: totalTaxWithheld,
      netPay: netPayPersisted,
      taxBracketUsed: bracketLabel,
      taxFrequencyUsed: taxFrequencyEnum as any,

      rawCalculation: responsePayload as any,

      segmentPayments: segmentPaymentsForDb,
      allowances: allowancesForDb,
    });
  } catch (err) {
    // Persistence failure must not break the calculation response; log and continue.
    console.error('Failed to persist ShiftPayroll snapshot:', err);
  }
  // ──────────────────────────────────────────────────────────────────────────

  res.status(HTTP_STATUS.OK).json({
    success: true,
    message: 'Payroll calculated and shift saved successfully',
    data: {
      shiftId: createdShift.id,
      payrollId: persistedPayroll?.id ?? null,
      payrollRecord: persistedPayroll ?? null,
      calculation: {
        segmentPayments,
        sleepoverFlatRateApplied,
        allowanceDetails,
        tax: taxBreakdown,
        ...restOfCalculation,
      },
    },
  });
});

/**
 * DELETE /payroll/shifts/bulk
 * Body: { shiftIds: string[] }
 *
 * Deletes pricing-service Shift records by ID, cascading to ShiftPayroll,
 * ShiftSegmentPayment, and ShiftPayrollAllowance. Used to roll back partial
 * timesheet sync when a mid-loop pricing call fails.
 */
export const rollbackShifts = catchAsync(async (req: Request, res: Response): Promise<void> => {
  const tenantId = getTenantIdFromHeader(req.headers);
  const { shiftIds } = req.body as { shiftIds?: unknown };

  if (!Array.isArray(shiftIds) || shiftIds.length === 0) {
    res.status(400).json({ success: false, message: 'shiftIds must be a non-empty array' });
    return;
  }

  // Capture shift metadata BEFORE deletion so we can recalculate derived tables.
  const shiftsToDelete = await prisma.shift.findMany({
    where: { id: { in: shiftIds as string[] }, tenantId },
    select: { id: true, year: true, staffId: true, startTime: true },
  });

  const { count } = await prisma.shift.deleteMany({
    where: { id: { in: shiftIds as string[] }, tenantId },
  });

  // ── 1. Recalculate PayrollHours (hours + overtime) ───────────────────────
  // calculateWeeklyHours re-scans ShiftSegment rows which were cascade-deleted,
  // so it will produce correct (lower) hour totals for the affected weeks.
  const recalcKeys = new Set<string>();
  for (const s of shiftsToDelete) {
    recalcKeys.add(`${s.year}::${s.startTime.toISOString()}`);
  }
  for (const key of recalcKeys) {
    const [yearStr, startTimeStr] = key.split('::');
    await calculateWeeklyHours(tenantId, Number(yearStr), new Date(startTimeStr)).catch((e) =>
      console.error('rollbackShifts: PayrollHours hour recalc failed', e)
    );
  }

  // ── 2. Recalculate laundryPaid / uniformPaid ─────────────────────────────
  // updateWeeklyAllowanceCache incremented these for each processed shift.
  // Deleting shifts does NOT auto-decrement them, so we recompute from the
  // surviving ShiftPayrollAllowance rows for every affected staffId + week.
  const freqRule = await prisma.rule.findFirst({
    where: { tenantId, type: 'PAYMENT_FREQUENCY' },
  });
  const freqVal = parseInt(freqRule?.value?.toString() || '2');
  const paymentFrequency: 'DAILY' | 'WEEKLY' | 'FORTNIGHTLY' | 'MONTHLY' =
    freqVal === 1 ? 'DAILY' : freqVal === 3 ? 'FORTNIGHTLY' : freqVal === 4 ? 'MONTHLY' : 'WEEKLY';

  const startRule = await prisma.rule.findFirst({
    where: { tenantId, type: 'START_OF_WEEK' },
  });

  // Deduplicate by staffId so we recalculate once per staff member.
  const affectedStaffIds = [...new Set(shiftsToDelete.map((s) => s.staffId))];

  for (const staffId of affectedStaffIds) {
    // Find the affected week(s) for this staff member.
    const staffShifts = shiftsToDelete.filter((s) => s.staffId === staffId);
    const weekStarts = new Set(
      staffShifts.map((s) => getWeekStart(s.startTime, startRule?.value ?? 1).toISOString())
    );

    for (const weekStartIso of weekStarts) {
      const weekStart = new Date(weekStartIso);
      const year = staffShifts[0].year;

      // Sum laundry and uniform from ShiftPayrollAllowance rows that still exist
      // (i.e., belong to surviving payroll records for this staff + week).
      const surviving = await prisma.shiftPayrollAllowance.findMany({
        where: {
          tenantId,
          type: { in: ['LAUNDRY', 'UNIFORM'] },
          shiftPayroll: {
            tenantId,
            staffId,
            isCurrent: true,
            shiftStart: { gte: weekStart },
          },
        },
        select: { type: true, amount: true },
      });

      const laundryPaid = surviving
        .filter((a) => a.type === 'LAUNDRY')
        .reduce((sum, a) => sum + Number(a.amount), 0);
      const uniformPaid = surviving
        .filter((a) => a.type === 'UNIFORM')
        .reduce((sum, a) => sum + Number(a.amount), 0);

      await prisma.payrollHours
        .updateMany({
          where: { tenantId, year, staffId, weekStart, paymentFrequency },
          data: { laundryPaid, uniformPaid },
        })
        .catch((e) => console.error('rollbackShifts: allowance cache reset failed', e));
    }
  }

  res.status(HTTP_STATUS.OK).json({ success: true, data: { deleted: count } });
});

# --- FILE: service/payroll/engine/payrollEngine.ts ---
import { buildShiftSegments } from '@/service/payroll/shiftSegmentation.service';
import { resolveAllSegmentTypes } from '@/service/payroll/shiftTypeResolution.service';
import { getWeekStart, getWeekEnd } from '@/util/week.util';
import {
  calculateShiftPay,
  identifySleepoverSegments,
} from '@/service/payroll/payCalculation.service';
import {
  processSleepDisturbances,
  SleepDisturbanceInput,
} from '@/service/payroll/sleepDisturbance.service';
import { TenantConfig, ShiftPayResult, AllowanceCalculation } from '@/types/payroll.types';
import {
  calculateAllowances,
  AllowanceConfigType,
} from '@/service/payroll/allowanceCalculation.service';
import { buildPrevShiftConfig } from '@/service/payroll/tenantConfig.service';
import {
  getWeeklyAllowanceTotals,
  updateWeeklyAllowanceCache,
} from '@/service/payroll/weeklyAllowance.service';

const roundCurrency = (value: number): number => Math.round((value + Number.EPSILON) * 100) / 100;
export type ShiftProcessingOptions = {
  staffId?: string; // Needed for historical lookups
  employmentType: 'casual' | 'fullTime' | 'partTime';
  baseRate: number;
  sleepOver?: boolean;
  isRemote?: boolean;
  year?: number; // Optional? Or required? User request implies required. Let's make it optional for backward compat but warn/default? Or just number. Controller has it.

  // Contextual overrides (if already known)
  prevShiftEnd?: Date;
  firstShiftStartOfDay?: Date;
  priorDailyHours?: number;
  priorPeriodicHours?: number;
  periodicOvertimeThreshold?: number;
  periodicThresholdReason?: string;

  kmTravelled?: number;
  sleepDisturbances?: SleepDisturbanceInput[];
  enabledAllowances?: AllowanceConfigType[];
};

/**
 * The unified Payroll Engine orchestrator.
 * This provides a clean entry point for calculating pay for any shift.
 */
export async function processShift(
  start: Date,
  end: Date,
  tenantConfig: TenantConfig,
  options: ShiftProcessingOptions
): Promise<ShiftPayResult> {
  if (!options.year) {
    throw new Error('Rule year is required for payroll processing');
  }
  // 0. Automatic Previous Shift Resolution
  let effectivePrevShiftEnd = options.prevShiftEnd;
  if (!effectivePrevShiftEnd && options.staffId) {
    console.log(
      `[Engine] Searching for previous shift for staff ${options.staffId} before ${start.toISOString()} (UTC)`
    );
    const prevShift = await buildPrevShiftConfig(tenantConfig.tenantId, options.staffId, start);
    if (prevShift) {
      console.log(
        `[Engine] Found previous shift ending at ${prevShift.endTime.toISOString()} (UTC)`
      );
      effectivePrevShiftEnd = prevShift.endTime;
    } else {
      console.log(
        `[Engine] No previous shift found for staff ${options.staffId} before ${start.toISOString()}`
      );
    }
  }

  // 1. Segmentation (Applies Minimum Engagement & Sleepover Completion)
  const segmentation = buildShiftSegments(start, end, tenantConfig, {
    forceSleepover: options.sleepOver === true,
    allowSleepover: options.sleepOver === true,
  });

  // 2. Type Resolution (Applies Trigger Upgrades & Break Violations)
  const dailyOvertimeRule = tenantConfig.rules.find((r) => r.type === 'OVERTIME_AFTER_HOURS');
  const resolvedSegments = resolveAllSegmentTypes(segmentation.segments, tenantConfig, {
    dailyOvertimeThreshold: dailyOvertimeRule?.value ?? 10,
    periodicOvertimeThreshold: options.periodicOvertimeThreshold ?? 38,
    periodicThresholdReason: options.periodicThresholdReason ?? 'Weekly',
    prevShiftEnd: options.prevShiftEnd,
    firstShiftStartOfDay: options.firstShiftStartOfDay,
    priorDailyHours: options.priorDailyHours || 0,
    priorPeriodicHours: options.priorPeriodicHours || 0,
    isRemote: options.isRemote,
    employmentType: options.employmentType,
  });

  // 3. Financial Calculation (Applies Multipliers and Flat Rates)
  const payResult = calculateShiftPay(
    resolvedSegments,
    options.baseRate,
    tenantConfig,
    options.employmentType,
    options.isRemote
  );

  // 4. Process Sleep Disturbances (if any) only when sleepover flat rate applied
  if (
    payResult.sleepoverFlatRateApplied &&
    options.sleepDisturbances &&
    options.sleepDisturbances.length > 0
  ) {
    const { sleepoverSegments } = identifySleepoverSegments(resolvedSegments);

    const disturbanceResult = processSleepDisturbances(
      options.sleepDisturbances,
      options.baseRate,
      tenantConfig.shiftDefinitions,
      options.employmentType,
      options.isRemote,
      tenantConfig,
      sleepoverSegments
    );

    // Add disturbance pay to the result
    if (disturbanceResult.disturbances.length > 0) {
      payResult.sleepDisturbances = {
        count: disturbanceResult.disturbances.length,
        totalChargedMinutes: disturbanceResult.totalChargedMinutes,
        totalPay: disturbanceResult.totalPay,
      };

      // Update summary
      payResult.summary.sleepDisturbancePay = roundCurrency(disturbanceResult.totalPay);

      payResult.summary.totalPay = roundCurrency(
        payResult.summary.totalPay + disturbanceResult.totalPay
      );
    }
  }

  // 5. Calculate Allowances (Step 5, 6, 11)
  // Get weekly allowance totals for this staff member
  const allowanceAnchor = resolvedSegments[0]?.start || new Date();
  const startRule = tenantConfig.rules.find((r) => r.type === 'START_OF_WEEK');
  const startDayIndex = startRule?.value ? Number(startRule.value) : 0; // Sunday=0
  const weekStart = getWeekStart(allowanceAnchor, startDayIndex, tenantConfig.timezone);
  const weekEnd = getWeekEnd(weekStart);
  const weeklyAllowanceTotals = await getWeeklyAllowanceTotals(
    tenantConfig.tenantId,
    options.staffId || '',
    options.year,
    weekStart,
    weekEnd
  );

  const allowances = calculateAllowances(resolvedSegments, tenantConfig, {
    kmTravelled: options.kmTravelled,
    overtimeHours: resolvedSegments
      .filter((s) => s.shiftType === 'OVERTIME' || s.shiftType === 'OVERTIME_L2')
      .reduce((sum, s) => sum + s.durationMinutes / 60, 0),
    isSleepover: options.sleepOver,
    weeklyAllowanceTotals,
    enabledAllowances: options.enabledAllowances,
  });

  // Update weekly allowance cache for paid per-shift allowances
  if (options.staffId) {
    const isWeeklyAllowance = (
      a: AllowanceCalculation
    ): a is AllowanceCalculation & { type: 'LAUNDRY' | 'UNIFORM' } =>
      a.type === 'LAUNDRY' || a.type === 'UNIFORM';

    const weeklyAllowances = allowances
      .filter(isWeeklyAllowance)
      .filter((a) => a.isEligible && a.amount > 0);

    for (const a of weeklyAllowances) {
      await updateWeeklyAllowanceCache(
        tenantConfig.tenantId,
        options.staffId!,
        options.year,
        weekStart,
        a.type,
        a.amount
      );
    }
  } else {
    console.warn('[Engine] Skipping weekly allowance cache update because staffId is missing');
  }

  if (allowances.length > 0) {
    const totalAllowancePay = roundCurrency(
      allowances.filter((a) => a.isEligible).reduce((sum, a) => sum + a.amount, 0)
    );

    payResult.allowanceDetails = allowances;
    payResult.summary.allowances = totalAllowancePay;
    payResult.summary.totalPay += totalAllowancePay;
    payResult.summary.allowances = roundCurrency(payResult.summary.allowances);
    payResult.summary.totalPay = roundCurrency(payResult.summary.totalPay);
  }

  return payResult;
}

# --- FILE: service/payroll/shiftSegmentation.service.ts ---
import { randomUUID } from 'crypto';
import { ShiftDefinition } from '@/types/shiftDefinition.types';
import { ShiftSegment, TenantConfig, ShiftSegmentationResult } from '@/types/payroll.types';
import { resolveCalendarDayType } from '@/util/calendar/calendarUtils';
import {
  parseTimeToMinutes,
  calculateSegmentDuration,
  crossesMidnight,
  extractHourFromTimeString,
} from '@/service/payroll/core/timeUtils';
import { calculateMinimumEngagementGap } from '@/service/payroll/rules/minimumEngagement.rule';

/**
 * Split shift by tenant-specific shift definitions
 */
export function splitByShiftDefinition(
  start: Date,
  end: Date,
  shiftDefinitions: ShiftDefinition[],
  options: { allowSleepover?: boolean; timezone?: string } = {}
): Array<{ start: Date; end: Date; matchedDefinition?: ShiftDefinition }> {
  const result: Array<{ start: Date; end: Date; matchedDefinition?: ShiftDefinition }> = [];

  const boundaries: number[] = [];
  const timezone = options.timezone || 'Asia/Kolkata';
  
  // Get reference start at midnight in the specified timezone
  const refStart = new Date(start);
  if (timezone === 'UTC') {
    refStart.setUTCHours(0, 0, 0, 0);
  } else {
    // Convert to local timezone midnight using Intl.DateTimeFormat for better accuracy
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
    
    // Get the local date parts
    const parts = formatter.formatToParts(start);
    const getPart = (type: string) => parts.find(p => p.type === type)?.value || '';
    
    const year = getPart('year');
    const month = getPart('month');
    const day = getPart('day');
    
    // Create midnight in local timezone
    const midnightLocal = new Date(`${year}-${month}-${day}T00:00:00`);
    const offsetMs = new Date(midnightLocal.toLocaleString('en-US', { timeZone: timezone })).getTime() - midnightLocal.getTime();
    refStart.setTime(new Date(`${year}-${month}-${day}T00:00:00`).getTime() - offsetMs);
  }

  const totalDurationSeconds = (end.getTime() - start.getTime()) / 1000;
  const startOffsetSeconds = (start.getTime() - refStart.getTime()) / 1000;
  const endOffsetSeconds = startOffsetSeconds + totalDurationSeconds;

  boundaries.push(startOffsetSeconds);
  boundaries.push(endOffsetSeconds);

  // Compulsory Midnight splits (skip if shift fully sits inside a sleepover window)
  const numDaysScan = Math.ceil(endOffsetSeconds / 86400) + 1;

  const sleepoverDefs =
    options.allowSleepover === false
      ? []
      : shiftDefinitions.filter((d) => d.type === 'SLEEPOVER' && d.startTime && d.endTime);
  let skipMidnightSplit = false;

  // When forcing sleepover, check if shift overlaps with sleepover time window
  if (sleepoverDefs.length > 0 && options.allowSleepover !== false) {
    for (const def of sleepoverDefs) {
      const { startTime, endTime } = def;
      if (!startTime || !endTime) continue;

      const defStartSec = Math.round(parseTimeToMinutes(startTime as string)) * 60;
      const defEndSecRaw = Math.round(parseTimeToMinutes(endTime as string)) * 60;
      const defEndSec = defEndSecRaw < defStartSec ? defEndSecRaw + 86400 : defEndSecRaw;

      // Check windows around the shift span (current day and next day to cover overnight)
      for (let day = -1; day <= numDaysScan; day++) {
        const winStart = day * 86400 + defStartSec;
        const winEnd = day * 86400 + defEndSec;

        // Check if shift overlaps with sleepover window (not fully contained)
        if (!(endOffsetSeconds <= winStart || startOffsetSeconds >= winEnd)) {
          skipMidnightSplit = true;
          break;
        }
      }
      if (skipMidnightSplit) break;
    }
  }

  // When forcing sleepover, add sleepover boundaries to ensure proper segmentation
  if (sleepoverDefs.length > 0 && options.allowSleepover !== false) {
    for (const def of sleepoverDefs) {
      const { startTime, endTime } = def;
      if (!startTime || !endTime) continue;

      const defStartSec = Math.round(parseTimeToMinutes(startTime as string)) * 60;
      const defEndSecRaw = Math.round(parseTimeToMinutes(endTime as string)) * 60;
      const defEndSec = defEndSecRaw < defStartSec ? defEndSecRaw + 86400 : defEndSecRaw;

      // Add sleepover boundaries for each day
      for (let day = -1; day <= numDaysScan; day++) {
        const winStart = day * 86400 + defStartSec;
        const winEnd = day * 86400 + defEndSec;

        // Add boundaries if they overlap with the shift span
        if (winEnd > startOffsetSeconds && winStart < endOffsetSeconds) {
          if (winStart > startOffsetSeconds && winStart < endOffsetSeconds) {
            boundaries.push(winStart);
          }
          if (winEnd > startOffsetSeconds && winEnd < endOffsetSeconds) {
            boundaries.push(winEnd);
          }
        }
      }
    }
  }

  if (!skipMidnightSplit) {
    // Add midnight boundaries in the specified timezone
    for (let day = 0; day < numDaysScan; day++) {
      const offset = day * 86400;
      if (offset > startOffsetSeconds && offset < endOffsetSeconds) {
        boundaries.push(offset);
      }
    }
  }

  // Definition-based boundaries (e.g. 6am, 8pm, 10pm)
  for (let day = 0; day < numDaysScan; day++) {
    const dayOffset = day * 86400;
    for (const def of shiftDefinitions) {
      if (!def.startTime || !def.endTime) continue;

      const defStartSec = Math.round(parseTimeToMinutes(def.startTime)) * 60;
      const defEndSec = Math.round(parseTimeToMinutes(def.endTime)) * 60;

      const absStart = dayOffset + defStartSec;
      let absEnd = dayOffset + defEndSec;

      if (defEndSec < defStartSec) absEnd += 86400; // Overnight range

      if (absStart > startOffsetSeconds && absStart < endOffsetSeconds) boundaries.push(absStart);
      if (absEnd > startOffsetSeconds && absEnd < endOffsetSeconds) boundaries.push(absEnd);
    }
  }

  const sortedBoundaries = Array.from(new Set(boundaries)).sort((a, b) => a - b);

  for (let i = 0; i < sortedBoundaries.length - 1; i++) {
    const segStartSec = sortedBoundaries[i];
    const segEndSec = sortedBoundaries[i + 1];

    const segStart = new Date(refStart.getTime() + segStartSec * 1000);
    const segEnd = new Date(refStart.getTime() + segEndSec * 1000);
    
    // Convert segment start time to local timezone for matching
    let segStartInDaySec: number;
    if (timezone === 'UTC') {
      segStartInDaySec = segStartSec % 86400;
    } else {
      // Get local time of day in seconds
      const localHours = parseInt(segStart.toLocaleString('en-US', { timeZone: timezone, hour: 'numeric', hour12: false }));
      const localMinutes = parseInt(segStart.toLocaleString('en-US', { timeZone: timezone, minute: 'numeric' }));
      const localSeconds = parseInt(segStart.toLocaleString('en-US', { timeZone: timezone, second: 'numeric' }));
      segStartInDaySec = localHours * 3600 + localMinutes * 60 + localSeconds;
    }
    
    // Debug logging
    console.log(`[SEGMENT ${i}] ${segStart.toISOString()} - ${segEnd.toISOString()}, segStartInDaySec: ${segStartInDaySec} (${Math.floor(segStartInDaySec/3600)}h ${Math.floor((segStartInDaySec%3600)/60)}m), Timezone: ${timezone}`);

    // Find matching definition
    const matchingDefs = shiftDefinitions.filter((def) => {
      if (!def.startTime || !def.endTime) return false;
      const dStart = Math.round(parseTimeToMinutes(def.startTime)) * 60;
      const dEnd = Math.round(parseTimeToMinutes(def.endTime)) * 60;

      if (dEnd < dStart) {
        // Overnight range matches
        return segStartInDaySec >= dStart || segStartInDaySec < dEnd;
      } else {
        return segStartInDaySec >= dStart && segStartInDaySec < dEnd;
      }
    });
    
    console.log(`[SEGMENT ${i}] Matching defs:`, matchingDefs.map(d => `${d.type} (${d.startTime}-${d.endTime})`));

    const matchedDef =
      options.allowSleepover === false
        ? matchingDefs.find((d) => d.type !== 'SLEEPOVER') || matchingDefs[0]
        : matchingDefs.find((d) => d.type === 'SLEEPOVER') || matchingDefs[0];

    console.log(`[SEGMENT ${i}] FINAL MATCH: ${matchedDef?.type || 'NONE'}, rate: ${matchedDef?.fullTimeRate || 'N/A'}`);

    result.push({ start: segStart, end: segEnd, matchedDefinition: matchedDef });
  }
  
  console.log(`[SEGMENTATION COMPLETE] Total segments: ${result.length}, Timezone: ${timezone}`);
  result.forEach((seg, i) => {
    console.log(`  [FINAL SEG ${i}] ${seg.start.toISOString()} - ${seg.end.toISOString()} → ${seg.matchedDefinition?.type || 'NONE'}`);
  });

  return result;
}

/**
 * Build complete shift segments with all business rules applied
 */
export function buildShiftSegments(
  start: Date,
  end: Date,
  tenantConfig: TenantConfig,
  options: { forceSleepover?: boolean; allowSleepover?: boolean } = {}
): ShiftSegmentationResult {
  // If not explicitly disabled, allow sleepover definitions to participate in splitting
  const allowSleepover = options.allowSleepover !== false;
  const forceSleepover = options.forceSleepover === true;
  const originalStart = new Date(start);
  const originalEnd = new Date(end);
  const { holidays, shiftDefinitions } = tenantConfig;

  const isSleepoverEnabled = tenantConfig.sleepoverConfiguration?.enabled !== false;
  let activeDefinitions = shiftDefinitions;

  // When forceSleepover is true, ensure sleepover is enabled and included
  if ((!isSleepoverEnabled || !allowSleepover) && !forceSleepover) {
    activeDefinitions = shiftDefinitions.filter((def) => def.type !== 'SLEEPOVER');
  }

  // Fallback sleepover definition when user forces sleepover but config lacks one
  const hasSleepoverDef = activeDefinitions.some((d) => d.type === 'SLEEPOVER');
  if (forceSleepover && !hasSleepoverDef) {
    activeDefinitions = [
      ...activeDefinitions,
      {
        type: 'SLEEPOVER',
        startTime: '22:00',
        endTime: '06:00',
        casualRate: null,
        fullTimeRate: null,
        partTimeRate: null,
      } as unknown as ShiftDefinition,
    ];
  }

  // CORE: Perform time-based splitting
  const splitSegments = splitByShiftDefinition(start, end, activeDefinitions, {
    allowSleepover: allowSleepover || forceSleepover,
    timezone: tenantConfig.timezone,
  });

  // BUILD: Create full segment objects
  const fullSegments: ShiftSegment[] = splitSegments.map((seg) => {
    const calendarDayType = resolveCalendarDayType(seg.start, holidays, tenantConfig.timezone);
    const currentType = seg.matchedDefinition?.type;

    // Overnight metadata based on NIGHT definition
    const nightDef = activeDefinitions.find((def) => def.type === 'NIGHT');
    let isOvernight = false;
    if (nightDef && nightDef.startTime && nightDef.endTime) {
      const nightStartHour = extractHourFromTimeString(nightDef.startTime);
      const nightEndHour = extractHourFromTimeString(nightDef.endTime);
      const startHour = seg.start.getUTCHours();
      isOvernight =
        startHour >= nightStartHour ||
        startHour < nightEndHour + (nightDef.endTime.includes(':59') ? 1 : 0);
    }

    // For sleepover segments, store the full definition end time
    let sleepoverDefinitionEnd: Date | undefined;
    if (currentType === 'SLEEPOVER' && seg.matchedDefinition?.endTime) {
      const [endHour, endMin] = seg.matchedDefinition.endTime.split(':').map(Number);
      sleepoverDefinitionEnd = new Date(seg.start);
      sleepoverDefinitionEnd.setUTCHours(endHour, endMin, 0, 0);

      // If sleepover crosses midnight, add a day
      const segStartHour = seg.start.getUTCHours();
      if (endHour < segStartHour) {
        sleepoverDefinitionEnd.setUTCDate(sleepoverDefinitionEnd.getUTCDate() + 1);
      }
    }

    return {
      id: randomUUID(),
      start: seg.start,
      end: seg.end,
      durationMinutes: calculateSegmentDuration({ start: seg.start, end: seg.end }),
      dayOfWeek: seg.start.getUTCDay(),
      calendarDayType,
      shiftType: currentType,
      isOvernight,
      isSleepover: currentType === 'SLEEPOVER',
      originalShiftStart: originalStart,
      originalShiftEnd: originalEnd,
      sleepoverDefinitionEnd,
    };
  });

  // RULE 1: Apply Minimum Engagement (2-hour rounding)
  // New Logic: Sum work across all segments to avoid unnecessary gaps in split shifts
  // a shift split by a sleepover is treated as a single engagement for min-engagement purposes.
  const hasSleepover = fullSegments.some((s) => s.isSleepover);

  const totalWorkDurationMinutes = fullSegments
    .filter((s) => !s.isSleepover && s.shiftType !== 'PAID_GAP_TIME')
    .reduce((sum, s) => sum + s.durationMinutes, 0);

  // When a shift includes a sleepover segment, skip adding paid gap time altogether.
  const totalGapNeeded = hasSleepover
    ? 0
    : calculateMinimumEngagementGap(totalWorkDurationMinutes, tenantConfig);
  let remainingGapMinutes = totalGapNeeded;

  const finalSegments: ShiftSegment[] = [];
  const engagementGroups: ShiftSegment[][] = [];
  let currentGroup: ShiftSegment[] = [];

  fullSegments.forEach((seg) => {
    if (seg.isSleepover) {
      if (currentGroup.length > 0) engagementGroups.push(currentGroup);
      engagementGroups.push([seg]);
      currentGroup = [];
    } else {
      currentGroup.push(seg);
    }
  });
  if (currentGroup.length > 0) engagementGroups.push(currentGroup);

  engagementGroups.forEach((group, idx) => {
    if (group.length === 1 && group[0].isSleepover) {
      finalSegments.push(...group);
      return;
    }

    finalSegments.push(...group);

    // Apply gap only to the last work group of the shift
    const isLastWorkGroup = !engagementGroups.slice(idx + 1).some((g) => !g[0].isSleepover);

    if (isLastWorkGroup && remainingGapMinutes > 0) {
      // If this work block immediately follows a sleepover block in the same shift,
      // treat it as a continuation and do not add paid gap time (Step 2 rule).
      const previousGroup = idx > 0 ? engagementGroups[idx - 1] : undefined;
      const followsSleepover = previousGroup?.length === 1 && previousGroup[0].isSleepover;

      if (!followsSleepover) {
        const lastSegment = group[group.length - 1];
        const gapStart = new Date(lastSegment.end);
        const gapEnd = new Date(gapStart.getTime() + remainingGapMinutes * 60 * 1000);

        finalSegments.push({
          id: randomUUID(),
          start: gapStart,
          end: gapEnd,
          durationMinutes: remainingGapMinutes,
          dayOfWeek: gapStart.getDay(),
          calendarDayType: resolveCalendarDayType(gapStart, holidays, tenantConfig.timezone),
          shiftType: 'PAID_GAP_TIME',
          isOvernight: lastSegment.isOvernight,
          isSleepover: false,
          isGap: true,
          originalShiftStart: originalStart,
          originalShiftEnd: originalEnd,
        });
        remainingGapMinutes = 0;
      }
    }
  });

  return {
    segments: finalSegments,
    totalDurationMinutes: finalSegments.reduce((sum, s) => sum + s.durationMinutes, 0),
    crossesMidnight: crossesMidnight(start, finalSegments[finalSegments.length - 1].end),
    spansDays: new Set(finalSegments.map((seg) => seg.start.toDateString())).size,
  };
}

# --- FILE: service/payroll/shiftTypeResolution.service.ts ---
import { randomUUID } from 'crypto';
import { ShiftDefinition } from '@/types/shiftDefinition.types';
import { ShiftSegment, TenantConfig, ShiftType } from '@/types/payroll.types';
import { isPublicHoliday, isSaturday, isSunday, resolveCalendarDayType } from '@/util/calendar/calendarUtils';
import { parseTimeToMinutes } from '@/service/payroll/core/timeUtils';
import { applyEveningTriggerRule } from '@/service/payroll/rules/eveningTrigger.rule';
import { mergeSegments } from '@/service/payroll/rules/segmentMerging.rule';

/**
 * Calculate total work hours in a 24-hour window from a given start time
 */
function calculateHoursIn24HourWindow(segments: ShiftSegment[], windowStart: Date): number {
  const windowEnd = new Date(windowStart.getTime() + 24 * 60 * 60 * 1000); // 24 hours later

  return segments
    .filter((seg) => !seg.isSleepover) // Exclude sleepover segments
    .reduce((total, seg) => {
      // Calculate overlap between segment and 24-hour window
      const segStart = Math.max(seg.start.getTime(), windowStart.getTime());
      const segEnd = Math.min(seg.end.getTime(), windowEnd.getTime());

      if (segStart < segEnd) {
        return total + (segEnd - segStart) / (1000 * 60 * 60); // Convert to hours
      }
      return total;
    }, 0);
}

export function resolveShiftType(
  segment: ShiftSegment,
  tenantConfig: TenantConfig,
  options: {
    totalHoursWorked?: number;
    overtimeThreshold: number;
    forceOvertime?: boolean;
    forceType?: ShiftType;
    employmentType: 'casual' | 'fullTime' | 'partTime';
    isRemote?: boolean;
  }
): ShiftType {
  const { forceOvertime, forceType, employmentType, isRemote } = options;
  const { holidays, sleepoverConfiguration, shiftDefinitions } = tenantConfig;
  const timezone = tenantConfig.timezone;
  const isSleepoverEnabled = sleepoverConfiguration?.enabled !== false;

  const isHoliday = isPublicHoliday(segment.start, holidays, timezone);
  const isSun = isSunday(segment.start, timezone);
  const isSat = isSaturday(segment.start, timezone);
  const isSleepover =
    isSleepoverEnabled && (segment.isSleepover || segment.shiftType === 'SLEEPOVER');

  console.log(`[RESOLVE TYPE] Segment: ${segment.start.toISOString()}, incoming shiftType: ${segment.shiftType}, isHoliday: ${isHoliday}`);

  // 1. Public Holiday (Step 4: Highest Rate Wins - No ordinary loadings)
  if (isHoliday) {
    console.log(`[RESOLVE TYPE] Returning PUBLIC_HOLIDAY`);
    return 'PUBLIC_HOLIDAY';
  }

  // 2. Weekends (Step 4: Highest Rate Wins - No ordinary loadings)
  // If periodic/daily overtime is forced, compare rates — overtime overrides weekend only when its rate is strictly higher.
  if (isSun || isSat) {
    const calendarType: ShiftType = isSun ? 'SUNDAY' : 'SATURDAY';
    if (forceType === 'OVERTIME' || forceType === 'OVERTIME_L2') {
      try {
        const calendarMultiplier = getShiftTypeMultiplier(calendarType, shiftDefinitions, employmentType, isRemote);
        const overtimeMultiplier = getShiftTypeMultiplier(forceType, shiftDefinitions, employmentType, isRemote);
        if (overtimeMultiplier >= calendarMultiplier) {
          console.log(`[RESOLVE TYPE] ${forceType} (${overtimeMultiplier}x) overrides ${calendarType} (${calendarMultiplier}x)`);
          return forceType;
        }
      } catch {
        // Rate lookup failed — fall back to calendar type
      }
    }
    return calendarType;
  }

  // 3. Sleepover (Step 2)
  if (isSleepover) return 'SLEEPOVER';

  // 4. Forced Type (Step 7/9/10 overrides)
  if (forceType) return forceType;

  // 5. Existing Segment Type (from robust segmentation)
  if (segment.shiftType && segment.shiftType !== 'SLEEPOVER' && segment.shiftType !== 'OVERTIME') {
    console.log(`[RESOLVE TYPE] Using segment type: ${segment.shiftType}`);
    return segment.shiftType;
  }

  // 6. Time-based matching from Database (Fallback) - Includes Morning Reset (06:00)
  // Use local timezone hours so IST-defined shift windows match correctly
  let segmentStartMinutes: number;
  if (timezone) {
    const localH = parseInt(segment.start.toLocaleString('en-US', { timeZone: timezone, hour: 'numeric', hour12: false }));
    const localM = parseInt(segment.start.toLocaleString('en-US', { timeZone: timezone, minute: 'numeric' }));
    segmentStartMinutes = localH * 60 + localM;
  } else {
    segmentStartMinutes = segment.start.getUTCHours() * 60 + segment.start.getUTCMinutes();
  }
  const sortedDefs = [...shiftDefinitions].sort((a, b) => {
    // Priority: Night > Afternoon > Day
    const priority = { NIGHT: 3, AFTERNOON: 2, DAY: 1 };
    return (
      (priority[b.type as keyof typeof priority] || 0) -
      (priority[a.type as keyof typeof priority] || 0)
    );
  });

  const matchedDef = sortedDefs.find((def) => {
    if (!def.startTime || !def.endTime) return false;
    const dStart = Math.round(parseTimeToMinutes(def.startTime));
    const dEnd = Math.round(parseTimeToMinutes(def.endTime));

    if (dEnd < dStart) {
      // Overnight
      return segmentStartMinutes >= dStart || segmentStartMinutes < dEnd;
    }
    return segmentStartMinutes >= dStart && segmentStartMinutes < dEnd;
  });

  const naturalType = isHoliday
    ? 'PUBLIC_HOLIDAY'
    : isSun
      ? 'SUNDAY'
      : isSat
        ? 'SATURDAY'
        : isSleepover
          ? 'SLEEPOVER'
          : matchedDef?.type || 'DAY';

  // RULE: If break violation, return max(naturalType multiplier, OVERTIME multiplier)
  if (forceOvertime) {
    try {
      const naturalMultiplier = getShiftTypeMultiplier(
        naturalType,
        shiftDefinitions,
        employmentType,
        isRemote
      );
      const overtimeMultiplier = getShiftTypeMultiplier(
        'OVERTIME',
        shiftDefinitions,
        employmentType,
        isRemote
      );

      if (overtimeMultiplier > naturalMultiplier) {
        return 'OVERTIME';
      }
    } catch {
      // Fallback if rates missing
      return naturalType === 'DAY' ? 'OVERTIME' : naturalType;
    }
  }

  // Enhanced rule: For overtime segments, apply higher rate between daily and weekly overtime
  if (forceType === 'OVERTIME' || forceType === 'OVERTIME_L2') {
    try {
      // In this implementation, daily and weekly overtime use the same base rates
      // The tiered structure (OVERTIME vs OVERTIME_L2) handles the different rates:
      // - OVERTIME: 1.5x (first 2 hours)
      // - OVERTIME_L2: 2.0x (after 2 hours)
      // This ensures the higher rate is always applied
      return forceType;
    } catch {
      return forceType || naturalType;
    }
  }

  return naturalType;
}

/**
 * Orchestrate type resolution for all segments including business rules
 */
export function resolveAllSegmentTypes(
  segments: ShiftSegment[],
  tenantConfig: TenantConfig,
  options: {
    dailyOvertimeThreshold: number;
    periodicOvertimeThreshold: number;
    prevShiftEnd?: Date;
    firstShiftStartOfDay?: Date;
    priorDailyHours?: number;
    priorPeriodicHours?: number;
    periodicThresholdReason?: string; // e.g. "Weekly", "Fortnightly", "Monthly"
    employmentType?: 'casual' | 'fullTime' | 'partTime';
    isRemote?: boolean;
  }
): ShiftSegment[] {
  const {
    dailyOvertimeThreshold,
    periodicOvertimeThreshold,
    prevShiftEnd,
    priorDailyHours = 0,
    priorPeriodicHours = 0,
    periodicThresholdReason = 'Weekly',
    employmentType = 'casual',
    isRemote,
  } = options;

  // If a first shift start is provided (from history), use it. Otherwise, use current shift start.
  // Ensure segments are sorted by start time to guarantee correct anchoring
  const sortedSegments = [...segments].sort((a, b) => a.start.getTime() - b.start.getTime());

  // Anchor for span rule: first NON-sleepover segment start (so sleepover hours don't count toward span)
  let spanAnchor: number | undefined;
  let sleepoverGapHours = 0;

  let cumulativeHours = priorDailyHours;
  let forceOvertime = false;

  // RULE: Step 7: Break Safety (from DB MIN_BREAK_BETWEEN_SHIFTS)
  const breakSafetyRule = tenantConfig.rules.find((r) => r.type === 'MIN_BREAK_BETWEEN_SHIFTS');
  const minBreakThreshold = breakSafetyRule?.value;

  // Check if this is the first shift of the day by comparing with firstShiftStartOfDay
  const isFirstShiftOfDay = options.firstShiftStartOfDay &&
    sortedSegments.length > 0 &&
    Math.abs(sortedSegments[0].start.getTime() - options.firstShiftStartOfDay.getTime()) < 60000; // Within 1 minute

  if (
    minBreakThreshold != null &&
    prevShiftEnd &&
    !isNaN(prevShiftEnd.getTime()) &&
    sortedSegments.length > 0 &&
    isFirstShiftOfDay
  ) {
    const breakHours = (sortedSegments[0].start.getTime() - prevShiftEnd.getTime()) / 3600000;
    if (breakHours < Number(minBreakThreshold)) {
      forceOvertime = true;
    }
  }

  // RULE Values for Step 8 and 9 (from DB: OVERTIME_AFTER_HOURS, MAX_WEEKLY_HOURS)
  const spanThreshold = 12;
  const dailyWorkThreshold =
    dailyOvertimeThreshold != null ? Number(dailyOvertimeThreshold) : undefined;
  const dailyL2Threshold =
    dailyWorkThreshold != null ? dailyWorkThreshold + 2 : undefined;
  const periodicWorkThreshold =
    periodicOvertimeThreshold != null ? Number(periodicOvertimeThreshold) : undefined;
  const periodicOvertimeBlock = 2; // SCHADS L2 threshold typically occurs after 2 hours of L1 overtime
  const periodicL2Threshold = periodicWorkThreshold != null ? periodicWorkThreshold + periodicOvertimeBlock : undefined;

  // CORE: Map initial types and apply Step 8/9/10
  // Note: We cannot use .map() because a single segment might need to be split into multiple
  // if it crosses a threshold (e.g. 10th hour of work).
  const resolvedSegments: ShiftSegment[] = [];

  for (const segment of sortedSegments) {
    if (segment.isSleepover) {
      // Sleepovers don't count towards work hours or span; accumulate their duration as gap
      sleepoverGapHours += segment.durationMinutes / 60;
      resolvedSegments.push({ ...segment, shiftType: 'SLEEPOVER' });
      continue;
    }

    if (spanAnchor === undefined) {
      spanAnchor = segment.start.getTime();
    }

    const segDurationHours = segment.durationMinutes / 60;

    // Check if this segment crosses any threshold:
    // 1. Daily Work Threshold (e.g. 10h)
    // 1b. Daily Work L2 Threshold (e.g. 12h)
    // 2. Weekly Work Threshold (e.g. 38h)
    // 2b. Weekly Work L2 Threshold (e.g. 40h)
    // 3. Span Threshold (12h from first start)

    // We will process the segment in chunks if needed.
    // Potential cut points (relative to segment start):
    const cutPoints: number[] = [];

    // A. Daily Work Cut (from DB OVERTIME_AFTER_HOURS)
    if (dailyWorkThreshold != null) {
      const timeToDailyLimit = dailyWorkThreshold - cumulativeHours;
      if (timeToDailyLimit > 0 && timeToDailyLimit < segDurationHours) {
        cutPoints.push(timeToDailyLimit);
      }
    }

    // A2. Daily Work L2 Cut (daily + 2h)
    if (dailyL2Threshold != null) {
      const timeToDailyL2Limit = dailyL2Threshold - cumulativeHours;
      if (timeToDailyL2Limit > 0 && timeToDailyL2Limit < segDurationHours) {
        cutPoints.push(timeToDailyL2Limit);
      }
    }

    // B. Periodic Work Cut (e.g. Weekly/Fortnightly/Monthly)
    if (periodicWorkThreshold != null) {
      const timeToPeriodicLimit = periodicWorkThreshold - (priorPeriodicHours + (cumulativeHours - priorDailyHours));
      if (timeToPeriodicLimit > 0 && timeToPeriodicLimit < segDurationHours) {
        cutPoints.push(timeToPeriodicLimit);
      }
    }

    // B2. Periodic Work L2 Cut (Periodic + 2h/3h block)
    if (periodicL2Threshold != null) {
      const timeToPeriodicL2Limit = periodicL2Threshold - (priorPeriodicHours + (cumulativeHours - priorDailyHours));
      if (timeToPeriodicL2Limit > 0 && timeToPeriodicL2Limit < segDurationHours) {
        cutPoints.push(timeToPeriodicL2Limit);
      }
    }

    // C. Span Work Cut
    // Span based on working span (exclude sleepover gaps)
    const segStartSpan =
      spanAnchor != null ? (segment.start.getTime() - spanAnchor) / 3600000 - sleepoverGapHours : 0;
    const timeToSpanLimit = spanThreshold - segStartSpan;
    if (timeToSpanLimit > 0 && timeToSpanLimit < segDurationHours) {
      cutPoints.push(timeToSpanLimit);
    }

    // Sort valid unique cut points associated with this segment
    const uniqueCuts = [...new Set(cutPoints)].sort((a, b) => a - b);

    let currentSegOffset = 0;

    // Process pieces (including the final piece after last cut)
    const piecesOffsets = [...uniqueCuts, segDurationHours];

    for (const endOffset of piecesOffsets) {
      const pieceDuration = endOffset - currentSegOffset;
      if (pieceDuration <= 0.0001) continue; // Skip tiny fragments

      const pieceStart = new Date(segment.start.getTime() + currentSegOffset * 3600000);
      const pieceEnd = new Date(segment.start.getTime() + endOffset * 3600000);

      // Determine status for this piece
      // Check limits based on the MIDPOINT of the piece (or start)
      // Actually, we know the piece is bounded by thresholds.
      // So we just check the state at the start of the piece.

      const pieceSpanStart =
        spanAnchor != null ? (pieceStart.getTime() - spanAnchor) / 3600000 - sleepoverGapHours : 0;

      // Enhanced daily overtime detection: Check if > daily thresholds in 24-hour window
      // Use the start of the first non-sleepover segment as the window anchor
      const windowAnchor = spanAnchor ? new Date(spanAnchor) : pieceStart;
      const hoursIn24HourWindow =
        calculateHoursIn24HourWindow(
          resolvedSegments.filter((s) => s.start.getTime() <= pieceStart.getTime()), // Only include previous segments
          windowAnchor
        ) + pieceDuration; // Include current piece

      const isDailyOvertime =
        dailyWorkThreshold != null &&
        (cumulativeHours >= dailyWorkThreshold || hoursIn24HourWindow > dailyWorkThreshold);
      const isDailyOvertimeL2 =
        dailyL2Threshold != null &&
        (cumulativeHours >= dailyL2Threshold || hoursIn24HourWindow > dailyL2Threshold);
      const isPeriodicOvertime =
        periodicWorkThreshold != null && (priorPeriodicHours + (cumulativeHours - priorDailyHours)) >= periodicWorkThreshold;
      const isPeriodicOvertimeL2 =
        periodicL2Threshold != null && (priorPeriodicHours + (cumulativeHours - priorDailyHours)) >= periodicL2Threshold;
      const isSpanViolation = pieceSpanStart >= spanThreshold; // (Use >= to be safe)

      let resolvedType: ShiftType | undefined;
      let overtimeReason: string | undefined;

      if (forceOvertime || isSpanViolation || isDailyOvertime || isPeriodicOvertime) {
        // Determine overtime priority and reason
        if (isSpanViolation) {
          overtimeReason = `Span Violation (<${minBreakThreshold ?? 'min'}h break)`;
        } else if (isDailyOvertimeL2 || isPeriodicOvertimeL2) {
          overtimeReason = isDailyOvertimeL2 ? `Daily Overtime L2 (>${dailyL2Threshold}h in window)` : `${periodicThresholdReason} Overtime L2 (>${periodicL2Threshold}h in period)`;
        } else if (isDailyOvertime && isPeriodicOvertime) {
          overtimeReason = `Both Daily & ${periodicThresholdReason} Overtime (higher rate applied)`;
        } else if (isDailyOvertime) {
          overtimeReason = `Daily Overtime (>${dailyWorkThreshold ?? 'threshold'}h in 24h window)`;
        } else if (isPeriodicOvertime) {
          overtimeReason = `${periodicThresholdReason} Overtime (>${periodicWorkThreshold ?? 'threshold'}h in period)`;
        } else {
          overtimeReason = 'Forced Overtime';
        }

        // Tiering rules:
        // - L2 when either daily or periodic L2 threshold is exceeded
        const pieceStartsInL2 = isDailyOvertimeL2 || isPeriodicOvertimeL2;

        if (pieceStartsInL2) {
          resolvedType = 'OVERTIME_L2';
        } else {
          resolvedType = 'OVERTIME';
        }
      }

      const baseType = resolveShiftType(
        {
          ...segment,
          start: pieceStart,
          end: pieceEnd,
          durationMinutes: pieceDuration * 60,
        },
        tenantConfig,
        {
          totalHoursWorked: cumulativeHours,
          overtimeThreshold: periodicOvertimeThreshold,
          forceType: resolvedType,
          employmentType,
          isRemote,
        }
      );

      resolvedSegments.push({
        ...segment,
        id: randomUUID(),
        start: pieceStart,
        end: pieceEnd,
        durationMinutes: pieceDuration * 60,
        shiftType: baseType,
        calendarDayType: resolveCalendarDayType(pieceStart, tenantConfig.holidays, tenantConfig.timezone),
        overtimeReason,
      });

      cumulativeHours += pieceDuration;
      currentSegOffset = endOffset;
    }
  }

  // RULE: Apply Evening Trigger (8 PM look-back)
  const upgradedSegments = applyEveningTriggerRule(resolvedSegments, tenantConfig);

  // RULE: Consolidate segments
  return mergeSegments(upgradedSegments);
}

/**
 * Multiplier resolution
 */
export function getShiftTypeMultiplier(
  shiftType: ShiftType,
  shiftDefinitions: ShiftDefinition[],
  employmentType: 'casual' | 'fullTime' | 'partTime',
  isRemote?: boolean
): number {
  const normalizedEmploymentType = employmentType.toLowerCase() as
    | 'casual'
    | 'fullTime'
    | 'partTime';

  if (shiftType === 'PAID_GAP_TIME') {
    const dayDef = shiftDefinitions.find((d) => d.type === 'DAY');
    if (dayDef)
      return normalizedEmploymentType === 'casual'
        ? isRemote
          ? (dayDef.remoteCasualRate ?? dayDef.casualRate ?? 1.25)
          : (dayDef.casualRate ?? 1.25)
        : normalizedEmploymentType === 'fullTime'
          ? isRemote
            ? (dayDef.remoteFullTimeRate ?? dayDef.fullTimeRate ?? 1.0)
            : (dayDef.fullTimeRate ?? 1.0)
          : isRemote
            ? (dayDef.remotePartTimeRate ?? dayDef.partTimeRate ?? 1.0)
            : (dayDef.partTimeRate ?? 1.0);
  }

  const def = shiftDefinitions.find((d) => (d.type || '').toUpperCase().trim() === shiftType);

  const rate =
    def &&
    (normalizedEmploymentType === 'casual'
      ? isRemote
        ? (def.remoteCasualRate ?? def.casualRate)
        : def.casualRate
      : normalizedEmploymentType === 'fullTime'
        ? isRemote
          ? (def.remoteFullTimeRate ?? def.fullTimeRate)
          : def.fullTimeRate
        : isRemote
          ? (def.remotePartTimeRate ?? def.partTimeRate)
          : def.partTimeRate);

  if (rate != null) return rate;

  // Fallback to standard SCHADS multipliers if DB config is missing
  const fallbacks: Record<ShiftType, { casual: number; perm: number }> = {
    DAY: { casual: 1.25, perm: 1.0 },
    AFTERNOON: { casual: 1.375, perm: 1.125 },
    NIGHT: { casual: 1.4, perm: 1.15 },
    SATURDAY: { casual: 1.75, perm: 1.5 },
    SUNDAY: { casual: 2.25, perm: 2.0 },
    PUBLIC_HOLIDAY: { casual: 2.75, perm: 2.5 },
    OVERTIME: { casual: 1.75, perm: 1.5 },
    OVERTIME_L2: { casual: 2.25, perm: 2.0 },
    PAID_GAP_TIME: { casual: 1.25, perm: 1.0 },
    SLEEPOVER: { casual: 1.4, perm: 1.15 }, // Fallback to Night rate if SLEEPOVER def missing
  };

  const fallback = fallbacks[shiftType];
  if (fallback) {
    return normalizedEmploymentType === 'casual' ? fallback.casual : fallback.perm;
  }

  throw new Error(`Missing ${employmentType} rate for ${shiftType} and no fallback available`);
}

# --- FILE: service/payroll/payCalculation.service.ts ---
import { AllowanceType } from '@prisma/client';
import { ShiftDefinition } from '@/types/shiftDefinition.types';
import { ShiftSegment, TenantConfig, SegmentPay, ShiftPayResult } from '@/types/payroll.types';
import { getShiftTypeMultiplier } from '@/service/payroll/shiftTypeResolution.service';

/**
 * Fixed sleepover payment amount when conditions are met (fallback)
 */
const SLEEPOVER_FLAT_RATE_DEFAULT = 60.02;

const roundCurrency = (value: number): number => Math.round((value + Number.EPSILON) * 100) / 100;

function resolveSleepoverFlatRate(tenantConfig: TenantConfig): number {
  const fromAllowance = tenantConfig.allowances?.find((a) => a.type === AllowanceType.SLEEPOVER);
  return fromAllowance?.rate ?? SLEEPOVER_FLAT_RATE_DEFAULT;
}

/**
 * Identify sleepover segment and its prefix/suffix segments
 */
export function identifySleepoverSegments(segments: ShiftSegment[]): {
  sleepoverSegments: ShiftSegment[];
  prefixSegments: ShiftSegment[];
  suffixSegments: ShiftSegment[];
} {
  const sorted = [...segments].sort((a, b) => a.start.getTime() - b.start.getTime());

  const sleepoverSegments = sorted.filter((seg) => seg.isSleepover);

  if (!sleepoverSegments.length) {
    return { sleepoverSegments: [], prefixSegments: [], suffixSegments: [] };
  }

  const firstSleepover = sleepoverSegments[0];
  const lastSleepover = sleepoverSegments[sleepoverSegments.length - 1];

  const prefixSegments = sorted.filter(
    (seg) => !seg.isSleepover && seg.end.getTime() <= firstSleepover.start.getTime()
  );

  const suffixSegments = sorted.filter(
    (seg) => !seg.isSleepover && seg.start.getTime() >= lastSleepover.end.getTime()
  );

  return { sleepoverSegments, prefixSegments, suffixSegments };
}

/**
 * Calculate total hours from segments
 */
function calculateTotalHours(segments: ShiftSegment[]): number {
  return segments.reduce((total, seg) => total + seg.durationMinutes / 60, 0);
}

/**
 * Check if sleepover qualifies for flat rate payment
 */
export function qualifiesForSleepoverFlatRate(
  segments: ShiftSegment[],
  shiftPhysicalEnd?: Date
): boolean {
  const { sleepoverSegments, prefixSegments, suffixSegments } = identifySleepoverSegments(segments);

  if (!sleepoverSegments.length) return false;

  const prefixHours = calculateTotalHours(prefixSegments);
  const suffixHours = calculateTotalHours(suffixSegments);

  if (prefixHours < 4 && suffixHours < 4) return false;

  const lastSleepover = sleepoverSegments[sleepoverSegments.length - 1];

  // Use the sleepover definition end time if available, otherwise fall back to segment end
  const requiredEndTime =
    lastSleepover.sleepoverDefinitionEnd?.getTime() ?? lastSleepover.end.getTime();

  const physicalEndTime =
    shiftPhysicalEnd?.getTime() ??
    lastSleepover.originalShiftEnd?.getTime() ??
    lastSleepover.end.getTime();

  return physicalEndTime >= requiredEndTime;
}

/**
 * Calculate pay for a single segment
 */
export function calculateSegmentPay(
  segment: ShiftSegment,
  baseRate: number,
  shiftDefinitions: ShiftDefinition[],
  employmentType: 'casual' | 'fullTime' | 'partTime',
  isRemote?: boolean,
  overridePay?: number
): SegmentPay {
  const shiftType = segment.shiftType || 'DAY';

  if (overridePay !== undefined) {
    return {
      segment,
      shiftType,
      rate: 0,
      pay: overridePay,
    };
  }

  const multiplier = getShiftTypeMultiplier(shiftType, shiftDefinitions, employmentType, isRemote);

  const hours = segment.durationMinutes / 60;
  const pay = roundCurrency(hours * baseRate * multiplier);

  return { segment, shiftType, rate: multiplier, pay };
}

/**
 * Calculate pay for all segments with sleepover logic
 */
export function calculateShiftPay(
  segments: ShiftSegment[],
  baseRate: number,
  tenantConfig: TenantConfig,
  employmentType: 'casual' | 'fullTime' | 'partTime',
  isRemote?: boolean
): ShiftPayResult {
  // ✅ FIX 1: ALWAYS SORT SEGMENTS
  const sortedSegments = [...segments].sort((a, b) => a.start.getTime() - b.start.getTime());

  const { shiftDefinitions } = tenantConfig;
  const segmentPayments: SegmentPay[] = [];
  let sleepoverFlatRateApplied = false;

  const { sleepoverSegments, prefixSegments, suffixSegments } =
    identifySleepoverSegments(sortedSegments);

  const hasSleepover = sleepoverSegments.length > 0;
  const isSleepoverEnabled = tenantConfig.sleepoverConfiguration?.enabled !== false;

  // ✅ FIX 2: PASS PHYSICAL SHIFT END
  const shiftPhysicalEnd =
    sortedSegments[sortedSegments.length - 1]?.originalShiftEnd ??
    sortedSegments[sortedSegments.length - 1]?.end;

  const usesFlatRate =
    hasSleepover &&
    isSleepoverEnabled &&
    qualifiesForSleepoverFlatRate(sortedSegments, shiftPhysicalEnd);

  const sleepoverFlatRate = resolveSleepoverFlatRate(tenantConfig);

  if (hasSleepover && isSleepoverEnabled && !usesFlatRate) {
    for (const segment of prefixSegments) {
      segmentPayments.push(
        calculateSegmentPay(segment, baseRate, shiftDefinitions, employmentType, isRemote)
      );
    }

    for (const segment of sleepoverSegments) {
      segmentPayments.push(
        calculateSegmentPay(segment, baseRate, shiftDefinitions, employmentType, isRemote, 0)
      );
    }

    for (const segment of suffixSegments) {
      segmentPayments.push(
        calculateSegmentPay(segment, baseRate, shiftDefinitions, employmentType, isRemote)
      );
    }
  } else if (usesFlatRate) {
    sleepoverFlatRateApplied = true;

    for (const segment of prefixSegments) {
      segmentPayments.push(
        calculateSegmentPay(segment, baseRate, shiftDefinitions, employmentType, isRemote)
      );
    }

    // ✅ FIX 3: APPLY FLAT RATE ONCE
    const firstSleepover = sleepoverSegments[0];

    segmentPayments.push(
      calculateSegmentPay(
        firstSleepover,
        baseRate,
        shiftDefinitions,
        employmentType,
        isRemote,
        sleepoverFlatRate
      )
    );

    for (const segment of sleepoverSegments.slice(1)) {
      segmentPayments.push(
        calculateSegmentPay(segment, baseRate, shiftDefinitions, employmentType, isRemote, 0)
      );
    }

    for (const segment of suffixSegments) {
      segmentPayments.push(
        calculateSegmentPay(segment, baseRate, shiftDefinitions, employmentType, isRemote)
      );
    }
  } else {
    for (const segment of sortedSegments) {
      segmentPayments.push(
        calculateSegmentPay(segment, baseRate, shiftDefinitions, employmentType, isRemote)
      );
    }
  }

  const totalPay = roundCurrency(segmentPayments.reduce((sum, p) => sum + p.pay, 0));
  const overtimePay = roundCurrency(
    segmentPayments
      .filter((p) => p.shiftType === 'OVERTIME' || p.shiftType === 'OVERTIME_L2')
      .reduce((sum, p) => sum + p.pay, 0)
  );
  const basePay = roundCurrency(totalPay - overtimePay);

  // ✅ FIX 4: PAID MINUTES BASED ON ALL PAID SEGMENTS (including overtime)
  const totalPaidMinutes = segmentPayments
    .filter((p) => p.pay > 0)
    .reduce((sum, p) => sum + p.segment.durationMinutes, 0);

  return {
    segmentPayments,
    summary: {
      basePay,
      overtimePay,
      allowances: 0,
      totalPay,
      totalPaidMinutes,
    },
    sleepoverFlatRateApplied,
  };
}

/**
 * Get detailed breakdown of sleepover calculation
 */
export function getSleepoverBreakdown(segments: ShiftSegment[]) {
  const sorted = [...segments].sort((a, b) => a.start.getTime() - b.start.getTime());

  const { sleepoverSegments, prefixSegments, suffixSegments } = identifySleepoverSegments(sorted);

  if (!sleepoverSegments.length) {
    return {
      hasSleepover: false,
      sleepoverHours: 0,
      prefixHours: 0,
      suffixHours: 0,
      qualifiesForFlatRate: false,
    };
  }

  const prefixHours = calculateTotalHours(prefixSegments);
  const suffixHours = calculateTotalHours(suffixSegments);

  return {
    hasSleepover: true,
    sleepoverHours: calculateTotalHours(sleepoverSegments),
    prefixHours,
    suffixHours,
    qualifiesForFlatRate:
      (prefixHours >= 4 || suffixHours >= 4) && qualifiesForSleepoverFlatRate(sorted),
  };
}

# --- FILE: util/weeklyOvertime.util.ts ---
import { prisma } from '@/prisma';

/**
 * Calculate weekly overtime data including rates from database
 */
export async function calculateWeeklyOvertimeData(
  tenantId: string,
  employmentType: string,
  totalWeeklyHours: number,
  weeklyThreshold?: number,
  _isRemote?: boolean,
  year?: number
) {
  // Get weekly overtime threshold from database if not provided
  let threshold = weeklyThreshold;
  if (threshold == null) {
    const ruleYear = year ?? new Date().getFullYear();
    const weeklyRule = await prisma.rule.findFirst({
      where: { tenantId, year: ruleYear, type: 'MAX_WEEKLY_HOURS', deletedAt: null },
    });
    threshold = weeklyRule?.value ?? 38;
  }

  // Apply weekly overtime formula: split into L1 and L2 blocks
  let weeklyNormalHours = totalWeeklyHours;
  let weeklyOvertimeL1Hours = 0;
  let weeklyOvertimeL2Hours = 0;

  if (threshold != null && totalWeeklyHours > threshold) {
    const totalOT = totalWeeklyHours - threshold;
    const l1Block = 2; // Always 2 hours for SCHADS Home Care / Disability

    weeklyOvertimeL1Hours = Math.min(totalOT, l1Block);
    weeklyOvertimeL2Hours = Math.max(0, totalOT - l1Block);
    weeklyNormalHours = threshold;
  }

  // Multipliers based on award
  const isCasual = employmentType.toLowerCase().includes('casual');
  const l1Multiplier = isCasual ? 1.75 : 1.5;
  const l2Multiplier = isCasual ? 2.25 : 2.0;

  return {
    weeklyNormalHours,
    weeklyOvertimeL1Hours,
    weeklyOvertimeL2Hours,
    weeklyOvertimeHours: weeklyOvertimeL1Hours + weeklyOvertimeL2Hours,
    weeklyOvertimeMultiplier: l1Multiplier,
    weeklyOvertimeL2Multiplier: l2Multiplier,
    weeklyThreshold: threshold,
  };
}

/**
 * Calculate weekly overtime pay using effective base rate
 */
export function calculateWeeklyOvertimePay(
  weeklyNormalHours: number,
  weeklyOvertimeL1Hours: number,
  weeklyOvertimeL2Hours: number,
  effectiveBaseRate: number,
  casualFullTimeMultiplier: number,
  l1Multiplier: number,
  l2Multiplier: number
) {
  const weeklyNormalPay = weeklyNormalHours * effectiveBaseRate * casualFullTimeMultiplier;
  const weeklyOvertimeL1Pay = weeklyOvertimeL1Hours * effectiveBaseRate * l1Multiplier;
  const weeklyOvertimeL2Pay = weeklyOvertimeL2Hours * effectiveBaseRate * l2Multiplier;

  return {
    weeklyNormalPay,
    weeklyOvertimePay: weeklyOvertimeL1Pay + weeklyOvertimeL2Pay,
    weeklyOvertimeL1Pay,
    weeklyOvertimeL2Pay,
    totalPay: weeklyNormalPay + weeklyOvertimeL1Pay + weeklyOvertimeL2Pay,
  };
}

/**
 * Get effective base rate from API or shift definitions
 */
export async function getEffectiveBaseRate(
  tenantId: string,
  employmentType: string,
  baseRateFromApi?: string | number,
  shifts?: any[],
  isRemote?: boolean
) {
  // Determine base rate
  const rawBaseRate = baseRateFromApi
    ? Number(baseRateFromApi)
    : shifts && shifts.length > 0 && shifts[0].baseRate
      ? Number(shifts[0].baseRate)
      : 30;

  // Get the multiplier for DAY shift
  let multiplier = 1.0;
  try {
    const multiplierQuery = await prisma.$queryRaw<any[]>`
      SELECT 
        CASE 
          WHEN ${Boolean(isRemote)} AND ${employmentType} = 'FULL_TIME' THEN COALESCE(remote_full_time_rate, full_time_rate)::numeric
          WHEN ${Boolean(isRemote)} AND ${employmentType} = 'PART_TIME' THEN COALESCE(remote_part_time_rate, part_time_rate)::numeric
          WHEN ${Boolean(isRemote)} AND ${employmentType} = 'CASUAL' THEN COALESCE(remote_casual_rate, casual_rate)::numeric
          WHEN NOT ${Boolean(isRemote)} AND ${employmentType} = 'FULL_TIME' THEN full_time_rate::numeric
          WHEN NOT ${Boolean(isRemote)} AND ${employmentType} = 'PART_TIME' THEN part_time_rate::numeric
          WHEN NOT ${Boolean(isRemote)} AND ${employmentType} = 'CASUAL' THEN casual_rate::numeric
          ELSE 1.0
        END as multiplier
      FROM pricing.shift_definitions 
      WHERE type = 'DAY' AND tenant_id = ${tenantId} AND deleted_at IS NULL
      LIMIT 1
    `;

    if (multiplierQuery && Array.isArray(multiplierQuery) && multiplierQuery.length > 0) {
      multiplier = Number(multiplierQuery[0].multiplier) || 1.0;
    }
  } catch (error) {
    console.log('Using default multiplier');
  }

  return {
    rawBaseRate,
    effectiveBaseRate: rawBaseRate * multiplier,
    dayShiftMultiplier: multiplier,
    baseRateFromApi: baseRateFromApi ? Number(baseRateFromApi) : null,
  };
}

/**
 * Calculate fortnightly overtime data
 */
export async function calculateFortnightlyOvertimeData(
  tenantId: string,
  employmentType: string,
  totalFortnightlyHours: number,
  fortnightlyThreshold?: number,
  _isRemote?: boolean,
  year?: number
) {
  let threshold = fortnightlyThreshold;
  if (threshold == null) {
    const ruleYear = year ?? new Date().getFullYear();
    const fortnightlyRule = await prisma.rule.findFirst({
      where: { tenantId, year: ruleYear, type: 'MAX_FORTNIGHT_HOURS', deletedAt: null },
    });
    threshold = fortnightlyRule?.value ?? 76;
  }

  let fortnightlyNormalHours = totalFortnightlyHours;
  let fortnightlyOvertimeL1Hours = 0;
  let fortnightlyOvertimeL2Hours = 0;

  if (threshold != null && totalFortnightlyHours > threshold) {
    const totalOT = totalFortnightlyHours - threshold;
    const l1Block = 2;

    fortnightlyOvertimeL1Hours = Math.min(totalOT, l1Block);
    fortnightlyOvertimeL2Hours = Math.max(0, totalOT - l1Block);
    fortnightlyNormalHours = threshold;
  }

  const isCasual = employmentType.toLowerCase().includes('casual');
  const l1Multiplier = isCasual ? 1.75 : 1.5;
  const l2Multiplier = isCasual ? 2.25 : 2.0;

  return {
    fortnightlyNormalHours,
    fortnightlyOvertimeL1Hours,
    fortnightlyOvertimeL2Hours,
    fortnightlyOvertimeHours: fortnightlyOvertimeL1Hours + fortnightlyOvertimeL2Hours,
    fortnightlyOvertimeMultiplier: l1Multiplier,
    fortnightlyOvertimeL2Multiplier: l2Multiplier,
    fortnightlyThreshold: threshold,
  };
}

/**
 * Calculate fortnightly overtime pay
 */
export function calculateFortnightlyOvertimePay(
  fortnightlyNormalHours: number,
  fortnightlyOvertimeL1Hours: number,
  fortnightlyOvertimeL2Hours: number,
  effectiveBaseRate: number,
  casualFullTimeMultiplier: number,
  l1Multiplier: number,
  l2Multiplier: number
) {
  const fortnightlyNormalPay = fortnightlyNormalHours * effectiveBaseRate * casualFullTimeMultiplier;
  const fortnightlyOvertimeL1Pay = fortnightlyOvertimeL1Hours * effectiveBaseRate * l1Multiplier;
  const fortnightlyOvertimeL2Pay = fortnightlyOvertimeL2Hours * effectiveBaseRate * l2Multiplier;

  return {
    fortnightlyNormalPay,
    fortnightlyOvertimePay: fortnightlyOvertimeL1Pay + fortnightlyOvertimeL2Pay,
    fortnightlyOvertimeL1Pay,
    fortnightlyOvertimeL2Pay,
    totalPay: fortnightlyNormalPay + fortnightlyOvertimeL1Pay + fortnightlyOvertimeL2Pay,
  };
}

/**
 * Calculate monthly overtime data
 */
export async function calculateMonthlyOvertimeData(
  tenantId: string,
  employmentType: string,
  totalMonthlyHours: number,
  monthlyThreshold?: number,
  _isRemote?: boolean,
  year?: number
) {
  let threshold = monthlyThreshold;
  if (threshold == null) {
    const ruleYear = year ?? new Date().getFullYear();
    const monthlyRule = await prisma.rule.findFirst({
      where: { tenantId, year: ruleYear, type: 'MAX_MONTHLY_HOURS' },
    });
    threshold = monthlyRule?.value ?? 152;
  }

  let monthlyNormalHours = totalMonthlyHours;
  let monthlyOvertimeL1Hours = 0;
  let monthlyOvertimeL2Hours = 0;

  if (threshold != null && totalMonthlyHours > threshold) {
    const totalOT = totalMonthlyHours - threshold;
    const l1Block = 2;

    monthlyOvertimeL1Hours = Math.min(totalOT, l1Block);
    monthlyOvertimeL2Hours = Math.max(0, totalOT - l1Block);
    monthlyNormalHours = threshold;
  }

  const isCasual = employmentType.toLowerCase().includes('casual');
  const l1Multiplier = isCasual ? 1.75 : 1.5;
  const l2Multiplier = isCasual ? 2.25 : 2.0;

  return {
    monthlyNormalHours,
    monthlyOvertimeL1Hours,
    monthlyOvertimeL2Hours,
    monthlyOvertimeHours: monthlyOvertimeL1Hours + monthlyOvertimeL2Hours,
    monthlyOvertimeMultiplier: l1Multiplier,
    monthlyOvertimeL2Multiplier: l2Multiplier,
    monthlyThreshold: threshold,
  };
}

/**
 * Calculate monthly overtime pay
 */
export function calculateMonthlyOvertimePay(
  monthlyNormalHours: number,
  monthlyOvertimeL1Hours: number,
  monthlyOvertimeL2Hours: number,
  effectiveBaseRate: number,
  casualFullTimeMultiplier: number,
  l1Multiplier: number,
  l2Multiplier: number
) {
  const monthlyNormalPay = monthlyNormalHours * effectiveBaseRate * casualFullTimeMultiplier;
  const monthlyOvertimeL1Pay = monthlyOvertimeL1Hours * effectiveBaseRate * l1Multiplier;
  const monthlyOvertimeL2Pay = monthlyOvertimeL2Hours * effectiveBaseRate * l2Multiplier;

  return {
    monthlyNormalPay,
    monthlyOvertimePay: monthlyOvertimeL1Pay + monthlyOvertimeL2Pay,
    monthlyOvertimeL1Pay,
    monthlyOvertimeL2Pay,
    totalPay: monthlyNormalPay + monthlyOvertimeL1Pay + monthlyOvertimeL2Pay,
  };
}

# --- FILE: service/payroll/allowanceCalculation.service.ts ---
import { ShiftSegment, TenantConfig, AllowanceCalculation } from '@/types/payroll.types';

const roundCurrency = (value: number): number => Math.round((value + Number.EPSILON) * 100) / 100;

// Define available allowance types for API configuration
export const AVAILABLE_ALLOWANCE_TYPES = {
  MEAL: 'MEAL',
  LAUNDRY: 'LAUNDRY',
  UNIFORM: 'UNIFORM',
  KM_TRAVEL: 'KM_TRAVEL',
  SLEEPOVER: 'SLEEPOVER',
  BROKENSHIFT_1: 'BROKENSHIFT_1',
  BROKENSHIFT_2: 'BROKENSHIFT_2',
} as const;

export type AllowanceConfigType = keyof typeof AVAILABLE_ALLOWANCE_TYPES;

export function calculateAllowances(
  segments: ShiftSegment[],
  tenantConfig: TenantConfig,
  options: {
    kmTravelled?: number;
    overtimeHours?: number;
    isSleepover?: boolean;
    weeklyAllowanceTotals: {
      LAUNDRY: number;
      UNIFORM: number;
    };
    enabledAllowances?: AllowanceConfigType[];
  }
): AllowanceCalculation[] {
  const results: AllowanceCalculation[] = [];
  const { allowances } = tenantConfig;

  // If no enabled allowances specified, enable all by default (backward compatibility)
  const enabledAllowances =
    options.enabledAllowances || (Object.keys(AVAILABLE_ALLOWANCE_TYPES) as AllowanceConfigType[]);

  // Helper function to check if allowance type is enabled
  const isAllowanceEnabled = (type: AllowanceConfigType): boolean => {
    return enabledAllowances.includes(type);
  };

  /* ---------------- LAUNDRY ---------------- */
  if (isAllowanceEnabled('LAUNDRY')) {
    const laundryDef = allowances.find((a) => a.type === 'LAUNDRY');

    if (laundryDef?.rate && laundryDef?.maxPerWeek) {
      const remaining = roundCurrency(
        laundryDef.maxPerWeek - options.weeklyAllowanceTotals.LAUNDRY
      );

      const amount = roundCurrency(Math.max(0, Math.min(laundryDef.rate, remaining)));
      // console.log(amount, ' remaining laundry allowance');
      results.push({
        type: 'LAUNDRY',
        amount,
        isEligible: amount > 0,
        reason: amount === 0 ? 'Weekly maximum reached' : 'Per shift allowance',
      });
    }
  }

  /* ---------------- UNIFORM ---------------- */
  if (isAllowanceEnabled('UNIFORM')) {
    const uniformDef = allowances.find((a) => a.type === 'UNIFORM');

    if (uniformDef?.rate && uniformDef?.maxPerWeek) {
      const remaining = roundCurrency(
        uniformDef.maxPerWeek - options.weeklyAllowanceTotals.UNIFORM
      );

      const amount = roundCurrency(Math.max(0, Math.min(uniformDef.rate, remaining)));
      // console.log(amount, ' remaining uniform allowance');

      results.push({
        type: 'UNIFORM',
        amount,
        isEligible: amount > 0,
        reason: amount === 0 ? 'Weekly maximum reached' : 'Per shift allowance',
      });
    }
  }

  /* ---------------- MEAL ---------------- */
  if (isAllowanceEnabled('MEAL')) {
    const totalMinutes = segments
      .filter((s) => !s.isSleepover)
      .reduce((sum, s) => sum + s.durationMinutes, 0);

    const mealDef = allowances.find((a) => a.type === 'MEAL');

    if (mealDef?.rate && (totalMinutes > 300 || (options.overtimeHours ?? 0) > 2)) {
      results.push({
        type: 'MEAL',
        amount: roundCurrency(mealDef.rate),
        isEligible: true,
        reason: totalMinutes > 300 ? 'Shift > 5 hours' : 'Overtime > 2 hours',
      });
    }
  }

  /* ---------------- KM TRAVEL ---------------- */
  if (isAllowanceEnabled('KM_TRAVEL') && options.kmTravelled && options.kmTravelled > 0) {
    const travelDef = allowances.find((a) => a.type === 'KM_TRAVEL');

    if (travelDef?.rate) {
      results.push({
        type: 'KM_TRAVEL',
        amount: roundCurrency(options.kmTravelled * travelDef.rate),
        isEligible: true,
        reason: `${options.kmTravelled} KM travelled`,
      });
    }
  }

  /* ---------------- SLEEPOVER ---------------- */
  const hasSleepoverSegment = segments.some((s) => s.isSleepover);
  if (isAllowanceEnabled('SLEEPOVER') && (options.isSleepover || hasSleepoverSegment)) {
    const sleepoverDef = allowances.find((a) => a.type === 'SLEEPOVER');

    if (sleepoverDef?.rate) {
      results.push({
        type: 'SLEEPOVER',
        amount: roundCurrency(sleepoverDef.rate),
        isEligible: true,
        reason: 'Sleepover shift allowance',
      });
    }
  }

  return results;
}

# --- FILE: service/brokenShift.service.ts ---
import { prisma } from '@/prisma';

/**
 * Core broken-shift calculator
 * Sequence only (NO allowance decision here)
 */
export const calculateBrokenShiftSequence = (shiftCount: number) => {
  const shiftSequence: Array<{
    position: number;
    type: 'normal' | 'broken';
    shiftsBeforeCount: number;
  }> = [];

  for (let i = 1; i <= shiftCount; i++) {
    if (i === 2 || i === 3) {
      shiftSequence.push({
        position: i,
        type: 'broken',
        shiftsBeforeCount: i - 1,
      });
    } else {
      shiftSequence.push({
        position: i,
        type: 'normal',
        shiftsBeforeCount: i - 1,
      });
    }
  }

  const brokenShiftDetails = shiftSequence
    .filter(s => s.type === 'broken')
    .slice(0, 2)
    .map((s, index) => ({
      brokenShiftNumber: index + 1,
      position: s.position,
      shiftsBeforeCount: s.shiftsBeforeCount,
      allowanceType: index === 0 ? 'BROKENSHIFT_1' : 'BROKENSHIFT_2',
    }));

  return {
    shiftSequence,
    brokenShiftDetails,
    brokenShiftCount: brokenShiftDetails.length,
  };
};

/**
 * CRON – process broken shifts
 */
export const calculateAndProcessBrokenShifts = async (
  tenantId: string,
  year: number,
  referenceDate: Date = new Date()
): Promise<void> => {
  const startOfDay = new Date(Date.UTC(
    referenceDate.getUTCFullYear(),
    referenceDate.getUTCMonth(),
    referenceDate.getUTCDate()
  ));

  const endOfDay = new Date(startOfDay);
  endOfDay.setUTCDate(endOfDay.getUTCDate() + 1);

  const staffShifts = await prisma.shift.groupBy({
    by: ['staffId', 'staffName'],
    where: {
      tenantId,
      year,
      startTime: { lt: endOfDay },
      endTime: { gt: startOfDay },
    },
    _count: { id: true },
  });

  for (const staff of staffShifts) {
    const shiftCount = staff._count.id;

    const { brokenShiftCount } =
      calculateBrokenShiftSequence(shiftCount);

    if (brokenShiftCount === 0) continue;

    // allowance creation can go here if needed
  }
};

/**
 * Payroll / API – per staff per date
 */
export const calculateBrokenShiftsForStaffOnDate = async (
  tenantId: string,
  staffId: string,
  year: number,
  date: Date
): Promise<{
  shiftCount: number;
  brokenShiftCount: number;
  shiftSequence: Array<{ position: number; type: 'normal' | 'broken'; shiftsBeforeCount: number }>;
  brokenShiftDetails: Array<{
    brokenShiftNumber: number;
    position: number;
    shiftsBeforeCount: number;
    allowanceType: string;
    amount: number;
  }>;
  allowanceType: string | null;
  allowanceRate: number | null;
  totalAllowanceAmount: number | null;
}> => {
  const startOfDay = new Date(Date.UTC(
    date.getUTCFullYear(),
    date.getUTCMonth(),
    date.getUTCDate()
  ));

  const endOfDay = new Date(startOfDay);
  endOfDay.setUTCDate(endOfDay.getUTCDate() + 1);

  const shifts = await prisma.shift.findMany({
    where: {
      tenantId,
      year,
      staffId,
      startTime: { lt: endOfDay },
      endTime: { gt: startOfDay },
    },
    orderBy: { startTime: 'asc' },
  });

  const shiftCount = shifts.length;

  const {
    shiftSequence,
    brokenShiftDetails,
    brokenShiftCount,
  } = calculateBrokenShiftSequence(shiftCount);

  // Identify the position of the CURRENT shift (the one passed in as 'date')
  const currentShiftPosition = shifts.findIndex(s => s.startTime.getTime() === date.getTime()) + 1;

  let totalAllowanceAmount = 0;
  const enrichedDetails = [];

  for (const detail of brokenShiftDetails) {
    // Only apply the allowance if it matches the current shift position
    if (detail.position !== currentShiftPosition) continue;

    const allowance = await prisma.allowance.findFirst({
      where: { tenantId, year, type: detail.allowanceType as any },
    });
    const rate = allowance?.rate ?? 0;
    totalAllowanceAmount += rate;
    enrichedDetails.push({
      ...detail,
      amount: rate,
    });
  }

  return {
    shiftCount,
    brokenShiftCount,
    shiftSequence,
    brokenShiftDetails: enrichedDetails,
    allowanceType: null, // Deprecated in favor of details
    allowanceRate: null, // Deprecated in favor of details
    totalAllowanceAmount,
  };
};

/**
 * Queries
 */
export const getBrokenShiftsForStaff = async (
  tenantId: string,
  staffId: string,
  year: number,
  fromDate?: Date,
  toDate?: Date
) =>
  prisma.brokenShift.findMany({
    where: {
      tenantId,
      staffId,
      year,
      ...(fromDate && { date: { gte: fromDate } }),
      ...(toDate && { date: { lte: toDate } }),
    },
    orderBy: { date: 'asc' },
  });

export const getBrokenShiftsForTenant = async (
  tenantId: string,
  year: number,
  fromDate?: Date,
  toDate?: Date
) =>
  prisma.brokenShift.findMany({
    where: {
      tenantId,
      year,
      ...(fromDate && { date: { gte: fromDate } }),
      ...(toDate && { date: { lte: toDate } }),
    },
    orderBy: { date: 'asc' },
  });

export const getTotalBrokenShifts = async (
  tenantId: string,
  staffId: string,
  year: number,
  fromDate?: Date,
  toDate?: Date
): Promise<number> => {
  const records = await getBrokenShiftsForStaff(
    tenantId,
    staffId,
    year,
    fromDate,
    toDate
  );

  return records.reduce(
    (sum, r: any) => sum + r.brokenShiftCount,
    0
  );
};

# --- FILE: service/payroll/taxCalculation.service.ts ---
/**
 * @file taxCalculation.service.ts
 * @description Australian PAYG tax calculation service.
 */

import { calculateTax, PayFrequency, AtoBracket } from '@/util/payroll/taxCalculation.util';
import { prisma } from '@/prisma';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TaxCategory = 'WAGES' | 'ALLOWANCES' | 'REDUNDANCY' | 'GOVERNMENT';
export type TaxStatus = 'TAXABLE' | 'PARTIALLY_TAXABLE' | 'NON_TAXABLE';

/** Represents a single pay component with its full tax breakdown. */
export interface TaxLineItem {
  category: TaxCategory;
  /** Human-readable label, e.g. "Salary & Wages" or "Laundry Allowance". */
  label: string;
  /** Raw amount paid for this item in the period. */
  grossAmount: number;
  /** Portion that is exempt from withholding. */
  taxFreeAmount: number;
  /** Portion that is subject to PAYG withholding. */
  taxableAmount: number;
  /** Tax withheld attributable to this line item (apportioned from the bracket formula). */
  taxWithheld: number;
  taxStatus: TaxStatus;
  note: string;
}

/** Full result returned to the payout layer. */
export interface TaxCalculationResult {
  frequency: PayFrequency;
  lineItems: TaxLineItem[];
  /** Sum of all grossAmounts. */
  totalGross: number;
  /** Sum of all taxFreeAmounts. */
  totalTaxFree: number;
  /** Sum of all taxableAmounts. */
  totalTaxable: number;
  /** Total PAYG withholding (from the bracket formula). */
  totalTaxWithheld: number;
  /** Gross pay minus totalTaxWithheld. */
  netPay: number;
  /** ATO bracket used to arrive at the withholding amount. */
  bracket: AtoBracket;
}

// ---------------------------------------------------------------------------
// Input shape
// ---------------------------------------------------------------------------

/** Wages component input. */
export interface WagesInput {
  /** Salary, ordinary wages, commissions, bonuses. */
  salary?: number;
  /** Any overtime payment amounts. */
  overtime?: number;
}

/** Allowances component input. */
export interface AllowancesInput {
  /** Task / skill allowances (First Aid, Height, Lead Hand, etc.). */
  taskSkill?: number;
  /** Broken shift allowance. */
  brokenShift?: number;
  /** Laundry / approved uniform allowance paid this period. */
  laundry?: number;
  /**
   * Cents-per-km travel allowance.
   * Provide both totalAmount and kmsTravelled so the service can calculate
   * the tax-free portion correctly.
   */
  kmTravel?: { totalAmount: number; kmsTravelled: number };
  /**
   * Overtime meal allowance.
   * Provide amount and numberOfOccasions so the service can apply the
   * per-occasion limit ($35.65).
   */
  overtimeMeal?: { totalAmount: number; occasions: number };
  /**
   * Domestic travel allowance.
   * Provide amount and numberOfDays so the service can apply ATO daily limits.
   * atoReasonableDailyLimit defaults to $335 (2024–25 combined meal/incid.).
   */
  domesticTravel?: {
    totalAmount: number;
    days: number;
    atoReasonableDailyLimit?: number;
  };
}

/** Redundancy component input. */
export interface RedundancyInput {
  /** Genuine redundancy payment (whole amount; service will calculate the tax-free base limit). */
  genuineRedundancy?: { totalAmount: number; yearsOfService: number };
  /** Unused annual leave paid on redundancy. */
  unusedAnnualLeave?: number;
}

/** Government payment input. */
export interface GovernmentInput {
  /** Child support / maintenance received. */
  childSupport?: number;
  /** Family Tax Benefit (Part A or B). */
  familyTaxBenefit?: number;
  /** JobSeeker or Youth Allowance received. */
  jobSeeker?: number;
}

export interface TaxCalculationServiceInput {
  frequency: PayFrequency;
  wages?: WagesInput;
  allowances?: AllowancesInput;
  redundancy?: RedundancyInput;
  government?: GovernmentInput;
}

// ---------------------------------------------------------------------------
// Database fetch functions for tax constants
// ---------------------------------------------------------------------------

async function getTaxConstants(year: number, tenantId: string) {
  let taxItemRules = await prisma.taxItemRule.findMany({
    where: {
      financialYear: year,
      tenantId: tenantId,
    },
  });

  if (taxItemRules.length === 0) {
    // Fallback to the most recent year available for this tenant
    const fallbackYearRecord = await prisma.taxItemRule.findFirst({
      where: { tenantId: tenantId },
      orderBy: { financialYear: 'desc' },
    });
    if (fallbackYearRecord) {
      taxItemRules = await prisma.taxItemRule.findMany({
        where: {
          financialYear: fallbackYearRecord.financialYear,
          tenantId: tenantId,
        },
      });
    }
  }

  const rulesMap: Record<string, any> = {};
  const values: Record<string, number> = {};

  taxItemRules.forEach((rule) => {
    rulesMap[rule.itemKey] = rule;

    switch (rule.itemKey) {
      case 'LAUNDRY':
        values.LAUNDRY_TAX_FREE_ANNUAL_LIMIT = rule.taxFreeLimit || 150;
        break;
      case 'KM_TRAVEL':
        values.KM_RATE_TAX_FREE_PER_KM = rule.taxFreeRatePerUnit || 0.85;
        values.MAX_TAX_FREE_KM = rule.taxFreeMaxUnits || 5000;
        break;
      case 'OVERTIME_MEAL':
        values.MEAL_ALLOWANCE_REASONABLE_LIMIT = rule.taxFreeLimit || 35.65;
        break;
      case 'DOMESTIC_TRAVEL':
        values.DOMESTIC_TRAVEL_DEFAULT_DAILY_LIMIT = rule.taxFreeLimit || 335;
        break;
      case 'GENUINE_REDUNDANCY':
        values.REDUNDANCY_BASE = rule.redundancyBaseAmount || 12524;
        values.REDUNDANCY_PER_YEAR = rule.redundancyPerYearAmount || 6264;
        break;
      case 'UNUSED_ANNUAL_LEAVE':
        values.UNUSED_LEAVE_CONCESSIONAL_RATE = rule.flatTaxRate || 0.32;
        break;
      case 'ATO_CENTS_ADDITION':
        values.ATO_CENTS_ADDITION = rule.taxFreeLimit || 0.99;
        break;
      case 'FREQ_DIVISOR_FORTNIGHTLY':
        values.FREQ_DIVISOR_FORTNIGHTLY = rule.taxFreeLimit || 2;
        break;
      case 'FREQ_MULTIPLIER_FORTNIGHTLY':
        values.FREQ_MULTIPLIER_FORTNIGHTLY = rule.taxFreeLimit || 2;
        break;
      case 'FREQ_DIVISOR_MONTHLY':
        values.FREQ_DIVISOR_MONTHLY = rule.taxFreeLimit || 13 / 3;
        break;
      case 'FREQ_MULTIPLIER_MONTHLY':
        values.FREQ_MULTIPLIER_MONTHLY = rule.taxFreeLimit || 13 / 3;
        break;
    }
  });

  return {
    rules: rulesMap,
    values: {
      LAUNDRY_TAX_FREE_ANNUAL_LIMIT: values.LAUNDRY_TAX_FREE_ANNUAL_LIMIT || 150,
      KM_RATE_TAX_FREE_PER_KM: values.KM_RATE_TAX_FREE_PER_KM || 0.85,
      MAX_TAX_FREE_KM: values.MAX_TAX_FREE_KM || 5000,
      MEAL_ALLOWANCE_REASONABLE_LIMIT: values.MEAL_ALLOWANCE_REASONABLE_LIMIT || 35.65,
      DOMESTIC_TRAVEL_DEFAULT_DAILY_LIMIT: values.DOMESTIC_TRAVEL_DEFAULT_DAILY_LIMIT || 335,
      REDUNDANCY_BASE: values.REDUNDANCY_BASE || 12524,
      REDUNDANCY_PER_YEAR: values.REDUNDANCY_PER_YEAR || 6264,
      UNUSED_LEAVE_CONCESSIONAL_RATE: values.UNUSED_LEAVE_CONCESSIONAL_RATE || 0.32,
      ATO_CENTS_ADDITION: values.ATO_CENTS_ADDITION || 0.99,
      FREQ_DIVISOR_FORTNIGHTLY: values.FREQ_DIVISOR_FORTNIGHTLY || 2,
      FREQ_MULTIPLIER_FORTNIGHTLY: values.FREQ_MULTIPLIER_FORTNIGHTLY || 2,
      FREQ_DIVISOR_MONTHLY: values.FREQ_DIVISOR_MONTHLY || 13 / 3,
      FREQ_MULTIPLIER_MONTHLY: values.FREQ_MULTIPLIER_MONTHLY || 13 / 3,
    },
  };
}

async function getTaxBracketsFromDB(year: number, tenantId: string): Promise<AtoBracket[]> {
  let brackets = await prisma.taxBracket.findMany({
    where: {
      financialYear: year,
      tenantId: tenantId,
    },
    orderBy: { sortOrder: 'asc' },
  });

  if (brackets.length === 0) {
    // Fallback to the most recent year available for this tenant
    const fallbackYearRecord = await prisma.taxBracket.findFirst({
      where: { tenantId: tenantId },
      orderBy: { financialYear: 'desc' },
    });
    if (fallbackYearRecord) {
      brackets = await prisma.taxBracket.findMany({
        where: {
          financialYear: fallbackYearRecord.financialYear,
          tenantId: tenantId,
        },
        orderBy: { sortOrder: 'asc' },
      });
    } else {
      throw new Error(`No tax brackets found in DB for year ${year} and no fallback available.`);
    }
  }

  return brackets.map((bracket) => ({
    lessThan: bracket.weeklyLessThan,
    a: bracket.coefficientA,
    b: bracket.coefficientB,
  }));
}

// ---------------------------------------------------------------------------
// ATO constants (FY 2024–25)
// ---------------------------------------------------------------------------

// Tax constants should be fetched from database

const ROUND = (v: number) => Math.round((v + Number.EPSILON) * 100) / 100;

// ---------------------------------------------------------------------------
// Line-item builders
// ---------------------------------------------------------------------------

function buildWagesLineItems(wages: WagesInput, rules: Record<string, any>): TaxLineItem[] {
  const items: TaxLineItem[] = [];

  if (wages.salary && wages.salary > 0) {
    const rule = rules['SALARY'];
    items.push({
      category: 'WAGES',
      label: rule?.label || 'Salary, Wages, Commissions & Bonuses',
      grossAmount: ROUND(wages.salary),
      taxFreeAmount: 0,
      taxableAmount: ROUND(wages.salary),
      taxWithheld: 0, // apportioned later
      taxStatus: 'TAXABLE',
      note: rule?.note || 'Full PAYG withholding applies.',
    });
  }

  if (wages.overtime && wages.overtime > 0) {
    const rule = rules['OVERTIME'];
    items.push({
      category: 'WAGES',
      label: rule?.label || 'Overtime Payments',
      grossAmount: ROUND(wages.overtime),
      taxFreeAmount: 0,
      taxableAmount: ROUND(wages.overtime),
      taxWithheld: 0,
      taxStatus: 'TAXABLE',
      note: rule?.note || 'Taxed at marginal rate via PAYG withholding.',
    });
  }

  return items;
}

function buildAllowanceLineItems(
  allowances: AllowancesInput,
  constants: Awaited<ReturnType<typeof getTaxConstants>>
): TaxLineItem[] {
  const items: TaxLineItem[] = [];
  const { rules } = constants;

  // Task / Skill allowance
  if (allowances.taskSkill && allowances.taskSkill > 0) {
    const rule = rules['TASK_SKILL'];
    items.push({
      category: 'ALLOWANCES',
      label: rule?.label || 'Task / Skill Allowance',
      grossAmount: ROUND(allowances.taskSkill),
      taxFreeAmount: 0,
      taxableAmount: ROUND(allowances.taskSkill),
      taxWithheld: 0,
      taxStatus: 'TAXABLE',
      note: rule?.note || 'Fully taxable; reportable in STP Phase 2.',
    });
  }

  // Broken shift allowance
  if (allowances.brokenShift && allowances.brokenShift > 0) {
    const rule = rules['BROKEN_SHIFT'];
    items.push({
      category: 'ALLOWANCES',
      label: rule?.label || 'Broken Shift Allowance (Taxable)',
      grossAmount: ROUND(allowances.brokenShift),
      taxFreeAmount: 0,
      taxableAmount: ROUND(allowances.brokenShift),
      taxWithheld: 0,
      taxStatus: 'TAXABLE',
      note: rule?.note || 'Fully taxable; reported as task/skill allowance in STP Phase 2.',
    });
  }

  // Laundry allowance
  if (allowances.laundry && allowances.laundry > 0) {
    const rule = rules['LAUNDRY'];
    const taxFreeLimit = ROUND(constants.values.LAUNDRY_TAX_FREE_ANNUAL_LIMIT);
    const taxFree = ROUND(Math.min(allowances.laundry, taxFreeLimit));
    const taxable = ROUND(Math.max(0, allowances.laundry - taxFree));
    items.push({
      category: 'ALLOWANCES',
      label: rule?.label || 'Laundry / Approved Uniform Allowance',
      grossAmount: ROUND(allowances.laundry),
      taxFreeAmount: taxFree,
      taxableAmount: taxable,
      taxWithheld: 0,
      taxStatus: taxable > 0 ? 'PARTIALLY_TAXABLE' : 'NON_TAXABLE',
      note: rule?.note
        ? rule.note.replace('[taxable]', `$${taxable}`)
        : `Tax-free up to $${constants.values.LAUNDRY_TAX_FREE_ANNUAL_LIMIT} (claimable without receipts). Excess $${taxable} is taxable.`,
    });
  }

  // Cents-per-km travel
  if (allowances.kmTravel) {
    const rule = rules['KM_TRAVEL'];
    const { totalAmount, kmsTravelled } = allowances.kmTravel;
    const taxFreeKm = Math.min(kmsTravelled, constants.values.MAX_TAX_FREE_KM);
    const taxFreeAmount = ROUND(taxFreeKm * constants.values.KM_RATE_TAX_FREE_PER_KM);
    const taxable = ROUND(Math.max(0, totalAmount - taxFreeAmount));
    items.push({
      category: 'ALLOWANCES',
      label: rule?.label || 'Cents-per-KM Business Travel Allowance',
      grossAmount: ROUND(totalAmount),
      taxFreeAmount: ROUND(Math.min(totalAmount, taxFreeAmount)),
      taxableAmount: taxable,
      taxWithheld: 0,
      taxStatus: taxable > 0 ? 'PARTIALLY_TAXABLE' : 'NON_TAXABLE',
      note: rule?.note
        ? rule.note.replace('[taxable]', `$${taxable}`)
        : `Tax-free up to ${constants.values.MAX_TAX_FREE_KM} business km at ${constants.values.KM_RATE_TAX_FREE_PER_KM}/km. Taxable portion: $${taxable}.`,
    });
  }

  // Overtime meal allowance
  if (allowances.overtimeMeal) {
    const rule = rules['OVERTIME_MEAL'];
    const { totalAmount, occasions } = allowances.overtimeMeal;
    const taxFreeTotal = ROUND(occasions * constants.values.MEAL_ALLOWANCE_REASONABLE_LIMIT);
    const taxFree = ROUND(Math.min(totalAmount, taxFreeTotal));
    const taxable = ROUND(Math.max(0, totalAmount - taxFree));
    items.push({
      category: 'ALLOWANCES',
      label: rule?.label || 'Overtime Meal Allowance',
      grossAmount: ROUND(totalAmount),
      taxFreeAmount: taxFree,
      taxableAmount: taxable,
      taxWithheld: 0,
      taxStatus: taxable > 0 ? 'PARTIALLY_TAXABLE' : 'NON_TAXABLE',
      note: rule?.note
        ? rule.note.replace('[taxable]', `$${taxable}`)
        : `Tax-free within ATO reasonable limit of $${constants.values.MEAL_ALLOWANCE_REASONABLE_LIMIT}/occasion × ${occasions} occasion(s) = $${taxFree}. Excess $${taxable} is taxable.`,
    });
  }

  // Domestic travel allowance
  if (allowances.domesticTravel) {
    const rule = rules['DOMESTIC_TRAVEL'];
    const {
      totalAmount,
      days,
      atoReasonableDailyLimit = constants.values.DOMESTIC_TRAVEL_DEFAULT_DAILY_LIMIT,
    } = allowances.domesticTravel;
    const taxFreeTotal = ROUND(days * atoReasonableDailyLimit);
    const taxFree = ROUND(Math.min(totalAmount, taxFreeTotal));
    const taxable = ROUND(Math.max(0, totalAmount - taxFree));
    items.push({
      category: 'ALLOWANCES',
      label: rule?.label || 'Domestic Travel Allowance (Meals & Incidentals)',
      grossAmount: ROUND(totalAmount),
      taxFreeAmount: taxFree,
      taxableAmount: taxable,
      taxWithheld: 0,
      taxStatus: taxable > 0 ? 'PARTIALLY_TAXABLE' : 'NON_TAXABLE',
      note: rule?.note
        ? rule.note.replace('[taxable]', `$${taxable}`)
        : `Tax-free within ATO reasonable daily limit $${atoReasonableDailyLimit} × ${days} day(s) = $${taxFree}. Excess $${taxable} is taxable.`,
    });
  }

  return items;
}

function buildRedundancyLineItems(
  redundancy: RedundancyInput,
  constants: Awaited<ReturnType<typeof getTaxConstants>>
): TaxLineItem[] {
  const items: TaxLineItem[] = [];
  const { rules, values } = constants;

  // Genuine redundancy
  if (redundancy.genuineRedundancy) {
    const rule = rules['GENUINE_REDUNDANCY'];
    const { totalAmount, yearsOfService } = redundancy.genuineRedundancy;
    const taxFreeLimit = ROUND(
      values.REDUNDANCY_BASE + values.REDUNDANCY_PER_YEAR * yearsOfService
    );
    const taxFree = ROUND(Math.min(totalAmount, taxFreeLimit));
    const taxable = ROUND(Math.max(0, totalAmount - taxFree));
    items.push({
      category: 'REDUNDANCY',
      label: rule?.label || 'Genuine Redundancy Payment',
      grossAmount: ROUND(totalAmount),
      taxFreeAmount: taxFree,
      taxableAmount: taxable,
      taxWithheld: 0,
      taxStatus: taxable > 0 ? 'PARTIALLY_TAXABLE' : 'NON_TAXABLE',
      note: rule?.note
        ? rule.note
            .replace('$12,524', `$${values.REDUNDANCY_BASE.toLocaleString()}`)
            .replace('$6,264', `$${values.REDUNDANCY_PER_YEAR.toLocaleString()}`)
            .replace('[taxable]', `$${taxable.toLocaleString()}`)
        : `Tax-free limit: $${values.REDUNDANCY_BASE.toLocaleString()} + ($${values.REDUNDANCY_PER_YEAR.toLocaleString()} × ${yearsOfService} yrs) = $${taxFreeLimit.toLocaleString()}. Excess $${taxable.toLocaleString()} is taxable.`,
    });
  }

  // Unused annual leave on redundancy — flat 32% concessional rate
  if (redundancy.unusedAnnualLeave && redundancy.unusedAnnualLeave > 0) {
    const rule = rules['UNUSED_ANNUAL_LEAVE'];
    const amount = ROUND(redundancy.unusedAnnualLeave);
    // Tax is calculated at a flat concessional rate (not the bracket formula)
    const concessionalTax = ROUND(amount * values.UNUSED_LEAVE_CONCESSIONAL_RATE);
    items.push({
      category: 'REDUNDANCY',
      label: rule?.label || 'Unused Annual Leave (on Redundancy)',
      grossAmount: amount,
      taxFreeAmount: 0,
      taxableAmount: amount,
      // Store the concessional tax directly; will be separated from bracket tax in the result.
      taxWithheld: concessionalTax,
      taxStatus: 'TAXABLE',
      note: rule?.note
        ? rule.note
            .replace('32%', `${values.UNUSED_LEAVE_CONCESSIONAL_RATE * 100}%`)
            .replace('Tax:', `Tax: $${concessionalTax.toFixed(2)}`)
        : `Taxed at concessional flat rate of ${values.UNUSED_LEAVE_CONCESSIONAL_RATE * 100}%. Tax: $${concessionalTax.toFixed(2)}.`,
    });
  }

  return items;
}

function buildGovernmentLineItems(
  government: GovernmentInput,
  rules: Record<string, any>
): TaxLineItem[] {
  const items: TaxLineItem[] = [];

  if (government.childSupport && government.childSupport > 0) {
    const rule = rules['CHILD_SUPPORT'];
    items.push({
      category: 'GOVERNMENT',
      label: rule?.label || 'Child Support / Maintenance',
      grossAmount: ROUND(government.childSupport),
      taxFreeAmount: ROUND(government.childSupport),
      taxableAmount: 0,
      taxWithheld: 0,
      taxStatus: 'NON_TAXABLE',
      note: rule?.note || 'Not included in assessable income. No PAYG withholding.',
    });
  }

  if (government.familyTaxBenefit && government.familyTaxBenefit > 0) {
    const rule = rules['FAMILY_TAX_BENEFIT'];
    items.push({
      category: 'GOVERNMENT',
      label: rule?.label || 'Family Tax Benefit (Part A & B)',
      grossAmount: ROUND(government.familyTaxBenefit),
      taxFreeAmount: ROUND(government.familyTaxBenefit),
      taxableAmount: 0,
      taxWithheld: 0,
      taxStatus: 'NON_TAXABLE',
      note: rule?.note || 'Exempt income. No PAYG withholding.',
    });
  }

  if (government.jobSeeker && government.jobSeeker > 0) {
    const rule = rules['JOBSEEKER'];
    items.push({
      category: 'GOVERNMENT',
      label: rule?.label || 'JobSeeker / Youth Allowance',
      grossAmount: ROUND(government.jobSeeker),
      taxFreeAmount: 0,
      taxableAmount: ROUND(government.jobSeeker),
      taxWithheld: 0,
      taxStatus: 'TAXABLE',
      note:
        rule?.note ||
        'Taxable; included in assessable income. PAYG applies (may be offset by tax offsets).',
    });
  }

  return items;
}

// ---------------------------------------------------------------------------
// Main service function
// ---------------------------------------------------------------------------

/**
 * Calculate PAYG withholding for an entire pay period, returning a full
 * per-item breakdown plus the total tax withheld and net pay.
 *
 * ## How it works
 *
 * 1. Build `TaxLineItem[]` for each category (wages, allowances, redundancy, government).
 * 2. Separate items with a **flat concessional rate** (Unused Annual Leave on Redundancy)
 *    from those that go through the **ATO bracket formula**.
 * 3. Sum all bracket-formula taxable amounts and call `calculateTax()`.
 * 4. **Apportion** the bracket-formula tax across the contributing line items proportionally
 *    so the per-item `taxWithheld` figures add up correctly.
 * 5. Return `TaxCalculationResult` including netPay (grossPay − totalTaxWithheld).
 *
 * @example
 * ```ts
 * const result = calculateTax({ taxableGross: 1104.10, frequency: 'WEEKLY', brackets: [] });,
 *   wages: { salary: 920.00, overtime: 184.10 },
 * });
 * // result.totalTaxWithheld === 177
 * // result.netPay === 927.10
 * ```
 */
export async function calculatePayoutTax(
  input: TaxCalculationServiceInput & { year: number; tenantId: string }
): Promise<TaxCalculationResult> {
  const { frequency, wages, allowances, redundancy, government, year, tenantId } = input;

  // Fetch tax constants from database
  const constants = await getTaxConstants(year, tenantId);

  // 1. Build all line items
  const lineItems: TaxLineItem[] = [
    ...(wages ? buildWagesLineItems(wages, constants.rules) : []),
    ...(allowances ? buildAllowanceLineItems(allowances, constants) : []),
    ...(redundancy ? buildRedundancyLineItems(redundancy, constants) : []),
    ...(government ? buildGovernmentLineItems(government, constants.rules) : []),
  ];

  // 2. Separate concessional-rate items (already have taxWithheld set)
  const concessionalItems = lineItems.filter(
    (item) =>
      item.taxWithheld > 0 &&
      item.category === 'REDUNDANCY' &&
      item.label.includes('Unused Annual Leave')
  );
  const bracketItems = lineItems.filter((item) => !concessionalItems.includes(item));

  // 3. Sum taxable amounts that go through the bracket formula
  const totalBracketTaxable = ROUND(
    bracketItems.reduce((sum, item) => sum + item.taxableAmount, 0)
  );

  // 4. Calculate bracket-formula tax using database brackets
  const dbBrackets = await getTaxBracketsFromDB(year, tenantId);
  const { taxWithheld: bracketTax, bracket } =
    totalBracketTaxable > 0
      ? calculateTax({
          taxableGross: totalBracketTaxable,
          frequency,
          brackets: dbBrackets,
          constants: constants.values,
        })
      : { taxWithheld: 0, bracket: { lessThan: null as number | null, a: 0, b: 0 } };

  // 5. Calculate total concessional tax
  const concessionalTax = ROUND(concessionalItems.reduce((sum, item) => sum + item.taxWithheld, 0));

  // 6. Totals
  const totalGross = ROUND(lineItems.reduce((sum, item) => sum + item.grossAmount, 0));
  const totalTaxFree = ROUND(lineItems.reduce((sum, item) => sum + item.taxFreeAmount, 0));
  const totalTaxable = ROUND(lineItems.reduce((sum, item) => sum + item.taxableAmount, 0));
  const totalTaxWithheld = ROUND(bracketTax + concessionalTax);
  const netPay = ROUND(totalGross - totalTaxWithheld);

  return {
    frequency,
    lineItems,
    totalGross,
    totalTaxFree,
    totalTaxable,
    totalTaxWithheld,
    netPay,
    bracket,
  };
}

// ---------------------------------------------------------------------------
// Formatting helper — produces a human-readable breakdown for API responses
// ---------------------------------------------------------------------------

/**
 * Render a `TaxCalculationResult` as a structured summary object suitable
 * for inclusion in API responses or payslips.
 */
export function formatTaxBreakdown(result: TaxCalculationResult): {
  frequency: string;
  taxBracketUsed: string;
  itemBreakdown: Array<{
    category: string;
    item: string;
    gross: string;
    taxFree: string;
    taxable: string;
    status: string;
    note: string;
  }>;
  totals: {
    grossPay: string;
    totalTaxFree: string;
    totalTaxable: string;
    totalTaxWithheld: string;
    netPay: string;
  };
} {
  const fmt = (n: number) => `$${n.toFixed(2)}`;
  const { bracket } = result;

  const bracketLabel =
    bracket.lessThan !== null
      ? `< $${bracket.lessThan.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} (a=${bracket.a}, b=${bracket.b})`
      : `> $3,653.00 (a=${bracket.a}, b=${bracket.b})`;

  return {
    frequency: result.frequency,
    taxBracketUsed: bracketLabel,
    itemBreakdown: result.lineItems.map((item) => ({
      category: item.category,
      item: item.label,
      gross: fmt(item.grossAmount),
      taxFree: fmt(item.taxFreeAmount),
      taxable: fmt(item.taxableAmount),
      status: item.taxStatus,
      note: item.note,
    })),
    totals: {
      grossPay: fmt(result.totalGross),
      totalTaxFree: fmt(result.totalTaxFree),
      totalTaxable: fmt(result.totalTaxable),
      totalTaxWithheld: fmt(result.totalTaxWithheld),
      netPay: fmt(result.netPay),
    },
  };
}

# --- FILE: util/payroll/taxCalculation.util.ts ---
/**
 * @file taxCalculation.util.ts
 * @description Pure utility for Australian PAYG withholding calculation.
 *
 * Implements ATO Scale 2 (resident employee who has claimed the Tax-Free Threshold).
 *
 * Reference:
 *   - NAT 1008 – Statement of formulas for calculating amounts to be withheld
 *   - https://www.ato.gov.au/tax-rates-and-codes/tax-table-weekly-tax-table
 *
 * Frequency conversion rules (from ATO NAT 1008):
 *   Weekly    → x = floor(gross) + 0.99
 *   Fortnightly → x = floor(gross / 2) + 0.99 ; scale result × 2
 *   Monthly   → x = floor(gross × 3 / 13) + 0.99 (with ½c adjustment); scale result × 13/3
 */

export type PayFrequency = 'WEEKLY' | 'FORTNIGHTLY' | 'MONTHLY';

export interface AtoBracket {
  /** Upper bound (exclusive). null means "no upper bound". */
  lessThan: number | null;
  a: number;
  b: number;
}



// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Round a dollar value to the nearest whole dollar (ATO rounding rule).
 */
function roundToDollar(value: number): number {
  return Math.round(value + Number.EPSILON);
}

/**
 * Look up the ATO Scale 2 bracket for a given weekly earnings figure (x).
 * @param weeklyEarnings - Already adjusted x value (floor(gross) + 0.99, etc.)
 * @param brackets - Array of AtoBracket
 */
export function getAtoTaxBracket(weeklyEarnings: number, brackets: AtoBracket[]): AtoBracket {
  for (const bracket of brackets) {
    if (bracket.lessThan === null || weeklyEarnings < bracket.lessThan) {
      return bracket;
    }
  }
  // Fallback – should never reach here given the null-upper-bound bracket above
  return brackets[brackets.length - 1];
}

/**
 * Apply the ATO linear formula:  y = (a × x) − b
 * Returns the raw (unrounded) weekly withholding.
 */
export function applyAtoFormula(x: number, a: number, b: number): number {
  return a * x - b;
}



// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface TaxCalculationInput {
  /** Total taxable gross to be paid in this period (after removing tax-free amounts). */
  taxableGross: number;
  /** The pay cycle frequency. */
  frequency: PayFrequency;
}

export interface TaxCalculationOutput {
  /** Final PAYG withholding, rounded to nearest dollar. */
  taxWithheld: number;
  /** The ATO bracket that was used. */
  bracket: AtoBracket;
  /** The weekly-equivalent earnings figure (x) used in the formula. */
  weeklyEquivalentX: number;
}

/**
 * Calculate PAYG withholding for a given taxable gross amount and pay frequency.
 *
 * @example
 *   // Employee earns $1,104.10 weekly
 *   calculateTax({ taxableGross: 1104.10, frequency: 'WEEKLY' })
 *   // => { taxWithheld: 177, bracket: { lessThan: 1282, a: 0.3227, b: 180.0385 }, weeklyEquivalentX: 1104.99 }
 */
export function calculateTax(input: TaxCalculationInput & { brackets: AtoBracket[], constants: Record<string, number> }): TaxCalculationOutput {
  const { taxableGross, frequency, brackets, constants } = input;

  let weeklyEquivalentX: number;
  let multiplier: number;

  switch (frequency) {
    case 'WEEKLY': {
      const centsAddition = constants.ATO_CENTS_ADDITION ?? 0.99;
      weeklyEquivalentX = Math.floor(taxableGross) + centsAddition;
      multiplier = 1;
      break;
    }

    case 'FORTNIGHTLY': {
      const divisor = constants.FREQ_DIVISOR_FORTNIGHTLY ?? 2;
      const centsAddition = constants.ATO_CENTS_ADDITION ?? 0.99;
      const weeklyAvg = taxableGross / divisor;
      weeklyEquivalentX = Math.floor(weeklyAvg) + centsAddition;
      multiplier = constants.FREQ_MULTIPLIER_FORTNIGHTLY ?? 2;
      break;
    }

    case 'MONTHLY': {
      // NAT 1008: If monthly earnings end in 33 cents, add one cent before conversion.
      const adjustedGross = Math.abs((taxableGross % 1) - 0.33) < 0.001
        ? taxableGross + 0.01
        : taxableGross;

      // NAT 1008: x = floor(gross * 3 / 13) + 0.99
      const divisor = 13 / 3;
      const centsAddition = constants.ATO_CENTS_ADDITION ?? 0.99;
      const weeklyAvg = adjustedGross / divisor;
      weeklyEquivalentX = Math.floor(weeklyAvg) + centsAddition;
      multiplier = 13 / 3;
      break;
    }
  }

  const bracket = getAtoTaxBracket(weeklyEquivalentX, brackets);
  const rawWeeklyTax = Math.max(0, applyAtoFormula(weeklyEquivalentX, bracket.a, bracket.b));

  let taxWithheld: number;
  if (frequency === 'WEEKLY') {
    // NAT 1008: Round weekly withholding to nearest dollar.
    taxWithheld = roundToDollar(rawWeeklyTax);
  } else {
    // NAT 1008 intermediate step for periodic: truncate weekly tax to the dollar.
    const intermediateWeeklyTax = Math.floor(rawWeeklyTax);

    if (frequency === 'MONTHLY') {
      // NAT 1008: Round monthly withholding to nearest dollar.
      taxWithheld = roundToDollar(intermediateWeeklyTax * multiplier);
    } else {
      // FORTNIGHTLY: Ignore cents in the resulting amount (floor).
      taxWithheld = Math.floor(intermediateWeeklyTax * multiplier);
    }
  }

  return { taxWithheld, bracket, weeklyEquivalentX };
}


# --- FILE: service/payroll/tenantConfig.service.ts ---
import prisma from '@/prisma';
import { TenantConfig, HttpHeaders } from '@/types/payroll.types';
import { Rule, Allowance, Holiday, Shift } from '@prisma/client';
import { ShiftDefinition } from '@/types/shiftDefinition.types';

/**
 * Extract tenantId from request headers
 */
export function getTenantIdFromHeader(headers: HttpHeaders): string {
  const tenantId = headers['x-user-tenant-id'];
  if (!tenantId) {
    throw new Error('Tenant ID missing in headers');
  }
  return typeof tenantId === 'string' ? tenantId : tenantId[0];
}

/**
 * Load shift definitions using raw SQL since Prisma cannot handle the time type
 */
export async function loadShiftDefinitions(
  tenantId: string,
  year: number
): Promise<ShiftDefinition[]> {
  const rows = await prisma.$queryRaw<any[]>`
    SELECT 
      id,
      tenant_id as "tenantId",
      type,
      name,
      start_time::text as "startTime",
      end_time::text as "endTime",
      description,
      casual_rate as "casualRate",
      full_time_rate as "fullTimeRate",
      part_time_rate as "partTimeRate",
      remote_casual_rate as "remoteCasualRate",
      remote_full_time_rate as "remoteFullTimeRate",
      remote_part_time_rate as "remotePartTimeRate",
      created_at as "createdAt",
      updated_at as "updatedAt"
    FROM pricing.shift_definitions
    WHERE tenant_id = ${tenantId} AND year = ${year} AND deleted_at IS NULL
  `;
  return rows as ShiftDefinition[];
}

export async function loadRules(tenantId: string, year: number): Promise<Rule[]> {
  return prisma.rule.findMany({
    where: { tenantId, year, deletedAt: null },
  });
}

export async function loadAllowances(tenantId: string, year: number): Promise<Allowance[]> {
  return prisma.allowance.findMany({
    where: { tenantId, year, deletedAt: null },
  });
}

/**
 * Holidays are date-based, no calculation here
 * We expand the range to start of start day and end of end day
 * to ensure we capture holidays stored at midnight
 */
export async function loadHolidays(tenantId: string, start: Date, end: Date): Promise<Holiday[]> {
  // Get the start of the day for the start date
  const startOfDay = new Date(start);
  startOfDay.setUTCHours(0, 0, 0, 0);

  // Get the end of the day for the end date
  const endOfDay = new Date(end);
  endOfDay.setUTCHours(23, 59, 59, 999);

  return prisma.holiday.findMany({
    where: {
      OR: [{ tenantId }, { tenantId: 'default' }],
      date: {
        gte: startOfDay,
        lte: endOfDay,
      },
      deletedAt: null,
    },
  });
}

/**
 * Build full tenant config used by later stages
 */
export async function buildTenantConfig(
  tenantId: string,
  year: number,
  start: Date,
  end: Date,
  timezone?: string
): Promise<TenantConfig> {
  const [shiftDefinitions, rules, allowances, holidays] = await Promise.all([
    loadShiftDefinitions(tenantId, year),
    loadRules(tenantId, year),
    loadAllowances(tenantId, year),
    loadHolidays(tenantId, start, end),
  ]);

  // Auto-enable sleepover disturbance when a MIN_SLEEP_DISTURBANCE_HOURS rule is present
  const hasMinSleepDisturbanceRule = rules.some((r) => r.type === 'MIN_SLEEP_DISTURBANCE_HOURS');

  return {
    tenantId,
    shiftDefinitions,
    rules,
    allowances,
    holidays,
    sleepoverConfiguration: {
      enabled: true,
      enableDisturbance: hasMinSleepDisturbanceRule,
    },
    timezone: timezone || 'Asia/Kolkata',
  };
}

/**
 * Load the previous shift for a specific employee and tenant
 */
export async function buildPrevShiftConfig(
  tenantId: string,
  staffId: string,
  currentShiftStart: Date
): Promise<Shift | null> {
  return prisma.shift.findFirst({
    where: {
      tenantId,
      staffId,
      endTime: {
        lte: currentShiftStart,
      },
    },
    orderBy: {
      endTime: 'desc',
    },
    include: {
      segments: true,
    },
  });
}

# --- FILE: service/payroll/sleepDisturbance.service.ts ---
import { ShiftSegment, TenantConfig } from '@/types/payroll.types';
import { getShiftTypeMultiplier } from '@/service/payroll/shiftTypeResolution.service';
import { ShiftDefinition } from '@/types/shiftDefinition.types';

const roundCurrency = (value: number): number => Math.round((value + Number.EPSILON) * 100) / 100;

const getMinSleepDisturbanceMinutes = (tenantConfig?: TenantConfig): number => {
  const hoursRule = tenantConfig?.rules?.find((r) => r.type === 'MIN_SLEEP_DISTURBANCE_HOURS');
  const hours = typeof hoursRule?.value === 'number' ? hoursRule.value : 1; // default 1 hour
  return hours * 60;
};

/**
 * Input type for sleep disturbance timings
 */
export type SleepDisturbanceInput = {
  startTime: Date;
  endTime: Date;
  reason?: string;
};

/**
 * Record of a single sleep disturbance (raw data only)
 */
export type SleepDisturbanceRecord = {
  disturbanceId: string;
  startTime: Date;
  endTime: Date;
  rawDurationMinutes: number;
  reason?: string;
};

/**
 * Normalize sleep disturbance duration
 * If less than 1 hour, round to 1 hour
 * Otherwise, use the given duration
 */
export function normalizeSleepDisturbanceDuration(
  durationMinutes: number,
  tenantConfig?: TenantConfig
): {
  chargedMinutes: number;
  wasRoundedUp: boolean;
} {
  const minDuration = getMinSleepDisturbanceMinutes(tenantConfig);
  if (durationMinutes < minDuration) {
    return {
      chargedMinutes: minDuration,
      wasRoundedUp: true,
    };
  }

  return {
    chargedMinutes: durationMinutes,
    wasRoundedUp: false,
  };
}

/**
 * Create a record for a single sleep disturbance without converting to pay
 */
export function createSleepDisturbanceRecord(
  disturbanceInput: SleepDisturbanceInput,
  disturbanceId: string
): SleepDisturbanceRecord {
  // Calculate raw duration
  const rawDurationMinutes = Math.round(
    (disturbanceInput.endTime.getTime() - disturbanceInput.startTime.getTime()) / (1000 * 60)
  );

  return {
    disturbanceId,
    startTime: disturbanceInput.startTime,
    endTime: disturbanceInput.endTime,
    rawDurationMinutes,
    reason: disturbanceInput.reason,
  };
}

/**
 * Validate if sleep disturbances are within sleepover period
 */
export function validateDisturbancesInSleepoverPeriod(
  disturbances: SleepDisturbanceInput[],
  sleepoverSegments: ShiftSegment[]
): {
  valid: boolean;
  invalidDisturbances: SleepDisturbanceInput[];
  error?: string;
} {
  if (sleepoverSegments.length === 0) {
    return {
      valid: false,
      invalidDisturbances: disturbances,
      error: 'No sleepover period found. Sleep disturbances can only be recorded during sleepover.',
    };
  }

  const sleepoverStart = Math.min(...sleepoverSegments.map((s) => s.start.getTime()));
  const sleepoverEnd = Math.max(...sleepoverSegments.map((s) => s.end.getTime()));

  const invalidDisturbances = disturbances.filter((d) => {
    const distStart = d.startTime.getTime();
    const distEnd = d.endTime.getTime();

    // Check if disturbance is completely outside sleepover period
    return distEnd <= sleepoverStart || distStart >= sleepoverEnd;
  });

  if (invalidDisturbances.length > 0) {
    return {
      valid: false,
      invalidDisturbances,
      error: `${invalidDisturbances.length} disturbance(s) fall outside the sleepover period`,
    };
  }

  return {
    valid: true,
    invalidDisturbances: [],
  };
}

/**
 * Check if sleep disturbances are enabled
 */
export function isSleepDisturbanceEnabled(tenantConfig: TenantConfig): boolean {
  // Sleep disturbance only works if sleepover is enabled
  const sleepoverEnabled = tenantConfig.sleepoverConfiguration?.enabled === true;
  const disturbanceEnabled = tenantConfig.sleepoverConfiguration?.enableDisturbance === true;

  return sleepoverEnabled && disturbanceEnabled;
}

/**
 * Process all sleep disturbances for a shift
 * Aggregates all disturbance minutes first, then applies 1hr minimum rule
 */
export function processSleepDisturbances(
  disturbanceInputs: SleepDisturbanceInput[],
  baseRate: number,
  shiftDefinitions: ShiftDefinition[],
  employmentType: 'casual' | 'fullTime' | 'partTime',
  isRemote?: boolean,
  tenantConfig?: TenantConfig,
  sleepoverSegments?: ShiftSegment[]
): {
  disturbances: SleepDisturbanceRecord[];
  totalPay: number;
  totalChargedMinutes: number;
  totalRawMinutes: number;
  wasRoundedUp: boolean;
  errors?: string[];
} {
  // Check if sleep disturbance is enabled
  if (!tenantConfig || !isSleepDisturbanceEnabled(tenantConfig)) {
    return {
      disturbances: [],
      totalPay: 0,
      totalChargedMinutes: 0,
      totalRawMinutes: 0,
      wasRoundedUp: false,
      errors: [
        'Sleep disturbance is not enabled. Enable sleepover and disturbance features first.',
      ],
    };
  }

  // Validate disturbances are within sleepover period
  const validation = validateDisturbancesInSleepoverPeriod(
    disturbanceInputs,
    sleepoverSegments || []
  );
  if (!validation.valid) {
    return {
      disturbances: [],
      totalPay: 0,
      totalChargedMinutes: 0,
      totalRawMinutes: 0,
      wasRoundedUp: false,
      errors: [validation.error || 'Invalid disturbances'],
    };
  }

  // 1. Create records and calculate charged minutes (min 1 hour PER disturbance)
  const disturbances = disturbanceInputs.map((input, index) => {
    const disturbanceId = `DIST-${Date.now()}-${index}`;
    const record = createSleepDisturbanceRecord(input, disturbanceId);

    // Step 3: Minimum 1.0 hour per disturbance
    const { chargedMinutes, wasRoundedUp } = normalizeSleepDisturbanceDuration(
      record.rawDurationMinutes,
      tenantConfig
    );

    return {
      ...record,
      chargedMinutes,
      wasRoundedUp,
    };
  });

  const totalChargedMinutes = disturbances.reduce((sum, d) => sum + d.chargedMinutes, 0);
  const totalRawMinutes = disturbances.reduce((sum, d) => sum + d.rawDurationMinutes, 0);

  // 3. Calculate Pay based on charged duration
  const overtimeMultiplier = getShiftTypeMultiplier(
    'OVERTIME',
    shiftDefinitions,
    employmentType,
    isRemote
  );
  const rate = baseRate * overtimeMultiplier;
  const totalPay = roundCurrency((totalChargedMinutes / 60) * rate);

  return {
    disturbances,
    totalPay,
    totalChargedMinutes,
    totalRawMinutes,
    wasRoundedUp: disturbances.some((d) => d.wasRoundedUp),
  };
}

# --- FILE: service/weeklyHours.service.ts ---
import { prisma } from '@/prisma';
import {
  getWeekStart,
  getWeekEnd,
  getFortnightStart,
  getFortnightEnd,
  getMonthStart,
  getMonthEnd,
} from '@/util/week.util';
import { parseTimeToMinutes } from '@/service/payroll/core/timeUtils';
type Totals = {
  staffId: string;
  staffName: string;
  work: number;
  sleepover: number;
  disturbance: number;
};

export const getWeekBounds = async (
  tenantId: string,
  year: number,
  referenceDate: Date = new Date(),
  timezone?: string
): Promise<{ weekStart: Date; weekEnd: Date }> => {
  const startRule = await prisma.rule.findFirst({
    where: { tenantId, year, type: 'START_OF_WEEK', deletedAt: null },
  });
  const weekStart = getWeekStart(referenceDate, startRule?.value ?? 1, timezone);
  const weekEnd = getWeekEnd(weekStart);

  return { weekStart, weekEnd };
};

const tenantWeekAnchorCache = new Map<string, Date>();

const getTenantWeekAnchor = async (tenantId: string, year: number): Promise<Date> => {
  const cacheKey = `${tenantId}-${year}`;
  if (tenantWeekAnchorCache.has(cacheKey)) {
    return tenantWeekAnchorCache.get(cacheKey)!;
  }

  const firstShift = await prisma.shift.findFirst({
    where: { tenantId, year }, // Assuming shift also has year now? Yes user said everywhere.
    orderBy: { startTime: 'asc' },
    select: { startTime: true },
  });

  const anchor = firstShift?.startTime ?? new Date();
  const anchoredWeekStart = getWeekStart(anchor, 0);
  tenantWeekAnchorCache.set(cacheKey, anchoredWeekStart);
  return anchoredWeekStart;
};

const deriveWeekId = (weekStart: Date): string => {
  // Use ISO week number for meaningful week identification
  const startOfYear = new Date(Date.UTC(weekStart.getUTCFullYear(), 0, 1));
  const diffMs = weekStart.getTime() - startOfYear.getTime();
  const diffWeeks = Math.floor(diffMs / (7 * 24 * 60 * 60 * 1000));
  return `week-${diffWeeks + 1}`;
};

export const calculateWeeklyHours = async (
  tenantId: string,
  year: number,
  referenceDate: Date = new Date(),
  timezone?: string
): Promise<void> => {
  console.warn(`[Cron] Calculating payroll hours for tenant: ${tenantId}, year: ${year}`);

  const [frequencyRule, startRule] = await Promise.all([
    prisma.rule.findFirst({ where: { tenantId, year, type: 'PAYMENT_FREQUENCY', deletedAt: null } }),
    prisma.rule.findFirst({ where: { tenantId, year, type: 'START_OF_WEEK' } }),
  ]);
  const frequencyValue = parseInt(frequencyRule?.value?.toString() || '2');

  const now = new Date();
  const calcDate = new Date(referenceDate);

  const startDayIndex = startRule?.value ?? 1; // default Monday (1)

  const weekStart = getWeekStart(calcDate, startDayIndex, timezone);
  const weekEnd = getWeekEnd(weekStart);
  console.log(`[WeeklyHours] tenantId=${tenantId} referenceDate=${referenceDate.toISOString()} timezone=${timezone} startDayIndex=${startDayIndex} weekStart=${weekStart.toISOString()} weekEnd=${weekEnd.toISOString()}`);
  const fortnightStart = getFortnightStart(calcDate, startDayIndex);
  const fortnightEnd = getFortnightEnd(fortnightStart);
  const monthStart = getMonthStart(calcDate);
  const monthEnd = getMonthEnd(monthStart);

  const tenantAnchor = await getTenantWeekAnchor(tenantId, year);
  const weekId = deriveWeekId(weekStart);

  // Frequency Rule: 1=Daily, 2=Weekly, 3=Fortnightly, 4=Monthly
  // We lock the payroll hours record based on the payment frequency period end.
  // e.g., Fortnightly pay locks only after the full fortnight ends.
  const shouldLock =
    frequencyValue === 3
      ? now > fortnightEnd
      : frequencyValue === 4
        ? now > monthEnd
        : now > weekEnd; // Defaults to Weekly locking (covers Weekly and Daily)

  const maxRules = await prisma.rule.findMany({
    where: {
      tenantId,
      year,
      deletedAt: null,
      type: {
        in: [
          'MAX_WEEKLY_HOURS',
          'MAX_FORTNIGHT_HOURS',
          'MAX_MONTHLY_HOURS',
          'OVERTIME_AFTER_HOURS',
        ],
      },
    },
  });
  const maxWeekly = maxRules.find((r) => r.type === 'MAX_WEEKLY_HOURS')?.value;
  const maxFortnightly = maxRules.find((r) => r.type === 'MAX_FORTNIGHT_HOURS')?.value;
  const maxMonthly = maxRules.find((r) => r.type === 'MAX_MONTHLY_HOURS')?.value;
  const dailyMax = maxRules.find((r) => r.type === 'OVERTIME_AFTER_HOURS')?.value;

  const sleepoverDefRaw = await prisma.$queryRaw<
    Array<{ start_time: string | null; end_time: string | null }>
  >`
    SELECT start_time::text as start_time, end_time::text as end_time
    FROM shift_definitions
    WHERE tenant_id = ${tenantId} AND year = ${year} AND type = 'SLEEPOVER' AND deleted_at IS NULL
    LIMIT 1
  `;
  const sleepoverDef = sleepoverDefRaw?.[0];

  const periodEnd = new Date(Math.min(monthEnd.getTime(), now.getTime()));
  const segments = await prisma.shiftSegment.findMany({
    where: {
      shift: { tenantId },
      startTime: { lt: periodEnd },
      endTime: { gt: monthStart, lte: now },
    },
    include: {
      shift: { include: { segments: true } },
    },
  });

  type PeriodTotals = Totals & {
    byDay: Map<string, number>;
    fortnightWork: number;
    monthWork: number;
  };
  const totals = new Map<string, PeriodTotals>();

  const clipInterval = (
    segStart: Date,
    segEnd: Date,
    periodStart: Date,
    periodEnd: Date
  ): number => {
    const s = segStart < periodStart ? periodStart : segStart;
    const e = segEnd > periodEnd ? periodEnd : segEnd;
    if (e <= s) return 0;
    return (e.getTime() - s.getTime()) / (1000 * 60 * 60);
  };

  const addWorkToPeriods = (rec: PeriodTotals, intervalStart: Date, intervalEnd: Date) => {
    const weekH = clipInterval(intervalStart, intervalEnd, weekStart, weekEnd);
    const fortH = clipInterval(intervalStart, intervalEnd, fortnightStart, fortnightEnd);
    const monthH = clipInterval(intervalStart, intervalEnd, monthStart, monthEnd);
    rec.work += weekH;
    rec.fortnightWork += fortH;
    rec.monthWork += monthH;
    const pad2 = (n: number) => String(n).padStart(2, '0');
    for (
      let t = new Date(intervalStart);
      t.getTime() < intervalEnd.getTime();
      t.setUTCDate(t.getUTCDate() + 1)
    ) {
      const dayStart = new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate()));
      const dayEnd = new Date(dayStart);
      dayEnd.setUTCDate(dayEnd.getUTCDate() + 1);
      const dayH = clipInterval(intervalStart, intervalEnd, dayStart, dayEnd);
      if (dayH > 0) {
        const dayKey = `${t.getUTCFullYear()}-${pad2(t.getUTCMonth() + 1)}-${pad2(t.getUTCDate())}`;
        rec.byDay.set(dayKey, (rec.byDay.get(dayKey) ?? 0) + dayH);
      }
    }
  };

  for (const seg of segments) {
    const key = seg.shift.staffId;
    if (!totals.has(key)) {
      totals.set(key, {
        staffId: seg.shift.staffId,
        staffName: seg.shift.staffName,
        work: 0,
        sleepover: 0,
        disturbance: 0,
        byDay: new Map<string, number>(),
        fortnightWork: 0,
        monthWork: 0,
      });
    }
    const record = totals.get(key)!;

    const effectiveStart = seg.startTime < weekStart ? weekStart : seg.startTime;
    const effectiveEnd = seg.endTime > weekEnd ? weekEnd : seg.endTime;
    const hours =
      effectiveEnd > effectiveStart
        ? (effectiveEnd.getTime() - effectiveStart.getTime()) / (1000 * 60 * 60)
        : 0;

    const isSleepoverSegment = seg.type === 'SLEEPOVER';

    if (isSleepoverSegment && sleepoverDef?.start_time && sleepoverDef?.end_time) {
      const startMinutes = parseTimeToMinutes(sleepoverDef.start_time as string);
      const endMinutes = parseTimeToMinutes(sleepoverDef.end_time as string);
      const candidates: Array<{ start: Date; end: Date }> = [];
      for (const dayOffset of [-1, 0, 1]) {
        const base = new Date(
          Date.UTC(
            effectiveStart.getUTCFullYear(),
            effectiveStart.getUTCMonth(),
            effectiveStart.getUTCDate()
          )
        );
        base.setUTCDate(base.getUTCDate() + dayOffset);
        const winStart = new Date(base);
        winStart.setUTCHours(Math.floor(startMinutes / 60), startMinutes % 60, 0, 0);
        const winEnd = new Date(base);
        winEnd.setUTCHours(Math.floor(endMinutes / 60), endMinutes % 60, 0, 0);
        if (winEnd <= winStart) winEnd.setUTCDate(winEnd.getUTCDate() + 1);
        candidates.push({ start: winStart, end: winEnd });
      }
      const window = candidates.find((w) => w.end > effectiveStart && w.start < effectiveEnd);

      if (window) {
        const overlapSleepStart = window.start > effectiveStart ? window.start : effectiveStart;
        const overlapSleepEnd = window.end < effectiveEnd ? window.end : effectiveEnd;
        const sleepHours =
          Math.max(0, overlapSleepEnd.getTime() - overlapSleepStart.getTime()) / 3600000;
        const prefixMs = Math.max(0, window.start.getTime() - effectiveStart.getTime());
        const suffixMs = Math.max(0, effectiveEnd.getTime() - window.end.getTime());
        const prefixHours = prefixMs / 3600000;
        const suffixHours = suffixMs / 3600000;

        const shiftSegments = seg.shift.segments;
        const prefixHoursSum = shiftSegments
          .filter((s) => s.type === 'WORK' && s.endTime <= window.start)
          .reduce((sum, s) => sum + (s.endTime.getTime() - s.startTime.getTime()) / 3600000, 0);
        const suffixHoursSum = shiftSegments
          .filter((s) => s.type === 'WORK' && s.startTime >= window.end)
          .reduce((sum, s) => sum + (s.endTime.getTime() - s.startTime.getTime()) / 3600000, 0);
        const qualifiesForFlatRate = prefixHoursSum >= 4 || suffixHoursSum >= 4;

        if (qualifiesForFlatRate) {
          if (prefixHours >= 4) {
            addWorkToPeriods(record, effectiveStart, window.start);
          }
          if (suffixHours >= 4) {
            addWorkToPeriods(record, window.end, effectiveEnd);
          }
          record.sleepover += sleepHours;
        }
        if (seg.type === 'DISTURBANCE') record.disturbance += hours;
        continue;
      }
    }

    if (!isSleepoverSegment && seg.type === 'WORK') {
      addWorkToPeriods(record, seg.startTime, seg.endTime);
    }
    if (isSleepoverSegment) record.sleepover += hours;
    if (seg.type === 'DISTURBANCE') record.disturbance += hours;
  }

  const freqStr =
    frequencyValue === 1
      ? 'DAILY'
      : frequencyValue === 2
        ? 'WEEKLY'
        : frequencyValue === 3
          ? 'FORTNIGHTLY'
          : 'MONTHLY';

  for (const t of totals.values()) {
    const rec = t as PeriodTotals;
    let dailyOvertimeHours = 0;
    if (dailyMax != null) {
      for (const [, dayH] of rec.byDay) {
        dailyOvertimeHours += Math.max(0, dayH - Number(dailyMax));
      }
    }
    const weeklyOvertimeHours = maxWeekly != null ? Math.max(0, rec.work - Number(maxWeekly)) : 0;
    const fortnightlyOvertimeHours =
      maxFortnightly != null ? Math.max(0, rec.fortnightWork - Number(maxFortnightly)) : 0;
    const monthlyOvertimeHours =
      maxMonthly != null ? Math.max(0, rec.monthWork - Number(maxMonthly)) : 0;

    const existing = await prisma.payrollHours.findUnique({
      where: {
        tenantId_year_staffId_weekStart_paymentFrequency: {
          tenantId,
          year,
          staffId: rec.staffId,
          weekStart,
          paymentFrequency: freqStr,
        },
      },
    });

    if (existing?.isLocked) continue;

    const basePayload = {
      staffName: rec.staffName,
      weeklyHours: rec.work,
      fortnightlyHours: rec.fortnightWork,
      monthlyHours: rec.monthWork,
      dailyOvertimeHours,
      weeklyOvertimeHours,
      fortnightlyOvertimeHours,
      monthlyOvertimeHours,
      sleepovrHours: rec.sleepover,
      disturbanceHours: rec.disturbance,
      weekEnd,
      fortnightStart,
      fortnightEnd,
      monthStart,
      monthEnd,
      isLocked: shouldLock,
      weekId,
      paymentFrequency: freqStr,
    };

    console.log(`[WeeklyHours] Upserting staffId=${rec.staffId} weekStart=${weekStart.toISOString()} weeklyHours=${rec.work} fortnightlyHours=${rec.fortnightWork}`);
    await prisma.payrollHours.upsert({
      where: {
        tenantId_year_staffId_weekStart_paymentFrequency: {
          tenantId,
          year,
          staffId: rec.staffId,
          weekStart,
          paymentFrequency: freqStr,
        },
      },
      update: basePayload,
      create: {
        tenantId,
        year,
        staffId: rec.staffId,
        ...basePayload,
        laundryPaid: 0,
        uniformPaid: 0,
        weekStart,
      },
    });
  }
};

export const getWeeklyHoursForStaff = async (
  tenantId: string,
  staffId: string,
  year: number,
  referenceDate: Date = new Date(),
  timezone?: string
): Promise<Awaited<ReturnType<typeof prisma.payrollHours.findUnique>>> => {
  const [startRule, freqRule] = await Promise.all([
    prisma.rule.findFirst({ where: { tenantId, year, type: 'START_OF_WEEK' } }),
    prisma.rule.findFirst({ where: { tenantId, year, type: 'PAYMENT_FREQUENCY' } }),
  ]);
  const freqVal = parseInt(freqRule?.value?.toString() || '2');
  const paymentFrequency =
    freqVal === 1 ? 'DAILY' : freqVal === 2 ? 'WEEKLY' : freqVal === 3 ? 'FORTNIGHTLY' : 'MONTHLY';
  const weekStart = getWeekStart(referenceDate, startRule?.value ?? 1, timezone);

  return prisma.payrollHours.findUnique({
    where: {
      tenantId_year_staffId_weekStart_paymentFrequency: {
        tenantId,
        year,
        staffId,
        weekStart,
        paymentFrequency,
      },
    },
  });
};

export const getWeeklyHoursForTenant = async (
  tenantId: string,
  year: number,
  referenceDate: Date = new Date(),
  timezone?: string
): Promise<Awaited<ReturnType<typeof prisma.payrollHours.findMany>>> => {
  const startRule = await prisma.rule.findFirst({
    where: { tenantId, year, type: 'START_OF_WEEK' },
  });
  const weekStart = getWeekStart(referenceDate, startRule?.value ?? 1, timezone);
  return prisma.payrollHours.findMany({
    where: {
      tenantId,
      year,
      weekStart,
    },
    orderBy: { staffName: 'asc' },
  });
};

export const getWeeklyHistoryForStaff = async (
  tenantId: string,
  staffId: string,
  year: number,
  limit = 12
): Promise<Awaited<ReturnType<typeof prisma.payrollHours.findMany>>> => {
  return prisma.payrollHours.findMany({
    where: {
      tenantId,
      staffId,
      year,
    },
    orderBy: { weekStart: 'desc' },
    take: limit,
  });
};

/**
 * Get overtime eligible hours using hierarchy: Monthly -> Fortnightly -> Weekly -> Daily.
 * Returns total overtime hours based on the longest applicable period.
 */
export const getOvertimeEligibleHours = async (
  tenantId: string,
  staffId: string,
  year: number,
  referenceDate: Date
): Promise<number> => {
  const record = await getWeeklyHoursForStaff(tenantId, staffId, year, referenceDate);
  if (!record) return 0;

  const monthly = record.monthlyOvertimeHours ?? 0;
  const fortnightly = record.fortnightlyOvertimeHours ?? 0;
  const weekly = record.weeklyOvertimeHours ?? 0;
  const daily = record.dailyOvertimeHours ?? 0;

  const totalOvertime = monthly + fortnightly + weekly + daily;

  console.warn(
    `Overtime for ${staffId}: monthly=${monthly}h, fortnightly=${fortnightly}h, weekly=${weekly}h, daily=${daily}h, total=${totalOvertime}h`
  );

  return totalOvertime;
};

export const getTotalHoursInRange = async (
  tenantId: string,
  year: number,
  staffId: string,
  from: Date,
  to: Date
): Promise<{ work: number; sleepover: number; disturbance: number }> => {
  const records = await prisma.payrollHours.findMany({
    where: {
      tenantId,
      year,
      staffId,
      weekStart: { gte: from },
      weekEnd: { lte: to },
    },
  });

  return records.reduce(
    (acc, r) => {
      acc.work += r.weeklyHours;
      acc.sleepover += r.sleepovrHours ?? 0;
      acc.disturbance += r.disturbanceHours ?? 0;
      return acc;
    },
    { work: 0, sleepover: 0, disturbance: 0 }
  );
};

export const getFinishedShiftsForWeek = async (
  tenantId: string,
  year: number,
  weekStart: Date,
  weekEnd: Date,
  staffId?: string
): Promise<Awaited<ReturnType<typeof prisma.shift.findMany>>> => {
  return prisma.shift.findMany({
    where: {
      tenantId,
      year,
      ...(staffId ? { staffId } : {}),
      endTime: {
        gte: weekStart,
        lte: weekEnd,
      },
    },
    include: { segments: true },
    orderBy: { endTime: 'asc' },
  });
};

# --- FILE: service/payroll/rules/minimumEngagement.rule.ts ---
import { TenantConfig } from '@/types/payroll.types';

/**
 * Calculates the gap minutes needed to reach a minimum engagement.
 * Default is 2 hours (120 minutes), but can be overridden by tenant rules.
 */
export function calculateMinimumEngagementGap(
  durationMinutes: number,
  tenantConfig: TenantConfig
): number {
  const minEngagementRule =
    tenantConfig.rules.find((r) => r.type === 'MIN_ENGAGEMENT_HOURS_SOC_COMM') ||
    tenantConfig.rules.find((r) => r.type === 'MIN_ENGAGEMENT_HOURS_HOME_DISABILITY');

  const minEngagementMinutes = minEngagementRule?.value ? minEngagementRule.value * 60 : 120;

  if (durationMinutes < minEngagementMinutes) {
    return minEngagementMinutes - durationMinutes;
  }
  return 0;
}

# --- FILE: service/payroll/rules/eveningTrigger.rule.ts ---
import { ShiftSegment, TenantConfig } from '@/types/payroll.types';
import { extractHourFromTimeString, extractMinuteFromTimeString } from '@/service/payroll/core/timeUtils';

function getLocalTimeParts(date: Date, timezone?: string): { hour: number; minute: number; dateStr: string } {
  if (!timezone || timezone === 'UTC') {
    return {
      hour: date.getUTCHours(),
      minute: date.getUTCMinutes(),
      dateStr: date.toISOString().slice(0, 10),
    };
  }
  const hour = parseInt(date.toLocaleString('en-US', { timeZone: timezone, hour: 'numeric', hour12: false }));
  const minute = parseInt(date.toLocaleString('en-US', { timeZone: timezone, minute: 'numeric' }));
  const dateStr = date.toLocaleDateString('en-CA', { timeZone: timezone }); // YYYY-MM-DD
  return { hour, minute, dateStr };
}

/**
 * On weekdays, if a shift continues past the defined Evening start (e.g. 20:00 IST),
 * all preceding hours in that engagement (back to local midnight or morning reset) are upgraded.
 */
export function applyEveningTriggerRule(
  resolvedSegments: ShiftSegment[],
  tenantConfig: TenantConfig
): ShiftSegment[] {
  const afternoonDef = tenantConfig.shiftDefinitions.find((d) => d.type === 'AFTERNOON');
  const dayDef = tenantConfig.shiftDefinitions.find((d) => d.type === 'DAY');
  const timezone = tenantConfig.timezone;

  const eveningTriggerHour = afternoonDef?.startTime
    ? extractHourFromTimeString(afternoonDef.startTime)
    : 20;
  const morningResetHour = dayDef?.startTime ? extractHourFromTimeString(dayDef.startTime) : 6;
  const morningResetMin = dayDef?.startTime ? extractMinuteFromTimeString(dayDef.startTime) : 0;

  // Group segments into "Engagements" separated by local reset points (local midnight and morning reset)
  const engagements: ShiftSegment[][] = [];
  let currentEngagement: ShiftSegment[] = [];

  resolvedSegments.forEach((seg, idx) => {
    const { hour: startHour, minute: startMin } = getLocalTimeParts(seg.start, timezone);
    const isResetPoint =
      (startHour === 0 && startMin === 0) ||
      (startHour === morningResetHour && startMin === morningResetMin);

    if (idx > 0 && isResetPoint) {
      engagements.push(currentEngagement);
      currentEngagement = [];
    }
    currentEngagement.push(seg);
  });
  if (currentEngagement.length > 0) engagements.push(currentEngagement);

  // Process each engagement group for potential Evening upgrades
  engagements.forEach((engagementSegments) => {
    const firstInGroup = engagementSegments[0];
    const engDay = firstInGroup.start;
    const physicalEnd = firstInGroup.originalShiftEnd;

    // Compare local calendar dates (not UTC dates) to determine same-day
    const engDayLocal = getLocalTimeParts(engDay, timezone);
    const physicalEndLocal = getLocalTimeParts(physicalEnd, timezone);

    const isSameDayWork = engDayLocal.dateStr === physicalEndLocal.dateStr;

    // Trigger if physical work for this local day hit or passed the Evening start
    const qualifies =
      (!isSameDayWork && physicalEnd.getTime() > engDay.getTime()) ||
      (isSameDayWork && physicalEndLocal.hour >= eveningTriggerHour);

    if (qualifies) {
      engagementSegments.forEach((seg) => {
        if (seg.shiftType === 'DAY' && seg.calendarDayType === 'WEEKDAY') {
          seg.shiftType = 'AFTERNOON';
        }
      });
    } else {
      engagementSegments.forEach((seg) => {
        if (seg.shiftType === 'AFTERNOON' && seg.calendarDayType === 'WEEKDAY') {
          seg.shiftType = 'DAY';
        }
      });
    }
  });

  return resolvedSegments;
}
