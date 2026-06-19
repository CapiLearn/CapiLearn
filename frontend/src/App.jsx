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
          element={<SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" />}
        />

        <Route
          path="/sign-up/*"
          element={<SignUp routing="path" path="/sign-up" signInUrl="/sign-in" />}
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