const API_BASE_URL = "http://localhost:8000";

// Set to true while backend branch is unavailable.
// Change to false when backend is running locally.
const USE_MOCK_API = true;

const DEV_USER_HEADERS = {
  "X-User-Id": "00000000-0000-0000-0000-000000000001",
  "X-User-Email": "student@example.com",
};

function createMockId(prefix) {
  return `${prefix}-${crypto.randomUUID()}`;
}

function createMockTimestamp() {
  return new Date().toISOString();
}

function createMockAssistantReply(content) {
  return `Let's slow it down. You asked: "${content}". What part feels unclear: the concept, the instructions, or what you have already tried?`;
}

async function mockCreateConversation(content) {
  const conversationId = createMockId("conversation");
  const timestamp = createMockTimestamp();

  return {
    conversation: {
      id: conversationId,
      title: content,
      updatedAt: timestamp,
    },
    userMessage: {
      id: createMockId("user-message"),
      conversationId,
      role: "user",
      content,
      status: "completed",
      createdAt: timestamp,
    },
    assistantMessage: {
      id: createMockId("assistant-message"),
      conversationId,
      role: "assistant",
      content: createMockAssistantReply(content),
      status: "completed",
      createdAt: createMockTimestamp(),
    },
    finishReason: "mock",
    blockedReason: null,
  };
}

async function mockCreateMessage(conversationId, content) {
  const timestamp = createMockTimestamp();

  return {
    conversation: {
      id: conversationId,
      title: null,
      updatedAt: timestamp,
    },
    userMessage: {
      id: createMockId("user-message"),
      conversationId,
      role: "user",
      content,
      status: "completed",
      createdAt: timestamp,
    },
    assistantMessage: {
      id: createMockId("assistant-message"),
      conversationId,
      role: "assistant",
      content: createMockAssistantReply(content),
      status: "completed",
      createdAt: createMockTimestamp(),
    },
    finishReason: "mock",
    blockedReason: null,
  };
}

async function handleResponse(response) {
  if (!response.ok) {
    let errorData = null;

    try {
      errorData = await response.json();
    } catch {
      errorData = {
        code: "unknown_error",
        message: "Something went wrong.",
        details: null,
      };
    }

    throw new Error(errorData.message || "Request failed.");
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export async function listConversations() {
  if (USE_MOCK_API) {
    return {
      conversations: [],
    };
  }

  const response = await fetch(`${API_BASE_URL}/api/conversations`, {
    method: "GET",
    headers: {
      ...DEV_USER_HEADERS,
    },
  });

  return handleResponse(response);
}

export async function createConversation(content) {
  if (USE_MOCK_API) {
    return mockCreateConversation(content);
  }

  const response = await fetch(`${API_BASE_URL}/api/conversations`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...DEV_USER_HEADERS,
    },
    body: JSON.stringify({
      content,
    }),
  });

  return handleResponse(response);
}

export async function listMessages(conversationId) {
  if (USE_MOCK_API) {
    return {
      messages: [],
    };
  }

  const response = await fetch(
    `${API_BASE_URL}/api/conversations/${conversationId}/messages`,
    {
      method: "GET",
      headers: {
        ...DEV_USER_HEADERS,
      },
    }
  );

  return handleResponse(response);
}

export async function createMessage(conversationId, content) {
  if (USE_MOCK_API) {
    return mockCreateMessage(conversationId, content);
  }

  const response = await fetch(
    `${API_BASE_URL}/api/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...DEV_USER_HEADERS,
      },
      body: JSON.stringify({
        content,
      }),
    }
  );

  return handleResponse(response);
}