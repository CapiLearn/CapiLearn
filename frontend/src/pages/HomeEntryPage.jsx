import { useEffect, useState } from "react";
import { useAuth } from "@clerk/react";
import { Navigate } from "react-router-dom";

import LandingPage from "./LandingPage";
import { API_BASE_URL, handleApiResponse } from "../services/apiClient";

function dashboardPathForRole(role) {
  if (role === "admin") {
    return "/admin-dashboard";
  }

  if (role === "instructor") {
    return "/instructor-dashboard";
  }

  return "/workspace";
}

function HomeEntryPage() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [targetPath, setTargetPath] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }

    let isCancelled = false;

    async function loadCurrentUser() {
      try {
        setErrorMessage("");

        const token = await getToken();

        if (!token) {
          throw new Error("Not authenticated.");
        }

        const response = await fetch(`${API_BASE_URL}/api/me`, {
          method: "GET",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        const currentUser = await handleApiResponse(
          response,
          "Unable to load current user."
        );

        if (!isCancelled) {
          setTargetPath(dashboardPathForRole(currentUser.role));
        }
      } catch (error) {
        if (!isCancelled) {
          setErrorMessage(error.message || "Unable to route signed-in user.");
        }
      }
    }

    loadCurrentUser();

    return () => {
      isCancelled = true;
    };
  }, [getToken, isLoaded, isSignedIn]);

  if (!isLoaded) {
    return (
      <main className="auth-page">
        <p>Loading...</p>
      </main>
    );
  }

  if (!isSignedIn) {
    return <LandingPage />;
  }

  if (targetPath) {
    return <Navigate to={targetPath} replace />;
  }

  if (errorMessage) {
    return (
      <main className="auth-page">
        <section className="auth-hero-panel">
          <p className="auth-kicker">CapiLearn</p>
          <h1>We couldn&apos;t load your account</h1>
          <p>{errorMessage}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="auth-page">
      <p>Loading your dashboard...</p>
    </main>
  );
}

export default HomeEntryPage;