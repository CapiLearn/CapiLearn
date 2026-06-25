import { useEffect, useMemo, useRef, useState } from "react";
import CitedMarkdownMessage from "../components/CitedMarkdownMessage";
import { useAuth } from "@clerk/react";
import capiCoffeeIcon from "../assets/capi_coffee_icon.png";
import capiBooksIcon from "../assets/capi_books.png";
import LogoutButton from "../components/LogoutButton";

import {
  createConversation,
  createMessage,
  listConversations,
  listMessages,
} from "../services/conversationService";
import {
  getActivityCalendar,
  recordLoginActivity,
} from "../services/activityService";

import "../styles/LearningWorkspace.css";

const initialChatMessages = [];

/**
 * LearningWorkspace is the main student chat surface.
 *
 * It coordinates authenticated conversation history, course-grounded assistant
 * responses, citation rendering, message search, and learning-activity
 * tracking. API request construction stays in the service layer so this page
 * can stay focused on user workflow and state transitions.
 */
function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeVisibleText(value) {
  return value.replace(/\s+/g, " ").trim();
}

function createTextProtector() {
  const protectedTexts = [];

  function protect(value) {
    const placeholder = `\uE000${protectedTexts.length}\uE001`;
    protectedTexts.push(value);

    return placeholder;
  }

  function restore(value) {
    return value.replace(/\uE000(\d+)\uE001/g, (_, index) =>
      protectedTexts[Number(index)] || ""
    );
  }

  return {
    protect,
    restore,
  };
}

function isMarkdownTableDivider(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function isMarkdownTableRow(line) {
  const trimmedLine = line.trim();

  return (
    trimmedLine.startsWith("|") &&
    trimmedLine.endsWith("|") &&
    trimmedLine.slice(1, -1).includes("|")
  );
}

function getVisibleMarkdownText(content) {
  const protector = createTextProtector();

  // Search should match what students can read, without counting Markdown
  // syntax or table divider rows as answer text.
  const protectedContent = content
    .replace(/```[\s\S]*?```/g, (match) => {
      const codeBlockText = match
        .replace(/^```[^\n]*\n?/, "")
        .replace(/\n?```$/, "");

      return protector.protect(codeBlockText);
    })
    .replace(/`([^`]+)`/g, (_, inlineCodeText) =>
      protector.protect(inlineCodeText)
    );

  const visibleLines = protectedContent
    .replace(/!\[[^\]]*]\([^)]+\)/g, "")
    .replace(/\[([^\]]+)]\([^)]+\)/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/~~([^~]+)~~/g, "$1")
    .split(/\n+/)
    .flatMap((line) => {
      const cleanedLine = line
        .replace(/^#{1,6}\s+/g, "")
        .replace(/^>\s?/g, "")
        .replace(/^\s*[-*+]\s+/g, "")
        .replace(/^\s*\d+\.\s+/g, "");

      if (isMarkdownTableDivider(cleanedLine)) {
        return [];
      }

      if (isMarkdownTableRow(cleanedLine)) {
        return cleanedLine
          .slice(1, -1)
          .split("|")
          .map((cell) => cell.trim())
          .filter(Boolean);
      }

      return [cleanedLine];
    })
    .join(" ");

  return normalizeVisibleText(protector.restore(visibleLines));
}

function getVisibleMessageText(message) {
  return message.role === "assistant"
    ? getVisibleMarkdownText(message.content)
    : message.content;
}

function countSearchMatchesInText(text, searchTerm) {
  if (!searchTerm) {
    return 0;
  }

  const escapedSearchTerm = escapeRegExp(searchTerm);
  const matches = text.match(new RegExp(escapedSearchTerm, "gi"));

  return matches ? matches.length : 0;
}

function HighlightedText({ text, searchTerm }) {
  const normalizedSearchTerm = searchTerm.trim();

  if (!normalizedSearchTerm) {
    return text;
  }

  const escapedSearchTerm = escapeRegExp(normalizedSearchTerm);
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

function getCalendarDays(date) {
  const year = date.getFullYear();
  const month = date.getMonth();

  const firstDayOfMonth = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const leadingBlankDays = Array.from({ length: firstDayOfMonth }, () => "");
  const monthDays = Array.from({ length: daysInMonth }, (_, index) =>
    String(index + 1)
  );

  const totalCalendarCells = leadingBlankDays.length + monthDays.length;
  const trailingBlankCount = (7 - (totalCalendarCells % 7)) % 7;
  const trailingBlankDays = Array.from({ length: trailingBlankCount }, () => "");

  return [...leadingBlankDays, ...monthDays, ...trailingBlankDays];
}

function formatCalendarTitle(date) {
  return date.toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });
}

function toDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function getCurrentMonthRange() {
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0);

  return {
    fromDate: toDateKey(firstDay),
    toDate: toDateKey(lastDay),
  };
}

/**
 * Learning workspace page for student chat.
 *
 * Handles conversation creation, follow-up messages, sidebar conversation
 * selection, new conversation reset behavior, assistant response display,
 * and learning streak activity.
 */

function LearningWorkspace() {
  const [conversationId, setConversationId] = useState(null);
  const [chatMessages, setChatMessages] = useState(initialChatMessages);
  const activeConversationIdRef = useRef(null);
  const hasRecordedLoginRef = useRef(false);

  const [inputValue, setInputValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [conversations, setConversations] = useState([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [messageSearchTerm, setMessageSearchTerm] = useState("");
  const [conversationSearchTerm, setConversationSearchTerm] = useState("");
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [currentStreak, setCurrentStreak] = useState(null);
  const [activityDays, setActivityDays] = useState([]);
  const [activityError, setActivityError] = useState("");

  useEffect(() => {
    async function loadConversations() {
      try {
        setIsLoadingConversations(true);

        const data = await listConversations(getToken);

        setConversations(data.conversations || []);
      } catch (error) {
        setErrorMessage(error.message || "Unable to load conversations.");
      } finally {
        setIsLoadingConversations(false);
      }
    }

    loadConversations();
  }, [getToken]);

  useEffect(() => {
    const timerId = setInterval(() => {
      setCurrentDate(new Date());
    }, 60 * 1000);

    return () => clearInterval(timerId);
  }, []);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }

    let isMounted = true;

    async function loadActivity() {
      try {
        setActivityError("");

        const token = await getToken();

        if (!token) {
          if (isMounted) {
            setActivityError("Unable to load activity. Please sign in again.");
          }
          return;
        }

        if (!hasRecordedLoginRef.current) {
          hasRecordedLoginRef.current = true;
          const loginActivity = await recordLoginActivity(token);

          if (!isMounted) {
            return;
          }

          setCurrentStreak(loginActivity.currentStreak);
        }

        const calendarRange = getCurrentMonthRange();
        const calendarActivity = await getActivityCalendar(token, calendarRange);

        if (!isMounted) {
          return;
        }

        setCurrentStreak(calendarActivity.currentStreak);
        setActivityDays(calendarActivity.days || []);
      } catch (error) {
        if (isMounted) {
          setActivityError(error.message || "Unable to load activity.");
        }
      }
    }

    loadActivity();

    return () => {
      isMounted = false;
    };
  }, [getToken, isLoaded, isSignedIn]);

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
        const data = await createMessage(
          targetConversationId,
          trimmedMessage,
          getToken
        );

        if (activeConversationIdRef.current === targetConversationId) {
          setChatMessages((currentMessages) => [
            ...currentMessages,
            data.userMessage,
            data.assistantMessage,
          ]);
        }
      } else {
        const data = await createConversation(trimmedMessage, getToken);
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
      const data = await listMessages(selectedConversationId, getToken);

      if (activeConversationIdRef.current !== selectedConversationId) {
        return;
      }

      setChatMessages(data.messages || []);
    } catch (error) {
      if (activeConversationIdRef.current === selectedConversationId) {
        setErrorMessage(
          error.message || "Unable to load conversation messages."
        );
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

  const normalizedSearchTerm = messageSearchTerm.trim();

  const visibleChatMessages = normalizedSearchTerm
    ? chatMessages.filter((message) =>
        getVisibleMessageText(message)
          .toLowerCase()
          .includes(normalizedSearchTerm.toLowerCase())
      )
    : chatMessages;

  const searchMatchCount = normalizedSearchTerm
    ? visibleChatMessages.reduce(
        (count, message) =>
          count +
          countSearchMatchesInText(
            getVisibleMessageText(message),
            normalizedSearchTerm
          ),
        0
      )
    : 0;

  const calendarDays = useMemo(
    () => getCalendarDays(currentDate),
    [currentDate]
  );

  const calendarTitle = formatCalendarTitle(currentDate);
  const activeDateKeys = useMemo(
    () => new Set(activityDays.map((activityDay) => activityDay.date)),
    [activityDays]
  );

  function getCalendarDateKey(day) {
    if (!day) {
      return "";
    }

    const calendarDate = new Date(
      currentDate.getFullYear(),
      currentDate.getMonth(),
      Number(day)
    );

    return toDateKey(calendarDate);
  }

  return (
    <main className="workspace-page">
      <aside className="workspace-sidebar">
        <div className="workspace-brand">
          <img
            src={capiCoffeeIcon}
            alt=""
            className="workspace-brand-icon"
            aria-hidden="true"
          />
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
                    conversation.id === conversationId
                      ? "active-conversation"
                      : ""
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

        <LogoutButton className="workspace-logout-link" />
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
        </header>

        <section className="welcome-card">
          <img
            src={capiBooksIcon}
            alt=""
            className="capi-avatar"
            aria-hidden="true"
          />

          <div>
            <h2>Hi, I'm Capi.</h2>
            <p>
              I can help you review lessons, reason through problems, and find
              the right course material. I won't give direct answers, but I'll
              help you think through the next step.
            </p>
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
                <CitedMarkdownMessage
                  content={message.content}
                  citations={message.citations || []}
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
              No messages found for "{messageSearchTerm}".
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
          <h2>{currentStreak ?? "--"} days</h2>
          {activityError && <p className="tracker-error">{activityError}</p>}
          <span>Keep showing up. Small steps count.</span>
        </section>

        <section className="tracker-card">
          <div className="calendar-header">
            <h2>{calendarTitle}</h2>
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
                  activeDateKeys.has(getCalendarDateKey(day)) ? "active-day" : ""
                }`}
                key={`${day}-${index}`}
              >
                {day}
              </div>
            ))}
          </div>
        </section>
      </aside>
    </main>
  );
}

export default LearningWorkspace;
