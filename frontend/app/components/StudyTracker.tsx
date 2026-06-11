import React, { useState } from "react";
import {
  ChevronLeft, ChevronRight, Timer, Trophy, Target, ChevronDown, ChevronUp, Settings
} from "lucide-react";

interface CalendarClassInfo {
  class_title: string;
  course_name: string;
  class_minutes: number;
}

interface CalendarDay {
  date: string;
  total_minutes: number;
  goal_percentage: number;
  goal_met: boolean;
  classes?: CalendarClassInfo[];
}

interface TodayProgress {
  study_date: string | null;
  total_minutes: number;
  daily_goal: number;
  goal_percentage: number;
  goal_met: boolean;
}

interface MonthCalendar {
  year: number;
  month: number;
  daily_goal: number;
  days: CalendarDay[];
}

interface StudyTrackerProps {
  todayProgress: TodayProgress;
  calendar: MonthCalendar | null;
  dailyGoal: number;
  calendarYear: number;
  calendarMonth: number;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onOpenSettings: () => void;
}

const MONTH_NAMES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
];

const DAY_HEADERS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

function getCalendarGrid(year: number, month: number): (number | null)[][] {
  const firstDay = new Date(year, month - 1, 1);
  // Lunes = 0, Domingo = 6
  let startDay = firstDay.getDay() - 1;
  if (startDay < 0) startDay = 6;
  
  const daysInMonth = new Date(year, month, 0).getDate();
  const grid: (number | null)[][] = [];
  let currentDay = 1;
  
  for (let week = 0; week < 6; week++) {
    const row: (number | null)[] = [];
    for (let day = 0; day < 7; day++) {
      if (week === 0 && day < startDay) {
        row.push(null);
      } else if (currentDay > daysInMonth) {
        row.push(null);
      } else {
        row.push(currentDay);
        currentDay++;
      }
    }
    grid.push(row);
    if (currentDay > daysInMonth) break;
  }
  
  return grid;
}

export function StudyTracker({
  todayProgress,
  calendar,
  dailyGoal,
  calendarYear,
  calendarMonth,
  onPrevMonth,
  onNextMonth,
  onOpenSettings,
}: StudyTrackerProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [hoveredDayNum, setHoveredDayNum] = useState<number | null>(null);

  const progressPercent = Math.min(todayProgress.goal_percentage, 100);
  const isGoalMet = todayProgress.goal_met;
  const today = new Date();
  const isCurrentMonth = calendarYear === today.getFullYear() && calendarMonth === today.getMonth() + 1;

  // Build a lookup from day number → calendar data
  const dayDataMap = new Map<number, CalendarDay>();
  if (calendar) {
    for (const day of calendar.days) {
      const dayNum = parseInt(day.date.split("-")[2], 10);
      dayDataMap.set(dayNum, day);
    }
  }

  const calendarGrid = getCalendarGrid(calendarYear, calendarMonth);

  return (
    <div className="w-full bg-slate-900/60 border border-slate-800/80 rounded-2xl overflow-hidden transition-all-custom glassmorphism">
      {/* Header colapsable */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-5 py-4 flex items-center justify-between gap-4 hover:bg-slate-800/30 transition-all-custom cursor-pointer group"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 bg-gradient-to-tr from-emerald-600 to-teal-600 rounded-xl shadow-lg shadow-emerald-500/20">
            <Timer className="w-5 h-5 text-white" />
          </div>
          <div className="flex flex-col items-start min-w-0">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Estudio del día</span>
            <div className="flex items-center gap-2">
              <span className={`text-lg font-extrabold tabular-nums ${isGoalMet ? "text-emerald-400" : "text-slate-200"}`}>
                {todayProgress.total_minutes}
              </span>
              <span className="text-sm text-slate-500">/ {dailyGoal} min</span>
              {isGoalMet && (
                <span className="flex items-center gap-1 px-2 py-0.5 bg-emerald-500/15 border border-emerald-500/30 rounded-full text-[10px] font-bold text-emerald-400 animate-pulse">
                  <Trophy className="w-3 h-3" />
                  ¡Meta cumplida!
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Mini progress bar */}
          <div className="hidden sm:flex items-center gap-2 min-w-[160px]">
            <div className="flex-1 h-2.5 bg-slate-800 rounded-full overflow-hidden relative">
              <div
                className={`h-full rounded-full transition-all duration-700 ease-out ${
                  isGoalMet
                    ? "bg-gradient-to-r from-emerald-500 to-teal-400 shadow-[0_0_8px_rgba(16,185,129,0.4)]"
                    : "bg-gradient-to-r from-blue-500 to-indigo-500"
                }`}
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <span className="text-[10px] font-bold text-slate-500 tabular-nums w-10 text-right">
              {Math.round(progressPercent)}%
            </span>
          </div>
          
          <button
            onClick={(e) => { e.stopPropagation(); onOpenSettings(); }}
            className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-lg transition-all"
            title="Configuración de estudio"
          >
            <Settings className="w-4 h-4" />
          </button>

          {isExpanded ? (
            <ChevronUp className="w-5 h-5 text-slate-500 group-hover:text-slate-300 transition-colors" />
          ) : (
            <ChevronDown className="w-5 h-5 text-slate-500 group-hover:text-slate-300 transition-colors" />
          )}
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-5 pb-5 pt-2 border-t border-slate-800/60 animate-fade-in">
          {/* Full progress bar */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5 text-xs text-slate-400">
                <Target className="w-3.5 h-3.5" />
                <span>Progreso diario</span>
              </div>
              <span className={`text-xs font-bold tabular-nums ${isGoalMet ? "text-emerald-400" : "text-slate-300"}`}>
                {todayProgress.total_minutes} / {dailyGoal} min
                {todayProgress.total_minutes > dailyGoal && (
                  <span className="text-emerald-500 ml-1">(+{todayProgress.total_minutes - dailyGoal})</span>
                )}
              </span>
            </div>
            <div className="w-full h-4 bg-slate-800 rounded-full overflow-hidden relative">
              <div
                className={`h-full rounded-full transition-all duration-1000 ease-out relative ${
                  isGoalMet
                    ? "bg-gradient-to-r from-emerald-500 via-teal-400 to-emerald-500 shadow-[0_0_12px_rgba(16,185,129,0.5)]"
                    : progressPercent > 60
                    ? "bg-gradient-to-r from-blue-500 via-indigo-500 to-violet-500"
                    : "bg-gradient-to-r from-blue-600 to-blue-500"
                }`}
                style={{ width: `${progressPercent}%` }}
              >
                {progressPercent > 15 && (
                  <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/20 to-white/0 animate-shimmer" />
                )}
              </div>
            </div>
          </div>

          {/* Calendar */}
          <div>
            {/* Calendar header */}
            <div className="flex items-center justify-between mb-3">
              <button
                onClick={onPrevMonth}
                className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-all cursor-pointer"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-sm font-bold text-slate-300">
                {MONTH_NAMES[calendarMonth - 1]} {calendarYear}
              </span>
              <button
                onClick={onNextMonth}
                className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-all cursor-pointer"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            {/* Day headers */}
            <div className="grid grid-cols-7 gap-1 mb-1">
              {DAY_HEADERS.map((header) => (
                <div key={header} className="text-center text-[10px] font-bold text-slate-600 uppercase py-1">
                  {header}
                </div>
              ))}
            </div>

            {/* Calendar grid */}
            <div className="grid grid-cols-7 gap-1">
              {calendarGrid.flat().map((dayNum, idx) => {
                if (dayNum === null) {
                  return <div key={`empty-${idx}`} className="aspect-square" />;
                }

                const dayData = dayDataMap.get(dayNum);
                const isToday = isCurrentMonth && dayNum === today.getDate();
                const hasActivity = !!dayData && dayData.total_minutes > 0;
                
                // Calcular tamaño y opacidad del círculo proporcional al porcentaje
                let circleScale = 0;
                let circleOpacity = 0;
                if (hasActivity && dayData) {
                  const pct = Math.min(dayData.goal_percentage, 100) / 100;
                  // Escala: de 0.4 (mínimo visible) a 1.0 (meta cumplida)
                  circleScale = 0.4 + pct * 0.6;
                  // Opacidad: de 0.25 (mínimo) a 1.0 (meta cumplida)
                  circleOpacity = 0.25 + pct * 0.75;
                }

                const isHovered = hoveredDayNum === dayNum;
                const isFirstTwoRows = idx < 14;

                return (
                  <div
                    key={`day-${dayNum}`}
                    className="aspect-square flex items-center justify-center relative group"
                    onMouseEnter={() => hasActivity && setHoveredDayNum(dayNum)}
                    onMouseLeave={() => setHoveredDayNum(null)}
                  >
                    {/* Círculo de fondo proporcional al progreso */}
                    {hasActivity && (
                      <div
                        className={`absolute rounded-full transition-all duration-500 ${
                          dayData!.goal_met
                            ? "bg-emerald-500"
                            : "bg-blue-500"
                        }`}
                        style={{
                          width: `${circleScale * 85}%`,
                          height: `${circleScale * 85}%`,
                          opacity: circleOpacity,
                        }}
                      />
                    )}

                    {/* Today ring */}
                    {isToday && (
                      <div className="absolute inset-[2px] rounded-full border-2 border-indigo-400/60" />
                    )}

                    {/* Day number */}
                    <span
                      className={`relative z-10 text-xs font-semibold tabular-nums ${
                        isToday
                          ? "text-indigo-300 font-extrabold"
                          : hasActivity && dayData?.goal_met
                          ? "text-white font-bold"
                          : hasActivity
                          ? "text-slate-200"
                          : "text-slate-600"
                      }`}
                    >
                      {dayNum}
                    </span>

                    {/* Diálogo emergente con la lista de clases tomadas */}
                    {isHovered && hasActivity && dayData && dayData.classes && dayData.classes.length > 0 && (
                      <div 
                        className={`absolute z-50 w-64 bg-slate-950/95 border border-slate-800 rounded-xl p-3 shadow-2xl backdrop-blur-md text-left pointer-events-none animate-fade-in ${
                          isFirstTwoRows ? "top-full mt-2" : "bottom-full mb-2"
                        }`}
                      >
                        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2 pb-1 border-b border-slate-800/80 flex justify-between">
                          <span>Clases tomadas</span>
                          <span className="text-indigo-400">{dayData.total_minutes} min</span>
                        </div>
                        <div className="max-h-36 overflow-y-auto scrollbar-thin flex flex-col gap-2 pr-1">
                          {dayData.classes.map((cls, cIdx) => (
                            <div key={cIdx} className="flex flex-col gap-0.5 border-l-2 border-indigo-500/60 pl-2 py-0.5">
                              <span className="text-[9px] text-slate-500 font-bold uppercase truncate" title={cls.course_name}>
                                {cls.course_name}
                              </span>
                              <span className="text-xs text-slate-200 font-semibold leading-snug break-words">
                                {cls.class_title}
                              </span>
                              <span className="text-[10px] text-indigo-400 font-medium">
                                ⏱ {cls.class_minutes} min
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Calendar legend */}
            <div className="flex items-center justify-center gap-4 mt-3 pt-3 border-t border-slate-800/40">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-emerald-500 opacity-100" />
                <span className="text-[10px] text-slate-500">Meta cumplida</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-blue-500 opacity-50" />
                <span className="text-[10px] text-slate-500">Progreso parcial</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-4 h-4 rounded-full border-2 border-indigo-400/60" />
                <span className="text-[10px] text-slate-500">Hoy</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
