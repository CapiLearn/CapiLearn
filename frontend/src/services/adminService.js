const API_BASE_URL = "http://127.0.0.1:8001";

const USE_MOCK_ADMIN_API = false;

const ADMIN_HEADERS = {
  "X-Admin-User": "true",
  "X-User-Id": "00000000-0000-0000-0000-000000000001",
  "X-User-Email": "instructor@example.com",
};

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

async function handleResponse(response) {
  if (!response.ok) {
    try {
      const errorData = await response.json();
      throw new Error(
        errorData.message || "Unable to load admin usage summary."
      );
    } catch {
      throw new Error("Unable to load admin usage summary.");
    }
  }

  return response.json();
}

export async function getAdminUsageSummary({ fromDate, toDate } = {}) {
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

  const response = await fetch(url, {
    method: "GET",
    headers: ADMIN_HEADERS,
  });

  return handleResponse(response);
}