import { useAuth } from "@clerk/react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import LandingPage from "./pages/LandingPage";
import LearningWorkspace from "./pages/LearningWorkspace";
import StudentDashboard from "./pages/StudentDashboard";
import InstructorDashboard from "./pages/InstructorDashboard";
import AdminDashboard from "./pages/AdminDashboard";
import AuthPage from "./pages/AuthPage";

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
            <AuthPage
              mode="sign-in"
              title="Welcome back"
              description="Sign in to continue your course-aligned study sessions, progress tracking, and guided explanations."
            />
          }
        />

        <Route
          path="/sign-up/*"
          element={
            <AuthPage
              mode="sign-up"
              title="Start learning with Capi"
              description="Create your account to ask course questions, get guided explanations, and keep your learning progress visible."
            />
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