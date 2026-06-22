import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  getAdminSystemHealth,
  getAdminUsageSummary,
} from "../services/adminService";
import "../styles/AdminDashboard.css";
import { useAuth } from "@clerk/react";
import LogoutButton from "../components/LogoutButton";

const adminNavItems = [
  { id: "overview", label: "System Overview", status: "available" },
  { id: "users", label: "Users", status: "coming-soon" },
  { id: "ingestion", label: "Ingestion", status: "coming-soon" },
  { id: "guardrails", label: "Guardrails", status: "coming-soon" },
  { id: "logs", label: "Logs", status: "coming-soon" },
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

function addUtcCalendarDay(dateString) {
  const date = new Date(`${dateString}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + 1);

  return date.toISOString().slice(0, 10);
}

function getDefaultDateRange() {
  const today = new Date();
  const fromDate = new Date();

  fromDate.setDate(today.getDate() - 7);

  return {
    fromDate: fromDate.toISOString().slice(0, 10),
    toDate: today.toISOString().slice(0, 10),
  };
}

function getStatusClass(status) {
  if (status === "healthy") {
    return "admin-status-good";
  }

  if (status === "warning" || status === "unknown") {
    return "admin-status-warning";
  }

  return "admin-status-danger";
}

function formatStatus(status) {
  if (!status) {
    return "Unknown";
  }

  return status.charAt(0).toUpperCase() + status.slice(1);
}

function formatCheckedAt(checkedAt) {
  if (!checkedAt) {
    return "Not checked yet";
  }

  return new Date(checkedAt).toLocaleString();
}

function formatDetailValue(value) {
  if (value === null || value === undefined) {
    return "Unavailable";
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
}

function formatDetailLabel(label) {
  return label
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, (character) => character.toUpperCase());
}

function AdminDashboard() {
  const [usageSummary, setUsageSummary] = useState(null);
  const [systemHealth, setSystemHealth] = useState(null);
  const [isLoadingUsage, setIsLoadingUsage] = useState(false);
  const [isLoadingSystemHealth, setIsLoadingSystemHealth] = useState(false);
  const [usageErrorMessage, setUsageErrorMessage] = useState("");
  const [systemHealthErrorMessage, setSystemHealthErrorMessage] = useState("");
  const [metricsDateRange, setMetricsDateRange] = useState(getDefaultDateRange);
  const isMetricsDateRangeInvalid =
    metricsDateRange.fromDate &&
    metricsDateRange.toDate &&
    metricsDateRange.fromDate > metricsDateRange.toDate;
  const { getToken } = useAuth();  

  useEffect(() => {
    async function loadUsageSummary() {
      if (isMetricsDateRangeInvalid) {
        setUsageErrorMessage("Start date must be before or equal to end date.");
        return;
      }

      try {
        setIsLoadingUsage(true);
        setUsageErrorMessage("");

        const apiDateRange = {
          fromDate: metricsDateRange.fromDate,
          toDate: addUtcCalendarDay(metricsDateRange.toDate),
        };

        const data = await getAdminUsageSummary(getToken, apiDateRange);

        setUsageSummary(data);
      } catch (error) {
        setUsageErrorMessage(
          error.message || "Unable to load admin usage data."
        );
      } finally {
        setIsLoadingUsage(false);
      }
    }

    loadUsageSummary();
  }, [getToken, metricsDateRange, isMetricsDateRangeInvalid]);

  useEffect(() => {
    async function loadSystemHealth() {
      try {
        setIsLoadingSystemHealth(true);
        setSystemHealthErrorMessage("");

        const data = await getAdminSystemHealth(getToken);

        setSystemHealth(data);
      } catch (error) {
        setSystemHealthErrorMessage(
          error.message || "Unable to load system health."
        );
      } finally {
        setIsLoadingSystemHealth(false);
      }
    }

    loadSystemHealth();
  }, [getToken]);

  const metrics = usageSummary?.metrics;
  const healthChecks = systemHealth?.checks || [];

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
        metrics?.averageLatencyMs !== null &&
        metrics?.averageLatencyMs !== undefined
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
          {adminNavItems.map((item) => (
            <button
              className={item.id === "overview" ? "active" : ""}
              disabled={item.status === "coming-soon"}
              key={item.id}
              type="button"
            >
              <span>{item.label}</span>

              {item.status === "coming-soon" && (
                <small> Coming soon</small>
              )}
            </button>
          ))}
        </nav>

        <LogoutButton className="admin-logout-link" />

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

        {isLoadingUsage && (
          <p className="admin-helper-message">Loading admin usage data...</p>
        )}

        {usageErrorMessage && (
          <p className="admin-error-message">{usageErrorMessage}</p>
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

              <span
                className={`admin-overall-status ${getStatusClass(
                  systemHealth?.overallStatus || "unknown"
                )}`}
              >
                {formatStatus(systemHealth?.overallStatus || "unknown")}
              </span>
            </div>

            <p className="admin-checked-at">
              Last checked: {formatCheckedAt(systemHealth?.checkedAt)}
            </p>

            {isLoadingSystemHealth && (
              <p className="admin-helper-message">Loading system health...</p>
            )}

            {systemHealthErrorMessage && (
              <p className="admin-error-message">{systemHealthErrorMessage}</p>
            )}

            {!isLoadingSystemHealth &&
              !systemHealthErrorMessage &&
              healthChecks.length === 0 && (
                <p className="admin-helper-message">
                  No system health checks available.
                </p>
              )}

            <div className="service-list">
              {healthChecks.map((check) => (
                <div className="service-row" key={check.id}>
                  <div className="service-row-content">
                    <div className="service-row-heading">
                      <h3>{check.name}</h3>

                      <span
                        className={`admin-status-pill ${getStatusClass(
                          check.status
                        )}`}
                      >
                        {formatStatus(check.status)}
                      </span>
                    </div>

                    <p>{check.message}</p>

                    {check.latencyMs !== null && check.latencyMs !== undefined && (
                      <p className="service-latency">Latency: {check.latencyMs} ms</p>
                    )}

                    {check.details &&
                      Object.keys(check.details).length > 0 && (
                        <dl className="service-details-list">
                          {Object.entries(check.details).map(([key, value]) => (
                            <div className="service-detail-item" key={key}>
                              <dt>{formatDetailLabel(key)}</dt>
                              <dd>{formatDetailValue(value)}</dd>
                            </div>
                          ))}
                        </dl>
                      )}
                  </div>
                </div>
              ))}
            </div>
          </article>

          <aside className="admin-side-stack">
            <article className="admin-panel">
              <p className="admin-panel-label">Usage Details</p>
              <h2>Response and cost metrics</h2>

              <div className="metrics-date-controls">
                <label>
                  From
                  <input
                    type="date"
                    value={metricsDateRange.fromDate}
                    max={metricsDateRange.toDate}
                    onChange={(event) =>
                      setMetricsDateRange((currentRange) => ({
                        ...currentRange,
                        fromDate: event.target.value,
                      }))
                    }
                  />
                </label>

                <label>
                  To
                  <input
                    type="date"
                    value={metricsDateRange.toDate}
                    min={metricsDateRange.fromDate}
                    onChange={(event) =>
                      setMetricsDateRange((currentRange) => ({
                        ...currentRange,
                        toDate: event.target.value,
                      }))
                    }
                  />
                </label>
              </div>

              {isMetricsDateRangeInvalid && (
                <p className="metrics-date-error">
                  Start date must be before or equal to end date.
                </p>
              )}

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