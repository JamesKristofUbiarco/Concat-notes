import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface TodayProgress {
  study_date: string | null;
  total_minutes: number;
  daily_goal: number;
  goal_percentage: number;
  goal_met: boolean;
}

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

interface MonthCalendar {
  year: number;
  month: number;
  daily_goal: number;
  days: CalendarDay[];
}

export function useStudyTracker() {
  const [todayProgress, setTodayProgress] = useState<TodayProgress>({
    study_date: null,
    total_minutes: 0,
    daily_goal: 60,
    goal_percentage: 0,
    goal_met: false,
  });
  const [calendar, setCalendar] = useState<MonthCalendar | null>(null);
  const [dailyGoal, setDailyGoal] = useState(60);
  const [calendarYear, setCalendarYear] = useState(new Date().getFullYear());
  const [calendarMonth, setCalendarMonth] = useState(new Date().getMonth() + 1);

  // --- Fetch today's progress ---
  const fetchToday = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/study/today`);
      if (res.ok) {
        const data: TodayProgress = await res.json();
        setTodayProgress(data);
      }
    } catch (e) {
      console.error("Error al cargar progreso de hoy", e);
    }
  }, []);

  // --- Fetch settings ---
  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/study/settings`);
      if (res.ok) {
        const data = await res.json();
        setDailyGoal(data.daily_goal);
      }
    } catch (e) {
      console.error("Error al cargar configuración de estudio", e);
    }
  }, []);

  // --- Fetch calendar month ---
  const fetchCalendar = useCallback(async (year: number, month: number) => {
    try {
      const res = await fetch(`${API_BASE}/api/study/calendar/${year}/${month}`);
      if (res.ok) {
        const data: MonthCalendar = await res.json();
        setCalendar(data);
      }
    } catch (e) {
      console.error("Error al cargar calendario", e);
    }
  }, []);

  // --- Log study minutes ---
  const logMinutes = useCallback(async (minutes: number) => {
    if (minutes < 1) return;
    try {
      const res = await fetch(`${API_BASE}/api/study/log`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ minutes }),
      });
      if (res.ok) {
        await fetchToday();
        await fetchCalendar(calendarYear, calendarMonth);
      }
    } catch (e) {
      console.error("Error al registrar minutos de estudio", e);
    }
  }, [fetchToday, fetchCalendar, calendarYear, calendarMonth]);

  // --- Update daily goal ---
  const updateGoal = useCallback(async (minutes: number) => {
    if (minutes < 1) return;
    try {
      const res = await fetch(`${API_BASE}/api/study/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ daily_goal: minutes }),
      });
      if (res.ok) {
        const data = await res.json();
        setDailyGoal(data.daily_goal);
        await fetchToday();
      }
    } catch (e) {
      console.error("Error al actualizar meta diaria", e);
    }
  }, [fetchToday]);

  // --- Navigate calendar ---
  const goToPrevMonth = useCallback(() => {
    setCalendarMonth(prev => {
      if (prev === 1) {
        setCalendarYear(y => y - 1);
        return 12;
      }
      return prev - 1;
    });
  }, []);

  const goToNextMonth = useCallback(() => {
    setCalendarMonth(prev => {
      if (prev === 12) {
        setCalendarYear(y => y + 1);
        return 1;
      }
      return prev + 1;
    });
  }, []);

  // --- Initial load ---
  useEffect(() => {
    fetchToday();
    fetchSettings();
  }, [fetchToday, fetchSettings]);

  // --- Reload calendar when month/year changes ---
  useEffect(() => {
    fetchCalendar(calendarYear, calendarMonth);
  }, [calendarYear, calendarMonth, fetchCalendar]);

  return {
    todayProgress,
    calendar,
    dailyGoal,
    calendarYear,
    calendarMonth,
    logMinutes,
    updateGoal,
    goToPrevMonth,
    goToNextMonth,
    fetchToday,
    fetchCalendar,
  };
}
