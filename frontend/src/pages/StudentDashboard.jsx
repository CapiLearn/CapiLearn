import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@clerk/react";
import { Link } from "react-router-dom";
import capiCoffeeIcon from "../assets/capi_coffee_icon.png";
import { getActivityCalendar } from "../services/activityService";
import "../styles/StudentDashboard.css";

const statCards = [
  {
    label: "Current progress",
    value: "68%",
    helper: "Across assigned learning modules",
  },
  {
    label: "Total time",
    value: "14.5 hrs",
    helper: "Spent learning in CapiLearn",
  },
  {
    label: "Sessions",
    value: "23",
    helper: "Study sessions completed",
  },
];

const modules = [
  {
    title: "Ipsum Lorem",
    progress: 90,
    status: "Almost complete",
  },
  {
    title: "Ipsum Lorem",
    progress: 72,
    status: "In progress",
  },
  {
    title: "Ipsum Lorem",
    progress: 55,
    status: "Needs review",
  },
  {
    title: "Ipsum Lorem",
    progress: 38,
    status: "Started",
  },
];

const recentActivity = [
  "Ipsum Lorem",
  "Ipsum Lorem",
  "Ipsum Lorem",
  "Ipsum Lorem",
];

const focusAreas = [
  "Ipsum Lorem",
  "Ipsum Lorem",
  "Ipsum Lorem",
];

function toDateKey(date) {
  return date.toISOString().slice(0, 10);
}

function getCurrentMonthRange() {
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0);

  return {
    fromDate: toDateKey(firstDay),
    toDate: toDateKey(lastDay),
  };
}

function StudentDashboard() {

  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [currentStreak, setCurrentStreak] = useState(null);
  const [activeDaysCount, setActiveDaysCount] = useState(null);
  const [activityError, setActivityError] = useState("");

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }

    let isMounted = true;

    async function loadActivityCalendar() {
      try {
        setActivityError("");

        const token = (await getToken()) || "test";
        const calendarActivity = await getActivityCalendar(
          token,
          getCurrentMonthRange()
        );

        if (!isMounted) {
          return;
        }

        setCurrentStreak(calendarActivity.currentStreak);
        setActiveDaysCount((calendarActivity.days || []).length);
      } catch (error) {
        if (isMounted) {
          setActivityError(error.message || "Unable to load activity.");
        }
      }
    }

    loadActivityCalendar();

    return () => {
      isMounted = false;
    };
  }, [getToken, isLoaded, isSignedIn]);

  const dashboardStats = useMemo(
    () => [
      ...statCards,
      {
        label: "Current streak",
        value: `${currentStreak ?? "—"} days`,
        helper: activityError || "Keep the habit going",
      },
    ],
    [activityError, currentStreak]
  );

  return (
    <main className="student-dashboard-page">
      <aside className="student-dashboard-sidebar">
        <div className="dashboard-brand">
          <img
            src={capiCoffeeIcon}
            alt=""
            className="dashboard-brand-icon"
            aria-hidden="true"
          />
          <span>CapiLearn</span>
        </div>

        <nav className="dashboard-nav">
          <button className="active">Overview</button>
          <button>Lessons</button>
          <button>Questions</button>
          <button>Progress</button>
        </nav>

        <div className="dashboard-profile-card">
          <div className="dashboard-avatar">J</div>
          <div>
            <h3>Jose</h3>
            <p>FCF Student</p>
          </div>
        </div>
      </aside>

      <section className="student-dashboard-main">
        <header className="student-dashboard-header">
          <div>
            <p className="dashboard-kicker">Student Dashboard</p>
            <h1>Your learning progress</h1>
            <p>
              Track your study activity, review progress, and see where to focus
              next.
            </p>
          </div>

          <Link className="return-button" to="/workspace">
              Return to workspace
          </Link>
        </header>

        <section className="dashboard-stat-grid">
          {dashboardStats.map((stat) => (
            <article className="dashboard-stat-card" key={stat.label}>
              <p>{stat.label}</p>
              <h2>{stat.value}</h2>
              <span>{stat.helper}</span>
            </article>
          ))}
        </section>

        <section className="dashboard-content-grid">
          <article className="dashboard-panel module-panel">
            <div className="panel-header">
              <div>
                <p className="panel-label">Course Progress</p>
                <h2>Learning modules</h2>
              </div>
              <span>{activeDaysCount ?? "—"} active this month</span>
            </div>

            <div className="module-list">
              {modules.map((module) => (
                <div className="module-item" key={module.title}>
                  <div className="module-info">
                    <h3>{module.title}</h3>
                    <p>{module.status}</p>
                  </div>

                  <div className="module-progress-block">
                    <span>{module.progress}%</span>
                    <div className="module-progress-bar">
                      <div
                        className="module-progress-fill"
                        style={{ width: `${module.progress}%` }}
                      ></div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </article>

          <aside className="dashboard-side-stack">
            <article className="dashboard-panel focus-panel">
              <p className="panel-label">Recommended focus</p>
              <h2>Topics to revisit</h2>

              <div className="focus-tags">
                {focusAreas.map((area) => (
                  <span key={area}>{area}</span>
                ))}
              </div>

              <p className="focus-note">
                These are based on recent questions and unfinished lessons.
              </p>
            </article>

            <article className="dashboard-panel activity-panel">
              <p className="panel-label">Recent activity</p>
              <h2>Latest learning moments</h2>

              <ul>
                {recentActivity.map((activity) => (
                  <li key={activity}>{activity}</li>
                ))}
              </ul>
            </article>
          </aside>
        </section>
      </section>
    </main>
  );
}

export default StudentDashboard;