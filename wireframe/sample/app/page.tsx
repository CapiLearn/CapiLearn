"use client"

import { useEffect, useState } from "react"
import { AdminDashboard } from "@/components/admin-dashboard"
import { LandingPage } from "@/components/landing-page"
import { ChatDashboard } from "@/components/chat-dashboard"

export default function Home() {
  const [isLoggedIn, setIsLoggedIn] = useState(false)
  const [isAdminRoute, setIsAdminRoute] = useState(false)

  useEffect(() => {
    const syncHashRoute = () => {
      setIsAdminRoute(window.location.hash === "#admin")
    }

    syncHashRoute()
    window.addEventListener("hashchange", syncHashRoute)

    return () => window.removeEventListener("hashchange", syncHashRoute)
  }, [])

  if (isAdminRoute) {
    return <AdminDashboard />
  }

  if (isLoggedIn) {
    return <ChatDashboard onLogout={() => setIsLoggedIn(false)} />
  }

  return <LandingPage onLogin={() => setIsLoggedIn(true)} />
}
