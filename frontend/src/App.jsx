import { SignIn, SignUp, useAuth } from "@clerk/react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import LandingPage from "./pages/LandingPage";
import LearningWorkspace from "./pages/LearningWorkspace";
import StudentDashboard from "./pages/StudentDashboard";
import InstructorDashboard from "./pages/InstructorDashboard";
import AdminDashboard from "./pages/AdminDashboard";

function ProtectedRoute({ children }) {
  const { isLoaded, isSignedIn } = useAuth();

  if (!isLoaded) {
    return (
      <main className="auth-page">
        <p>Loading...</p>
      </main>
    );
  }

  if (!isSignedIn) {
    return <Navigate to="/sign-in" replace />;
  }

  return children;
}

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

        <Route
          path="/workspace"
          element={
            <ProtectedRoute>
              <LearningWorkspace />
            </ProtectedRoute>
          }
        />

        <Route
          path="/student-dashboard"
          element={
            <ProtectedRoute>
              <StudentDashboard />
            </ProtectedRoute>
          }
        />

        <Route
          path="/instructor-dashboard"
          element={
            <ProtectedRoute>
              <InstructorDashboard />
            </ProtectedRoute>
          }
        />

        <Route
          path="/admin-dashboard"
          element={
            <ProtectedRoute>
              <AdminDashboard />
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;