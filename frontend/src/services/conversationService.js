import { getToken } from "@clerk/react";
import { API_BASE_URL, handleApiResponse } from "./apiClient";

// Set to true while backend branch is unavailable.
// Change to false when backend is running locally.
const USE_MOCK_API = false;
const mockConversations = [];
const mockMessagesByConversationId = {};

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

async function authFetch(path, getToken, options = {}) {
  const token = await getToken();

  if (!token) {
    throw new Error("Not authenticated.");
  }

  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${token}`);

  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
}

export async function listConversations(getToken) {
  if (USE_MOCK_API) {
    return {
      conversations: [...mockConversations],
    };
  }

  const response = await authFetch("/api/conversations", getToken, {
        method: "GET",
  });

  return handleApiResponse(response, "Unable to load conversations.");
}

export async function createConversation(content) {
  if (USE_MOCK_API) {
    return mockCreateConversation(content, getToken);
  }

  const response = await authFetch("/api/conversations", getToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      content,
    }),
  });

  return handleApiResponse(response, "Unable to create conversation.");
}

export async function listMessages(conversationId) {
  if (USE_MOCK_API) {
    return mockListMessages(conversationId);
  }

  const response = await authFetch(
    `/api/conversations/${conversationId}/messages`,
    getToken,
    {
      method: "GET",
    }
  );

  return handleApiResponse(response, "Unable to load conversation messages.");
}

export async function createMessage(conversationId, content) {
  if (USE_MOCK_API) {
    return mockCreateMessage(conversationId, content);
  }

  const response = await authFetch(
    `/api/conversations/${conversationId}/messages`,
    getToken,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        content,
      }),
    }
  );

  return handleApiResponse(response, "Unable to send message.");
}