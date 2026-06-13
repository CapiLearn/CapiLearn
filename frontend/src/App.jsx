import { BrowserRouter, Routes, Route } from "react-router-dom";

import BetaAuthDialog from "./components/BetaAuthDialog";
import LandingPage from "./pages/LandingPage";
import LearningWorkspace from "./pages/LearningWorkspace";
import StudentDashboard from "./pages/StudentDashboard";
import InstructorDashboard from "./pages/InstructorDashboard";
import AdminDashboard from "./pages/AdminDashboard";

function App() {
  return (
    <BrowserRouter>
      {/* TEMP BETA AUTH SHIM: Remove when Clerk authentication is wired end-to-end. */}
      <BetaAuthDialog />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/workspace" element={<LearningWorkspace />} />
        <Route path="/student-dashboard" element={<StudentDashboard />} />
        <Route path="/instructor-dashboard" element={<InstructorDashboard />} />
        <Route path="/admin-dashboard" element={<AdminDashboard />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
