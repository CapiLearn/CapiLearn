"use client"

import { Button } from "@/components/ui/button"
import { BookOpen, Brain, Flame, MessageSquare, Sparkles, Sprout, Target } from "lucide-react"

interface LandingPageProps {
  onLogin: () => void
}

export function LandingPage({ onLogin }: LandingPageProps) {
  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
              <Sprout className="h-5 w-5 text-primary-foreground" />
            </div>
            <span className="text-xl font-bold text-foreground">CapiLearn</span>
          </div>
          <div className="hidden items-center gap-8 md:flex">
            <a href="#features" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
              Features
            </a>
            <a href="#how-it-works" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
              How it works
            </a>
          </div>
          <Button onClick={onLogin} className="bg-primary text-primary-foreground hover:bg-primary/90">
            Log in
          </Button>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative flex min-h-screen flex-col items-center justify-center px-6 pt-16">
        <div className="absolute inset-0 overflow-hidden">
          <div className="absolute left-1/2 top-1/4 h-96 w-96 -translate-x-1/2 rounded-full bg-accent/30 blur-3xl" />
          <div className="absolute right-1/4 top-1/3 h-64 w-64 rounded-full bg-primary/10 blur-3xl" />
        </div>
        
        <div className="relative z-10 mx-auto max-w-4xl text-center">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-secondary px-4 py-2 text-sm text-muted-foreground">
            <Sparkles className="h-4 w-4 text-primary" />
            Learn. Understand. Grow.
          </div>
          
          <h1 className="mb-6 text-balance text-5xl font-bold leading-tight tracking-tight text-foreground md:text-7xl">
            Learn smarter with your
            <span className="text-primary"> chill AI study buddy</span>
          </h1>
          
          <p className="mx-auto mb-10 max-w-2xl text-pretty text-lg text-muted-foreground md:text-xl">
            Get personalized explanations, track your learning streaks, and grow your confidence one step at a time.
          </p>
          
          <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Button 
              onClick={onLogin} 
              size="lg" 
              className="w-full bg-primary text-primary-foreground hover:bg-primary/90 sm:w-auto"
            >
              Get started free
            </Button>
            <Button 
              variant="outline" 
              size="lg" 
              className="w-full border-border text-foreground hover:bg-secondary sm:w-auto"
            >
              See how it works
            </Button>
          </div>
          
          <div className="mt-12 flex flex-wrap items-center justify-center gap-8 text-sm text-muted-foreground">
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/20">
                <Flame className="h-3 w-3 text-primary" />
              </div>
              Track daily streaks
            </div>
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/20">
                <MessageSquare className="h-3 w-3 text-primary" />
              </div>
              Chat-based learning
            </div>
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/20">
                <Target className="h-3 w-3 text-primary" />
              </div>
              One step at a time
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="border-t border-border bg-card px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <div className="mb-16 text-center">
            <h2 className="mb-4 text-3xl font-bold text-foreground md:text-4xl">
              Everything you need to excel
            </h2>
            <p className="mx-auto max-w-2xl text-muted-foreground">
              CapiLearn adapts to your learning style and keeps studying calm, curious, and consistent.
            </p>
          </div>
          
          <div className="grid gap-6 md:grid-cols-3">
            <FeatureCard 
              icon={<Brain className="h-6 w-6" />}
              title="AI Tutoring"
              description="Get instant answers and explanations tailored to your level of understanding."
            />
            <FeatureCard 
              icon={<Flame className="h-6 w-6" />}
              title="Streak Tracking"
              description="Build consistent study habits with daily check-ins and streak rewards."
            />
            <FeatureCard 
              icon={<BookOpen className="h-6 w-6" />}
              title="Conversation History"
              description="Never lose your progress. All your learning sessions are saved and searchable."
            />
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="border-t border-border px-6 py-24">
        <div className="mx-auto max-w-4xl text-center">
          <h2 className="mb-4 text-3xl font-bold text-foreground md:text-4xl">
            Ready to grow your learning?
          </h2>
          <p className="mb-8 text-muted-foreground">
            Join students who are learning with CapiLearn one calm step at a time.
          </p>
          <Button 
            onClick={onLogin} 
            size="lg" 
            className="bg-primary text-primary-foreground hover:bg-primary/90"
          >
            Start learning for free
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 md:flex-row">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary">
              <Sprout className="h-4 w-4 text-primary-foreground" />
            </div>
            <span className="font-semibold text-foreground">CapiLearn</span>
          </div>
          <p className="text-sm text-muted-foreground">
            © 2026 CapiLearn. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  )
}

function FeatureCard({ 
  icon, 
  title, 
  description 
}: { 
  icon: React.ReactNode
  title: string
  description: string 
}) {
  return (
    <div className="group rounded-xl border border-border bg-card/70 p-6 transition-colors hover:border-accent hover:bg-secondary/70">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-accent group-hover:text-accent-foreground">
        {icon}
      </div>
      <h3 className="mb-2 text-lg font-semibold text-foreground">{title}</h3>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  )
}
