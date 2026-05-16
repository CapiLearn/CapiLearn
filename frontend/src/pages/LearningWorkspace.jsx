import { useState } from "react";
import { Link } from "react-router-dom";
import { createConversation, createMessage } from "../services/conversationService";
import "../styles/LearningWorkspace.css";

const recentChats = [
  {
    label: "Today",
    items: ["Gradient descent confusion", "RAG evaluation questions"],
  },
  {
    label: "Yesterday",
    items: ["Python decorator review", "Model monitoring notes"],
  },
  {
    label: "Last week",
    items: ["FastAPI readiness probes", "Postgres vector search"],
  },
];

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

function LearningWorkspace() {
  const [conversationId, setConversationId] = useState(null);

  const [chatMessages, setChatMessages] = useState([
    {
      id: "mock-user-1",
      role: "user",
      content: "I’m stuck on the assignment. I don’t know where to start.",
    },
    {
      id: "mock-assistant-1",
      role: "assistant",
      content:
        "Let’s slow it down. What part feels unclear: the instructions, the code structure, or the concept being tested?",
    },
  ]);

  const [inputValue, setInputValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSendMessage(event) {
    event.preventDefault();

    const trimmedMessage = inputValue.trim();

    if (!trimmedMessage) {
      return;
    }

    try {
      setIsSending(true);
      setErrorMessage("");

      let data;

      if (conversationId) {
        data = await createMessage(conversationId, trimmedMessage);
      } else {
        data = await createConversation(trimmedMessage);
        setConversationId(data.conversation.id);
      }

      setChatMessages((currentMessages) => [
        ...currentMessages,
        data.userMessage,
        data.assistantMessage,
      ]);

      setInputValue("");
    } catch (error) {
      setErrorMessage(error.message || "Unable to send message.");
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className="workspace-page">
      <aside className="workspace-sidebar">
        <div className="workspace-brand">
          <div className="workspace-brand-icon">♧</div>
          <span>CapiLearn</span>
        </div>

        <button className="new-chat-button">+ New conversation</button>

        <div className="search-box">
          <span>⌕</span>
          <input type="text" placeholder="Search conversations" />
        </div>

        <div className="chat-history">
          {recentChats.map((group) => (
            <section className="chat-group" key={group.label}>
              <h3>{group.label}</h3>

              {group.items.map((item) => (
                <button className="chat-history-item" key={item}>
                  {item}
                </button>
              ))}
            </section>
          ))}
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

        <section className="chat-preview">
          {chatMessages.map((message) => (
            <div
              className={`message ${
                message.role === "user" ? "student-message" : "tutor-message"
              }`}
              key={message.id}
            >
              <p>{message.content}</p>
            </div>
          ))}
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