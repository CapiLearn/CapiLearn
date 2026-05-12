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
  {
    label: "Current streak",
    value: "5 days",
    helper: "Keep the habit going",
  },
];

const modules = [
  {
    title: "Intro to Machine Learning",
    progress: 90,
    status: "Almost complete",
  },
  {
    title: "Model Evaluation",
    progress: 72,
    status: "In progress",
  },
  {
    title: "RAG Systems",
    progress: 55,
    status: "Needs review",
  },
  {
    title: "Guardrails and Safety",
    progress: 38,
    status: "Started",
  },
];

const recentActivity = [
  "Asked for help understanding model evaluation metrics",
  "Reviewed lesson: RAG retrieval flow",
  "Completed guided reflection on overfitting",
  "Started lesson: Guardrails and bad outputs",
];

const focusAreas = [
  "RAG evaluation",
  "Model monitoring",
  "Prompt guardrails",
];

function StudentDashboard() {
  return (
    <main className="student-dashboard-page">
      <aside className="student-dashboard-sidebar">
        <div className="dashboard-brand">
          <div className="dashboard-brand-icon">♧</div>
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

          <button className="return-button">Return to workspace</button>
        </header>

        <section className="dashboard-stat-grid">
          {statCards.map((stat) => (
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
              <span>4 active</span>
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