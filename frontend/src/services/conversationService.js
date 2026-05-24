const API_BASE_URL = "http://localhost:8001";

// Set to true while backend branch is unavailable.
// Change to false when backend is running locally.
const USE_MOCK_API = false;
const mockConversations = [];
const mockMessagesByConversationId = {};

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

  const conversation = {
    id: conversationId,
    title: content,
    updatedAt: timestamp,
  };

  const userMessage = {
    id: createMockId("user-message"),
    conversationId,
    role: "user",
    content,
    status: "completed",
    createdAt: timestamp,
  };

  const assistantMessage = {
    id: createMockId("assistant-message"),
    conversationId,
    role: "assistant",
    content: createMockAssistantReply(content),
    status: "completed",
    createdAt: createMockTimestamp(),
  };

  mockConversations.unshift(conversation);
  mockMessagesByConversationId[conversationId] = [userMessage, assistantMessage];

  return {
    conversation,
    userMessage,
    assistantMessage,
    finishReason: "mock",
    blockedReason: null,
  };
}

async function mockCreateMessage(conversationId, content) {
  const timestamp = createMockTimestamp();

  const userMessage = {
    id: createMockId("user-message"),
    conversationId,
    role: "user",
    content,
    status: "completed",
    createdAt: timestamp,
  };

  const assistantMessage = {
    id: createMockId("assistant-message"),
    conversationId,
    role: "assistant",
    content: createMockAssistantReply(content),
    status: "completed",
    createdAt: createMockTimestamp(),
  };

  if (!mockMessagesByConversationId[conversationId]) {
    mockMessagesByConversationId[conversationId] = [];
  }

  mockMessagesByConversationId[conversationId].push(userMessage, assistantMessage);

  const conversation = mockConversations.find(
    (item) => item.id === conversationId
  );

  if (conversation) {
    conversation.updatedAt = createMockTimestamp();
  }

  return {
    conversation: conversation || {
      id: conversationId,
      title: null,
      updatedAt: createMockTimestamp(),
    },
    userMessage,
    assistantMessage,
    finishReason: "mock",
    blockedReason: null,
  };
}

async function mockListMessages(conversationId) {
  return {
    messages: mockMessagesByConversationId[conversationId] || [],
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
      conversations: [...mockConversations],
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
    return mockListMessages(conversationId);
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