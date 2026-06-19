import { SignIn, SignUp } from "@clerk/react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import LandingPage from "./pages/LandingPage";
import LearningWorkspace from "./pages/LearningWorkspace";
import StudentDashboard from "./pages/StudentDashboard";
import InstructorDashboard from "./pages/InstructorDashboard";
import AdminDashboard from "./pages/AdminDashboard";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />

        <Route
          path="/sign-in/*"
          element={
            <main className="auth-page">
              <section className="auth-hero-panel">
                <div className="auth-brand-mark">♧</div>
                <p className="auth-kicker">CapiLearn</p>
                <h1>Welcome back</h1>
                <p>
                  Sign in to continue your course-aligned study sessions, progress
                  tracking, and guided explanations.
                </p>
              </section>

              <section className="auth-card-shell">
                <SignIn
                  routing="path"
                  path="/sign-in"
                  signUpUrl="/sign-up"
                  appearance={{
                    elements: {
                      rootBox: "auth-clerk-root",
                      cardBox: "auth-clerk-card",
                    },
                  }}
                />
              </section>
            </main>
          }
        />

        <Route
          path="/sign-up/*"
          element={
            <main className="auth-page">
              <section className="auth-hero-panel">
                <div className="auth-brand-mark">♧</div>
                <p className="auth-kicker">CapiLearn</p>
                <h1>Start learning with Capi</h1>
                <p>
                  Create your account to ask course questions, get guided explanations,
                  and keep your learning progress visible.
                </p>
              </section>

              <section className="auth-card-shell">
                <SignUp
                  routing="path"
                  path="/sign-up"
                  signInUrl="/sign-in"
                  appearance={{
                    elements: {
                      rootBox: "auth-clerk-root",
                      cardBox: "auth-clerk-card",
                    },
                  }}
                />
              </section>
            </main>
          }
        />

        <Route path="/workspace" element={<LearningWorkspace />} />
        <Route path="/student-dashboard" element={<StudentDashboard />} />
        <Route path="/instructor-dashboard" element={<InstructorDashboard />} />
        <Route path="/admin-dashboard" element={<AdminDashboard />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;