import { API_BASE_URL, handleApiResponse } from "./apiClient";

const USE_MOCK_ADMIN_API = false;

const mockAdminUsageSummary = {
  range: {
    fromDate: "2026-05-01",
    toDate: "2026-05-19",
  },
  metrics: {
    totalUsers: 18,
    totalConversations: 47,
    userQueries: 142,
    assistantResponses: 139,
    failedResponses: 3,
    blockedResponses: 4,
    totalTokens: 89321,
    estimatedCostUsd: "1.284500",
    averageLatencyMs: 1830,
  },
  dailyUsage: [
    {
      date: "2026-05-17",
      userQueries: 19,
      assistantResponses: 19,
      totalTokens: 8820,
    },
    {
      date: "2026-05-18",
      userQueries: 24,
      assistantResponses: 23,
      totalTokens: 12450,
    },
  ],
};

const mockAdminSystemHealth = {
  overallStatus: "warning",
  checkedAt: "2026-06-07T12:00:00Z",
  checks: [
    {
      id: "backend",
      name: "FastAPI Backend",
      status: "healthy",
      message: "API is running.",
      details: {
        service: "FastAPI",
        endpoint: "/api/admin/system-health",
      },
    },
    {
      id: "database",
      name: "Postgres + pgvector",
      status: "healthy",
      message: "Database accepts connections and pgvector is available.",
      details: {
        databaseConnected: true,
        pgvectorAvailable: true,
      },
    },
    {
      id: "rag",
      name: "RAG Index",
      status: "warning",
      message: "6 documents failed processing.",
      details: {
        indexReady: true,
        documentsProcessed: 118,
        documentsFailed: 6,
        lastIngestionRun: "2026-06-07T11:30:00Z",
      },
    },
    {
      id: "llm",
      name: "LLM Gateway",
      status: "healthy",
      message: "Provider configuration is available.",
      details: {
        providerConfigured: true,
        provider: "openrouter",
        modelConfigured: true,
      },
    },
    {
      id: "guardrails",
      name: "Guardrails",
      status: "healthy",
      message: "Guardrails are enabled.",
      details: {
        enabled: true,
      },
    },
  ],
};

async function authFetch(url, getToken, options = {}) {
  const token = await getToken();

  if (!token) {
    throw new Error("Not authenticated.");
  }

  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${token}`);

  return fetch(url, {
    ...options,
    headers,
  });
}

export async function getAdminUsageSummary( getToken, { fromDate, toDate } = {}) {
  if (USE_MOCK_ADMIN_API) {
    return mockAdminUsageSummary;
  }

  const params = new URLSearchParams();

  if (fromDate) {
    params.set("fromDate", fromDate);
  }

  if (toDate) {
    params.set("toDate", toDate);
  }

  const queryString = params.toString();

  const url = queryString
    ? `${API_BASE_URL}/api/admin/usage/summary?${queryString}`
    : `${API_BASE_URL}/api/admin/usage/summary`;

  const response = await authFetch(url, getToken, {
    method: "GET",
  });

  return handleApiResponse(response, "Unable to load admin usage summary.");
}

function mapHealthStatus(status) {
  if (status === "ok" || status === "healthy") {
    return "healthy";
  }

  if (status === "degraded" || status === "warning") {
    return "warning";
  }

  if (status === "unhealthy") {
    return "unhealthy";
  }

  return "unknown";
}

function createHealthCheckId(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function normalizeSystemHealthResponse(data) {
  return {
    overallStatus: mapHealthStatus(data.status),
    checkedAt: data.checkedAt,
    checks: (data.checks || []).map((check) => ({
      id: createHealthCheckId(check.name),
      name: check.name,
      status: mapHealthStatus(check.status),
      message: check.message,
      latencyMs: check.latencyMs,
      details: check.details || {},
    })),
  };
}

export async function getAdminSystemHealth(getToken) {
  if (USE_MOCK_ADMIN_API) {
    return mockAdminSystemHealth;
  }

  const response = await authFetch(`${API_BASE_URL}/api/admin/health`, getToken, {
    method: "GET",
  });

  const data = await handleApiResponse(
    response,
    "Unable to load system health."
  );

  return normalizeSystemHealthResponse(data);
}