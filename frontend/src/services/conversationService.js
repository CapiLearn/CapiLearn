import { API_BASE_URL, handleApiResponse } from "./apiClient";

/**
 * Conversation service wraps the student chat API.
 *
 * The live path sends Clerk bearer tokens to conversation and message endpoints
 * so the backend can persist authenticated user messages and assistant replies.
 */
// Disabled by default; retained only as a local UI fallback when the backend is
// intentionally unavailable during manual frontend work.
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

/**
 * Lists saved conversations for the current user.
 *
 * @param {Function} getToken - Clerk token getter used for authenticated requests.
 * @returns {Promise<Object>} Object containing a conversations array.
 */
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

/**
 * Creates a new conversation from the student's first message.
 *
 * @param {string} content - Initial message submitted by the student.
 * @param {Function} getToken - Clerk token getter used for authenticated requests.
 * @returns {Promise<Object>} Created conversation response.
 */
export async function createConversation(content, getToken) {
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

/**
 * Loads all messages for a selected conversation.
 *
 * @param {string} conversationId - ID of the conversation to load.
 * @param {Function} getToken - Clerk token getter used for authenticated requests.
 * @returns {Promise<Object>} Object containing a messages array.
 */
export async function listMessages(conversationId, getToken) {
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

/**
 * Sends a follow-up message in an existing conversation.
 *
 * The backend response includes the saved user message and generated
 * assistant message for the active conversation.
 *
 * @param {string} conversationId - ID of the active conversation.
 * @param {string} content - Message submitted by the student.
 * @param {Function} getToken - Clerk token getter used for authenticated requests.
 * @returns {Promise<Object>} Message creation response.
 */
export async function createMessage(conversationId, content, getToken) {
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
