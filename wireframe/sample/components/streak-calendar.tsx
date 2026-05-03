"use client"

import { CalendarDays, Flame, TrendingUp } from "lucide-react"
import { useMemo } from "react"

export function StreakCalendar() {
  const today = new Date()
  const currentMonth = today.getMonth()
  const currentYear = today.getFullYear()

  // Generate check-in data (simulated)
  const checkIns = useMemo(() => {
    const data: Record<string, boolean> = {}
    // Simulate some check-ins for the current month
    const daysWithCheckIn = [1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19, 22, 23, 24, 25, 26, 29, 30]
    const currentDay = today.getDate()
    
    daysWithCheckIn.forEach((day) => {
      if (day <= currentDay) {
        const dateKey = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`
        data[dateKey] = true
      }
    })
    
    return data
  }, [currentMonth, currentYear, today])

  // Calculate current streak
  const currentStreak = useMemo(() => {
    let streak = 0
    const checkDate = new Date(today)
    
    while (true) {
      const dateKey = `${checkDate.getFullYear()}-${String(checkDate.getMonth() + 1).padStart(2, "0")}-${String(checkDate.getDate()).padStart(2, "0")}`
      if (checkIns[dateKey]) {
        streak++
        checkDate.setDate(checkDate.getDate() - 1)
      } else {
        break
      }
    }
    
    return streak
  }, [checkIns, today])

  // Generate calendar days
  const calendarDays = useMemo(() => {
    const firstDay = new Date(currentYear, currentMonth, 1)
    const lastDay = new Date(currentYear, currentMonth + 1, 0)
    const daysInMonth = lastDay.getDate()
    const startingDay = firstDay.getDay()

    const days: (number | null)[] = []
    
    // Add empty slots for days before the first day of the month
    for (let i = 0; i < startingDay; i++) {
      days.push(null)
    }
    
    // Add days of the month
    for (let day = 1; day <= daysInMonth; day++) {
      days.push(day)
    }
    
    return days
  }, [currentMonth, currentYear])

  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ]

  const dayNames = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]

  const isCheckedIn = (day: number) => {
    const dateKey = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`
    return checkIns[dateKey]
  }

  const isToday = (day: number) => {
    return day === today.getDate()
  }

  const totalCheckIns = Object.keys(checkIns).length

  return (
    <div className="flex h-full w-80 flex-col border-l border-border bg-sidebar">
      {/* Header */}
      <div className="flex h-16 items-center border-b border-sidebar-border px-4">
        <div className="flex items-center gap-2">
          <CalendarDays className="h-5 w-5 text-primary" />
          <h2 className="font-semibold text-sidebar-foreground">Study Tracker</h2>
        </div>
      </div>

      {/* Streak Stats */}
      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between rounded-xl bg-sidebar-accent p-4">
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Current Streak
            </p>
            <p className="text-3xl font-bold text-sidebar-foreground">
              {currentStreak}
            </p>
            <p className="text-xs text-muted-foreground">days</p>
          </div>
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent/25">
            <Flame className="h-6 w-6 text-accent-foreground" />
          </div>
        </div>

        <div className="flex gap-3">
          <div className="flex-1 rounded-xl bg-sidebar-accent p-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" />
              <span className="text-xs text-muted-foreground">This Month</span>
            </div>
            <p className="mt-1 text-xl font-semibold text-sidebar-foreground">
              {totalCheckIns}
              <span className="text-sm font-normal text-muted-foreground"> days</span>
            </p>
          </div>
          <div className="flex-1 rounded-xl bg-sidebar-accent p-3">
            <div className="flex items-center gap-2">
              <Flame className="h-4 w-4 text-accent-foreground" />
              <span className="text-xs text-muted-foreground">Best Streak</span>
            </div>
            <p className="mt-1 text-xl font-semibold text-sidebar-foreground">
              15
              <span className="text-sm font-normal text-muted-foreground"> days</span>
            </p>
          </div>
        </div>
      </div>

      {/* Calendar */}
      <div className="flex-1 p-4 pt-0">
        <div className="rounded-xl border border-sidebar-border bg-card p-4">
          <h3 className="mb-4 text-center font-medium text-card-foreground">
            {monthNames[currentMonth]} {currentYear}
          </h3>
          
          {/* Day names */}
          <div className="mb-2 grid grid-cols-7 gap-1">
            {dayNames.map((day) => (
              <div
                key={day}
                className="flex h-8 items-center justify-center text-xs font-medium text-muted-foreground"
              >
                {day}
              </div>
            ))}
          </div>
          
          {/* Calendar grid */}
          <div className="grid grid-cols-7 gap-1">
            {calendarDays.map((day, index) => (
              <div
                key={index}
                className={`flex h-8 w-full items-center justify-center rounded-lg text-xs transition-colors ${
                  day === null
                    ? ""
                    : isToday(day)
                    ? "ring-2 ring-accent ring-offset-2 ring-offset-card " +
                      (isCheckedIn(day)
                        ? "bg-streak text-accent-foreground"
                        : "bg-muted text-muted-foreground")
                    : isCheckedIn(day)
                    ? "bg-streak text-accent-foreground"
                    : day <= today.getDate()
                    ? "bg-muted/50 text-muted-foreground"
                    : "text-muted-foreground/50"
                }`}
              >
                {day}
              </div>
            ))}
          </div>

          {/* Legend */}
          <div className="mt-4 flex items-center justify-center gap-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <div className="h-3 w-3 rounded bg-streak" />
              <span>Checked in</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="h-3 w-3 rounded bg-muted/50" />
              <span>Missed</span>
            </div>
          </div>
        </div>

        {/* Motivational message */}
        <div className="mt-4 rounded-xl bg-accent/20 p-4 text-center">
          <p className="text-sm font-medium text-accent-foreground">
            {currentStreak >= 7
              ? "Amazing! Keep the momentum going!"
              : currentStreak >= 3
              ? "Great progress! You're building a habit!"
              : "Every day counts. Start your streak today!"}
          </p>
        </div>
      </div>
    </div>
  )
}
