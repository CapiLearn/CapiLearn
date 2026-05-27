import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { getAdminUsageSummary } from "../services/adminService";
import "../styles/AdminDashboard.css";

const serviceChecks = [
  {
    service: "FastAPI Backend",
    status: "Healthy",
    detail: "Last checked 2 minutes ago",
  },
  {
    service: "Postgres + pgvector",
    status: "Healthy",
    detail: "Database accepts connections",
  },
  {
    service: "RAG Index",
    status: "Warning",
    detail: "6 documents failed processing",
  },
  {
    service: "LLM Gateway",
    status: "Healthy",
    detail: "Provider response available",
  },
  {
    service: "Guardrails",
    status: "Healthy",
    detail: "Prompt safety checks enabled",
  },
];

const recentEvents = [
  {
    event: "Postgres health check passed",
    time: "2 minutes ago",
    type: "System",
  },
  {
    event: "6 documents failed ingestion",
    time: "15 minutes ago",
    type: "Ingestion",
  },
  {
    event: "LLM provider returned successful response",
    time: "22 minutes ago",
    type: "LLM",
  },
  {
    event: "Guardrails blocked unsafe direct-answer request",
    time: "35 minutes ago",
    type: "Safety",
  },
];

function getStatusClass(status) {
  if (status === "Healthy") {
    return "admin-status-good";
  }

  if (status === "Warning") {
    return "admin-status-warning";
  }

  return "admin-status-danger";
}

/**
 * Admin dashboard page for operational usage metrics.
 *
 * Loads aggregate platform usage data from the admin API and displays
 * high-level metrics such as users, conversations, queries, responses,
 * failures, blocked responses, token usage, cost, and latency.
 */

function AdminDashboard() {
  const [usageSummary, setUsageSummary] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  
  useEffect(() => {
    async function loadUsageSummary() {
      try {
        setIsLoading(true);
        setErrorMessage("");

        const data = await getAdminUsageSummary();

        setUsageSummary(data);
      } catch (error) {
        setErrorMessage(error.message || "Unable to load admin usage data.");
      } finally {
        setIsLoading(false);
      }
    }

    loadUsageSummary();
  }, []);

  const metrics = usageSummary?.metrics;

  const usageStats = [
  {
    label: "Total users",
    value: metrics?.totalUsers ?? "--",
    helper: "Users active in selected range",
    status: "healthy",
  },
  {
    label: "Conversations",
    value: metrics?.totalConversations ?? "--",
    helper: "Conversation sessions created",
    status: "healthy",
  },
  {
    label: "User queries",
    value: metrics?.userQueries ?? "--",
    helper: "Student messages submitted",
    status: "healthy",
  },
  {
    label: "Assistant responses",
    value: metrics?.assistantResponses ?? "--",
    helper: "Responses returned by assistant",
    status: "healthy",
  },
];

  const operationalStats = [
  {
    label: "Failed responses",
    value: metrics?.failedResponses ?? "--",
    helper: "Assistant responses marked as failed",
  },
  {
    label: "Blocked responses",
    value: metrics?.blockedResponses ?? "--",
    helper: "Assistant responses blocked by safety rules",
  },
  {
    label: "Total tokens",
    value: metrics?.totalTokens?.toLocaleString() ?? "--",
    helper: "Total token usage in selected range",
  },
  {
    label: "Estimated cost",
    value: metrics?.estimatedCostUsd
      ? `$${Number(metrics.estimatedCostUsd).toFixed(4)}`
      : "--",
    helper: "Estimated provider cost",
  },
  {
    label: "Average latency",
    value:
      metrics?.averageLatencyMs !== null && metrics?.averageLatencyMs !== undefined
        ? `${metrics.averageLatencyMs} ms`
        : "Unavailable",
    helper: "Average response latency",
  },
];

  return (
    <main className="admin-page">
      <aside className="admin-sidebar">
        <div className="admin-brand">
          <div className="admin-brand-icon">♧</div>
          <span>CapiLearn</span>
        </div>

        <nav className="admin-nav">
          <button className="active">System Overview</button>
          <button>Users</button>
          <button>Ingestion</button>
          <button>Guardrails</button>
          <button>Logs</button>
        </nav>

        <Link className="admin-logout-link" to="/">
          Log out
        </Link>

        <div className="admin-profile-card">
          <div className="admin-avatar">A</div>
          <div>
            <h3>Admin</h3>
            <p>System Manager</p>
          </div>
        </div>
      </aside>

      <section className="admin-main">
        <header className="admin-header">
          <div>
            <p className="admin-kicker">Administrator Dashboard</p>
            <h1>System operations</h1>
            <p>
              Monitor service health, ingestion status, safety checks, and
              platform readiness.
            </p>
          </div>

          <Link className="admin-secondary-link" to="/instructor-dashboard">
            Instructor view
          </Link>
        </header>

        {isLoading && (
          <p className="admin-helper-message">Loading admin usage data...</p>
        )}

        {errorMessage && (
          <p className="admin-error-message">{errorMessage}</p>
        )}

        <section className="admin-stat-grid">
          {usageStats.map((stat) => (
            <article className="admin-stat-card" key={stat.label}>
              <div className={`admin-status-dot ${stat.status}`}></div>
              <p>{stat.label}</p>
              <h2>{stat.value}</h2>
              <span>{stat.helper}</span>
            </article>
          ))}
        </section>

        <section className="admin-content-grid">
          <article className="admin-panel">
            <div className="admin-panel-header">
              <div>
                <p className="admin-panel-label">Service Health</p>
                <h2>Core system checks</h2>
              </div>
              <span>Live status</span>
            </div>

            <div className="service-list">
              {serviceChecks.map((check) => (
                <div className="service-row" key={check.service}>
                  <div>
                    <h3>{check.service}</h3>
                    <p>{check.detail}</p>
                  </div>

                  <span className={`admin-status-pill ${getStatusClass(check.status)}`}>
                    {check.status}
                  </span>
                </div>
              ))}
            </div>
          </article>

          <aside className="admin-side-stack">
            <article className="admin-panel">
              <p className="admin-panel-label">Usage Details</p>
              <h2>Response and cost metrics</h2>

              <div className="usage-detail-list">
                {operationalStats.map((item) => (
                  <div className="usage-detail-item" key={item.label}>
                    <p>{item.label}</p>
                    <h3>{item.value}</h3>
                    <span>{item.helper}</span>
                  </div>
                ))}
              </div>
            </article>

            <article className="admin-panel admin-safety-card">
              <p className="admin-panel-label">Safety</p>
              <h2>Guided learning mode active</h2>
              <p>
                The assistant is configured to guide students with hints and
                questions instead of giving direct answers.
              </p>
            </article>
          </aside>
        </section>

        <section className="admin-panel events-panel">
          <div className="admin-panel-header">
            <div>
              <p className="admin-panel-label">Recent Events</p>
              <h2>Operational activity</h2>
            </div>
            <button className="admin-outline-button">View all logs</button>
          </div>

          <div className="events-table-wrapper">
            <table className="events-table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Type</th>
                  <th>Time</th>
                </tr>
              </thead>

              <tbody>
                {recentEvents.map((event) => (
                  <tr key={`${event.event}-${event.time}`}>
                    <td>{event.event}</td>
                    <td>
                      <span className="event-type-pill">{event.type}</span>
                    </td>
                    <td>{event.time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}

export default AdminDashboard;
