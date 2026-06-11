import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import MarkdownMessage from "../components/MarkdownMessage";

import { 
  createConversation, 
  createMessage, 
  listConversations, 
  listMessages,
} from "../services/conversationService";

import "../styles/LearningWorkspace.css";

const suggestedPrompts = [
  "Help me understand this lesson",
  "Ask me a guiding question",
  "Point me to the right course material",
  "Help me think through this bug",
];

const calendarDays = [
  "", "", "", "1", "2", "3", "4",
  "5", "6", "7", "8", "9", "10", "11",
  "12", "13", "14", "15", "16", "17", "18",
  "19", "20", "21", "22", "23", "24", "25",
  "26", "27", "28", "29", "30", "31", "",
];

const initialChatMessages = [
  {
    id: "mock-assistant-welcome",
    role: "assistant",
    content:
      "Hi, I’m Capi. What lesson, assignment, or concept would you like help thinking through?",
  },
];

function HighlightedText({ text, searchTerm }) {
  const normalizedSearchTerm = searchTerm.trim();

  if (!normalizedSearchTerm) {
    return text;
  }

  const escapedSearchTerm = normalizedSearchTerm.replace(
    /[.*+?^${}()|[\]\\]/g,
    "\\$&"
  );

  const parts = text.split(new RegExp(`(${escapedSearchTerm})`, "gi"));

  return parts.map((part, index) =>
    part.toLowerCase() === normalizedSearchTerm.toLowerCase() ? (
      <mark className="message-search-highlight" key={`${part}-${index}`}>
        {part}
      </mark>
    ) : (
      part
    )
  );
}

function LearningWorkspace() {
  const [conversationId, setConversationId] = useState(null);

  const [chatMessages, setChatMessages] = useState(initialChatMessages);
  const activeConversationIdRef = useRef(null);

  //State variables

  const [inputValue, setInputValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [conversations, setConversations] = useState([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [messageSearchTerm, setMessageSearchTerm] = useState("");
  const [conversationSearchTerm, setConversationSearchTerm] = useState("");

  useEffect(() => {
    async function loadConversations() {
      try {
        setIsLoadingConversations(true);

        const data = await listConversations();

        setConversations(data.conversations || []);
      } catch (error) {
        setErrorMessage(error.message || "Unable to load conversations.");
      } finally {
        setIsLoadingConversations(false);
      }
    }

    loadConversations();
  }, []);

  async function handleSendMessage(event) {
    event.preventDefault();

    const trimmedMessage = inputValue.trim();

    if (!trimmedMessage) {
      return;
    }

    const targetConversationId = conversationId;

    try {
      setIsSending(true);
      setErrorMessage("");

      if (targetConversationId) {
        const data = await createMessage(targetConversationId, trimmedMessage);

        if (activeConversationIdRef.current === targetConversationId) {
          setChatMessages((currentMessages) => [
            ...currentMessages,
            data.userMessage,
            data.assistantMessage,
          ]);
        }
      } else {
        const data = await createConversation(trimmedMessage);
        const newConversationId = data.conversation.id;

        if (activeConversationIdRef.current === null) {
          activeConversationIdRef.current = newConversationId;
          setConversationId(newConversationId);

          setConversations((currentConversations) => [
            data.conversation,
            ...currentConversations,
          ]);

          setChatMessages([data.userMessage, data.assistantMessage]);
        }
      }

      setInputValue("");
    } catch (error) {
      setErrorMessage(error.message || "Unable to send message.");
    } finally {
      setIsSending(false);
    }
  }
  
  function handleNewConversation() {
    activeConversationIdRef.current = null;
    setConversationId(null);
    setChatMessages([...initialChatMessages]);
    setInputValue("");
    setErrorMessage("");
    setIsLoadingMessages(false);
    setMessageSearchTerm("");
    setConversationSearchTerm("");
  }
      
  async function handleSelectConversation(selectedConversationId) {
    activeConversationIdRef.current = selectedConversationId;
    setConversationId(selectedConversationId);
    setIsLoadingMessages(true);
    setErrorMessage("");
    setMessageSearchTerm("");

    try {
      const data = await listMessages(selectedConversationId);

      if (activeConversationIdRef.current !== selectedConversationId) {
        return;
      }

      setChatMessages(data.messages || []);
    } catch (error) {
      if (activeConversationIdRef.current === selectedConversationId) {
        setErrorMessage(error.message || "Unable to load conversation messages.");
      }
    } finally {
      setIsLoadingMessages(false);
    }
  }

  const normalizedConversationSearchTerm = conversationSearchTerm
    .trim()
    .toLowerCase();

  const filteredConversations = normalizedConversationSearchTerm
    ? conversations.filter((conversation) =>
        (conversation.title || "Untitled conversation")
          .toLowerCase()
          .includes(normalizedConversationSearchTerm)
      )
    : conversations;

  const normalizedSearchTerm = messageSearchTerm.trim().toLowerCase();

  const visibleChatMessages = normalizedSearchTerm
    ? chatMessages.filter((message) =>
        message.content.toLowerCase().includes(normalizedSearchTerm)
      )
    : chatMessages;

  const searchMatchCount = normalizedSearchTerm
  ? chatMessages.reduce((count, message) => {
      const escapedSearchTerm = normalizedSearchTerm.replace(
        /[.*+?^${}()|[\]\\]/g,
        "\\$&"
      );

      const matches = message.content.toLowerCase().match(
        new RegExp(escapedSearchTerm, "g")
      );

      return count + (matches ? matches.length : 0);
    }, 0)
  : 0;

  return (
    <main className="workspace-page">
      <aside className="workspace-sidebar">
        <div className="workspace-brand">
          <div className="workspace-brand-icon">♧</div>
          <span>CapiLearn</span>
        </div>

        <button
          className="new-chat-button"
          type="button"
          onClick={handleNewConversation}
        >
          + New conversation
        </button>

        <div className="search-box">
          <span>⌕</span>
          <input
            type="text"
            placeholder="Search conversations"
            value={conversationSearchTerm}
            onChange={(event) => setConversationSearchTerm(event.target.value)}
          />
        </div>

        <div className="chat-history">
          <section className="chat-group">
            <h3>Conversations</h3>

            {isLoadingConversations && (
              <p className="sidebar-helper-text">Loading conversations...</p>
            )}

            {!isLoadingConversations && conversations.length === 0 && (
              <p className="sidebar-helper-text">No conversations yet.</p>
            )}

            {!isLoadingConversations &&
              conversations.length > 0 &&
              filteredConversations.length === 0 && (
              <p className="sidebar-helper-text">No conversations found.</p>
            )}

            {!isLoadingConversations &&
              filteredConversations.map((conversation) => (
                <button
                  className={`chat-history-item ${
                    conversation.id === conversationId ? "active-conversation" : ""
                  }`}
                  key={conversation.id}
                  type="button"
                  onClick={() => handleSelectConversation(conversation.id)}
                >
                  {conversation.title || "Untitled conversation"}
                </button>
            ))}
             
          </section>
        </div>

        <Link className="workspace-logout-link" to="/">
          Log out
        </Link>

        <div className="student-profile">
          <div className="student-avatar">J</div>
          <div>
            <p>Jose</p>
            <span>FCF Student</span>
          </div>
        </div>
      </aside>

      <section className="workspace-main">
        <header className="workspace-header">
          <div>
            <p className="workspace-kicker">AI Tutor</p>
            <h1>What would you like to learn today?</h1>
          </div>

          <div className="workspace-header-actions">
            <button className="workspace-help-button">Guided mode</button>

            <Link className="workspace-dashboard-link" to="/student-dashboard">
              Dashboard
            </Link>
          </div>
        </header>

        <section className="welcome-card">
          <div className="capi-avatar">🌿</div>

          <div>
            <h2>Hi, I’m Capi.</h2>
            <p>
              I can help you review lessons, reason through problems, and find
              the right course material. I won’t give direct answers, but I’ll
              help you think through the next step.
            </p>
          </div>
        </section>

        <section className="suggested-section">
          <h2>Try asking</h2>

          <div className="prompt-grid">
            {suggestedPrompts.map((prompt) => (
              <button
                className="prompt-card"
                key={prompt}
                type="button"
                onClick={() => setInputValue(prompt)}
              >
                {prompt}
              </button>
            ))}
          </div>
        </section>

        <section className="message-search-section">
          <label htmlFor="message-search">Search current conversation</label>

          <div className="message-search-control">
            <input
              id="message-search"
              type="text"
              placeholder="Search messages..."
              value={messageSearchTerm}
              onChange={(event) => setMessageSearchTerm(event.target.value)}
            />

            {messageSearchTerm && (
              <button
                className="message-search-clear"
                type="button"
                onClick={() => setMessageSearchTerm("")}
              >
                Clear
              </button>
            )}
          </div>

          {normalizedSearchTerm && (
            <span className="message-search-count">
              {searchMatchCount} {searchMatchCount === 1 ? "match" : "matches"}
            </span>
          )}    

        </section>

        <section className="chat-preview">
          {isLoadingMessages && (
            <p className="workspace-loading-message">Loading conversation...</p>
          )}

          {visibleChatMessages.map((message) => (
            <div
              className={`message ${
                message.role === "user" ? "student-message" : "tutor-message"
              }`}
              key={message.id}
            >
              {message.role === "assistant" ? (
                <MarkdownMessage 
                  content={message.content}
                  searchTerm={messageSearchTerm}
                />
              ) : (
                <p>
                  <HighlightedText
                    text={message.content}
                    searchTerm={messageSearchTerm}
                  />
                </p>
              )}
              
            </div>
          ))}

          {normalizedSearchTerm && visibleChatMessages.length === 0 && (
            <p className="workspace-empty-search">
              No messages found for “{messageSearchTerm}”.
            </p>
          )}

        </section>

        <form className="chat-input-bar" onSubmit={handleSendMessage}>
          <input
            type="text"
            placeholder="Ask about your lesson..."
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
          />

          <button type="submit" disabled={isSending}>
            {isSending ? "Sending..." : "Send"}
          </button>
        </form>

        {errorMessage && (
          <p className="workspace-error-message">{errorMessage}</p>
        )}
      </section>

      <aside className="study-panel">
        <section className="tracker-card streak-card">
          <p className="card-label">Current streak</p>
          <h2>5 days</h2>
          <span>Keep showing up. Small steps count.</span>
        </section>

        <section className="tracker-card">
          <div className="calendar-header">
            <h2>May 2026</h2>
            <span>Learning calendar</span>
          </div>

          <div className="calendar-weekdays">
            <span>S</span>
            <span>M</span>
            <span>T</span>
            <span>W</span>
            <span>T</span>
            <span>F</span>
            <span>S</span>
          </div>

          <div className="calendar-grid">
            {calendarDays.map((day, index) => (
              <div
                className={`calendar-day ${
                  ["6", "7", "9", "13", "14", "16", "20"].includes(day)
                    ? "active-day"
                    : ""
                }`}
                key={`${day}-${index}`}
              >
                {day}
              </div>
            ))}
          </div>
        </section>

        <section className="tracker-card progress-card">
          <div className="progress-heading">
            <p className="card-label">Weekly goal</p>
            <strong>70%</strong>
          </div>

          <div className="progress-bar">
            <div className="progress-fill"></div>
          </div>

          <p className="progress-note">
            You completed 7 of 10 planned study sessions.
          </p>
        </section>

        <section className="tracker-card encouragement-card">
          <h2>One step at a time</h2>
          <p>
            When you feel stuck, ask for a hint, not the answer. That is how the
            learning sticks.
          </p>
        </section>
      </aside>
    </main>
  );
}

export default LearningWorkspace;