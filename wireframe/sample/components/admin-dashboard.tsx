"use client"

import { Progress } from "@/components/ui/progress"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  AlertCircle,
  CalendarDays,
  Clock3,
  GraduationCap,
  MessageSquareText,
  Sprout,
  Users,
} from "lucide-react"

const classStats = [
  {
    label: "Active students",
    value: "128",
    detail: "22 checked in today",
    icon: Users,
  },
  {
    label: "Questions asked",
    value: "1,482",
    detail: "312 this week",
    icon: MessageSquareText,
  },
  {
    label: "Students to review",
    value: "9",
    detail: "3 need follow-up today",
    icon: AlertCircle,
  },
]

const topicDistribution = [
  { topic: "Math", share: 34, questions: 504, trend: "+8%" },
  { topic: "Science", share: 27, questions: 400, trend: "+5%" },
  { topic: "History", share: 16, questions: 237, trend: "-2%" },
  { topic: "Writing", share: 14, questions: 207, trend: "+6%" },
  { topic: "Study Skills", share: 9, questions: 134, trend: "+3%" },
]

const students = [
  {
    name: "Maya Chen",
    topTopic: "Math",
    questionsThisWeek: 28,
    streak: 14,
    status: "On track",
    lastActive: "18 min ago",
  },
  {
    name: "Jordan Reed",
    topTopic: "Science",
    questionsThisWeek: 19,
    streak: 2,
    status: "Needs support",
    lastActive: "42 min ago",
  },
  {
    name: "Ari Patel",
    topTopic: "History",
    questionsThisWeek: 16,
    streak: 8,
    status: "On track",
    lastActive: "1 hr ago",
  },
  {
    name: "Sofia Garcia",
    topTopic: "Writing",
    questionsThisWeek: 22,
    streak: 5,
    status: "Watch",
    lastActive: "Yesterday",
  },
  {
    name: "Noah Brooks",
    topTopic: "Math",
    questionsThisWeek: 24,
    streak: 11,
    status: "On track",
    lastActive: "Yesterday",
  },
]

const reviewQueue = [
  {
    student: "Jordan Reed",
    reason: "Science questions are clustering around the same cell-division concept",
    time: "Due today",
  },
  {
    student: "Sofia Garcia",
    reason: "Writing questions shifted from drafting to feedback anxiety",
    time: "Review tomorrow",
  },
  {
    student: "Eli Morgan",
    reason: "Asked for help with the same algebra step 4 times",
    time: "Review this week",
  },
]

export function AdminDashboard() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Sprout className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">
                CapiLearn Instructor
              </p>
              <h1 className="text-lg font-semibold text-foreground">
                Student Progress Dashboard
              </h1>
            </div>
          </div>
          <div className="hidden items-center gap-2 rounded-full border border-border bg-secondary px-3 py-1.5 text-sm text-muted-foreground sm:flex">
            <CalendarDays className="h-4 w-4 text-primary" />
            Spring Cohort 2026
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-8 px-6 py-8">
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {classStats.map((stat) => (
            <div
              key={stat.label}
              className="rounded-xl border border-border bg-card p-5 shadow-sm"
            >
              <div className="mb-4 flex items-center justify-between gap-3">
                <p className="text-sm font-medium text-muted-foreground">
                  {stat.label}
                </p>
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <stat.icon className="h-5 w-5" />
                </div>
              </div>
              <p className="text-3xl font-bold text-foreground">{stat.value}</p>
              <p className="mt-1 text-sm text-muted-foreground">{stat.detail}</p>
            </div>
          ))}
        </section>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="rounded-xl border border-border bg-card shadow-sm">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <h2 className="font-semibold text-foreground">
                  Question Distribution by Topic
                </h2>
                <p className="text-sm text-muted-foreground">
                  Where students are focusing their RAG-based study questions
                </p>
              </div>
              <MessageSquareText className="h-5 w-5 text-primary" />
            </div>
            <div className="divide-y divide-border">
              {topicDistribution.map((topic) => (
                <div
                  key={topic.topic}
                  className="grid gap-4 px-5 py-4 md:grid-cols-[1fr_8rem_5rem]"
                >
                  <div>
                    <div className="mb-2 flex items-center justify-between gap-4">
                      <p className="font-medium text-foreground">
                        {topic.topic}
                      </p>
                      <span className="text-sm text-muted-foreground md:hidden">
                        {topic.share}%
                      </span>
                    </div>
                    <Progress value={topic.share} />
                    <p className="mt-2 text-sm text-muted-foreground">
                      {topic.questions} questions in the last 30 days
                    </p>
                  </div>
                  <div className="hidden items-center text-2xl font-semibold text-foreground md:flex">
                    {topic.share}%
                  </div>
                  <div className="flex items-center text-sm font-medium text-primary">
                    {topic.trend}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <aside className="rounded-xl border border-border bg-sidebar p-5 shadow-sm">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h2 className="font-semibold text-sidebar-foreground">
                  Review Queue
                </h2>
                <p className="text-sm text-muted-foreground">
                  Students who may need instructor attention
                </p>
              </div>
              <AlertCircle className="h-5 w-5 text-accent-foreground" />
            </div>
            <div className="space-y-3">
              {reviewQueue.map((item) => (
                <div
                  key={item.student}
                  className="rounded-lg border border-sidebar-border bg-card p-4"
                >
                  <p className="font-medium text-card-foreground">
                    {item.student}
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                    {item.reason}
                  </p>
                  <div className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-accent/20 px-2.5 py-1 text-xs font-medium text-accent-foreground">
                    <Clock3 className="h-3.5 w-3.5" />
                    {item.time}
                  </div>
                </div>
              ))}
            </div>
          </aside>
        </section>

        <section className="rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <div>
              <h2 className="font-semibold text-foreground">Student Roster</h2>
              <p className="text-sm text-muted-foreground">
                Recent activity, topic focus, and study consistency
              </p>
            </div>
            <GraduationCap className="h-5 w-5 text-primary" />
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-5">Student</TableHead>
                <TableHead>Top topic</TableHead>
                <TableHead>Questions this week</TableHead>
                <TableHead>Streak</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="pr-5 text-right">Last active</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {students.map((student) => (
                <TableRow key={student.name}>
                  <TableCell className="pl-5 font-medium text-foreground">
                    {student.name}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {student.topTopic}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {student.questionsThisWeek}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {student.streak} days
                  </TableCell>
                  <TableCell>
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                        student.status === "On track"
                          ? "bg-primary/10 text-primary"
                          : student.status === "Watch"
                          ? "bg-accent/20 text-accent-foreground"
                          : "bg-destructive/10 text-destructive"
                      }`}
                    >
                      {student.status}
                    </span>
                  </TableCell>
                  <TableCell className="pr-5 text-right text-muted-foreground">
                    {student.lastActive}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      </main>
    </div>
  )
}
