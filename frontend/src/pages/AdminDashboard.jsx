import { useEffect, useState } from "react";
import {
  getAdminSystemHealth,
  getAdminUsageSummary,
  getAdminUsersOverview,
} from "../services/adminService";
import "../styles/AdminDashboard.css";
import { useAuth } from "@clerk/react";
import LogoutButton from "../components/LogoutButton";
import capiCoffeeIcon from "../assets/capi_coffee_icon.png";

const adminNavItems = [
  { id: "overview", label: "System Overview" },
  { id: "users", label: "Users" },
];

/**
 * AdminDashboard is the reviewer-facing operations view.
 *
 * It reads authenticated admin metrics, health checks, and user activity from
 * backend admin endpoints so deployment reviewers can verify API, database,
 * RAG, guardrail, and usage signals from one screen.
 */
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

function formatDateTime(value) {
  if (!value) {
    return "No activity yet";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }

  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
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

function formatAccessLevel(accessLevel) {
  if (!accessLevel) {
    return "Unknown";
  }

  return accessLevel.charAt(0).toUpperCase() + accessLevel.slice(1);
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

const hiddenHealthDetailKeys = new Set([
  // Hide backend RAG index metadata from the admin health cards.
  "indexVersion",
]);

function getVisibleDetailEntries(details) {
  return Object.entries(details || {}).filter(
    ([key]) => !hiddenHealthDetailKeys.has(key)
  );
}

/**
 * Admin dashboard page for operational usage metrics.
 *
 * Loads aggregate platform usage data from the admin API and displays
 * high-level metrics such as users, conversations, queries, responses,
 * failures, blocked responses, token usage, cost, latency, system health,
 * and user activity summaries.
 */

function AdminDashboard() {
  const [usageSummary, setUsageSummary] = useState(null);
  const [systemHealth, setSystemHealth] = useState(null);
  const [isLoadingUsage, setIsLoadingUsage] = useState(false);
  const [isLoadingSystemHealth, setIsLoadingSystemHealth] = useState(false);
  const [usageErrorMessage, setUsageErrorMessage] = useState("");
  const [systemHealthErrorMessage, setSystemHealthErrorMessage] = useState("");
  const [activeAdminSection, setActiveAdminSection] = useState("overview");
  const [adminUsers, setAdminUsers] = useState([]);
  const [isLoadingAdminUsers, setIsLoadingAdminUsers] = useState(false);
  const [adminUsersErrorMessage, setAdminUsersErrorMessage] = useState("");
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

  useEffect(() => {
    if (activeAdminSection !== "users") {
      return;
    }

    async function loadAdminUsers() {
      if (isMetricsDateRangeInvalid) {
        setAdminUsersErrorMessage(
          "Start date must be before or equal to end date."
        );
        return;
      }

      try {
        setIsLoadingAdminUsers(true);
        setAdminUsersErrorMessage("");

        const apiDateRange = {
          fromDate: metricsDateRange.fromDate,
          toDate: addUtcCalendarDay(metricsDateRange.toDate),
          limit: 25,
          offset: 0,
        };

        const data = await getAdminUsersOverview(getToken, apiDateRange);

        setAdminUsers(data.users || []);
      } catch (error) {
        setAdminUsersErrorMessage(
          error.message || "Unable to load admin users."
        );
      } finally {
        setIsLoadingAdminUsers(false);
      }
    }

    loadAdminUsers();
  }, [
    activeAdminSection,
    getToken,
    metricsDateRange,
    isMetricsDateRangeInvalid,
  ]);

  const metrics = usageSummary?.metrics;
  const healthChecks = (systemHealth?.checks || []).map((check) => ({
    ...check,
    detailEntries: getVisibleDetailEntries(check.details),
  }));

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
          <img
            src={capiCoffeeIcon}
            alt=""
            className="admin-brand-icon"
            aria-hidden="true"
          />
          <span>CapiLearn</span>
        </div>

        <nav className="admin-nav">
          {adminNavItems.map((item) => (
            <button
              className={activeAdminSection === item.id ? "active" : ""}
              key={item.id}
              type="button"
              onClick={() => setActiveAdminSection(item.id)}
            >
              <span>{item.label}</span>
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

            <h1>
              {activeAdminSection === "users" ? "Users" : "System Operations"}
            </h1>
            <p>
              {activeAdminSection === "users"
                ? "Review user access levels, message volume, blocked requests, and latest activity."
                : "Monitor service health, ingestion status, safety checks, and platform readiness."}
            </p>
          </div>

        </header>

        {activeAdminSection === "overview" && (
          <>

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
                <h2>Core System Checks</h2>
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

                    {check.detailEntries.length > 0 && (
                      <dl className="service-details-list">
                        {check.detailEntries.map(([key, value]) => (
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
              <h2>Response and Cost Metrics</h2>

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
          </>
        )}

        {activeAdminSection === "users" && (
          <section className="admin-panel users-panel">
            <div className="admin-panel-header">
              <div>
                <p className="admin-panel-label">Users</p>
                <h2>User access and guardrail usage</h2>
              </div>
              <span>Showing {adminUsers.length} most recent users</span>
            </div>

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

            {isLoadingAdminUsers && (
              <p className="admin-helper-message">Loading admin users...</p>
            )}

            {adminUsersErrorMessage && (
              <p className="admin-error-message">{adminUsersErrorMessage}</p>
            )}

            {!isLoadingAdminUsers &&
              !adminUsersErrorMessage &&
              adminUsers.length === 0 && (
                <p className="admin-helper-message">
                  No admin user activity found for this date range.
                </p>
              )}

            {adminUsers.length > 0 && (
              <div className="users-table-wrapper">
                <table className="users-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Access level</th>
                      <th>Total messages sent</th>
                      <th>Blocked requests</th>
                      <th>Last activity</th>
                    </tr>
                  </thead>

                  <tbody>
                    {adminUsers.map((user, index) => (
                      <tr key={`${user.displayName}-${user.accessLevel}-${index}`}>
                        <td>{user.displayName}</td>
                        <td>
                          <span className="access-level-pill">
                            {formatAccessLevel(user.accessLevel)}
                          </span>
                        </td>
                        <td>
                          {Number(user.totalMessagesSent || 0).toLocaleString()}
                        </td>
                        <td>
                          {Number(user.blockedRequests || 0).toLocaleString()}
                        </td>
                        <td>{formatDateTime(user.lastActivity)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

      </section>
    </main>
  );
}

export default AdminDashboard;
