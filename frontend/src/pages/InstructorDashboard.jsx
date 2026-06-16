import { Link } from "react-router-dom";
import "../styles/InstructorDashboard.css";

const summaryStats = [
  {
    label: "Active students",
    value: "18",
    helper: "Students active this week",
  },
  {
    label: "Questions asked",
    value: "142",
    helper: "Across all learning sessions",
  },
];

const commonContexts = [
  {
    context: "Ipsum Lorem...",
    count: 38,
    percentage: 78,
  },
  {
    context: "Ipsum Lorem...",
    count: 31,
    percentage: 64,
  },
  {
    context: "Ipsum Lorem...",
    count: 24,
    percentage: 50,
  },
  {
    context: "Ipsum Lorem...",
    count: 19,
    percentage: 39,
  },
  {
    context: "Ipsum Lorem...",
    count: 15,
    percentage: 31,
  },
];

const studentRoster = [
  {
    name: "John Carter",
    topTopic: "Ipsum Lorem",
    questions: 18,
    streak: "4 days",
    lastActive: "Today",
  },
  {
    name: "Maya Singh",
    topTopic: "Ipsum Lorem",
    questions: 9,
    streak: "1 day",
    lastActive: "Yesterday",
  },
  {
    name: "Luis Rivera",
    topTopic: "Ipsum Lorem",
    questions: 14,
    streak: "5 days",
    lastActive: "Today",
  },
  {
    name: "Ava Thompson",
    topTopic: "Ipsum Lorem",
    questions: 6,
    streak: "6 days",
    lastActive: "Today",
  },
  {
    name: "Noah Kim",
    topTopic: "Ipsum Lorem",
    questions: 7,
    streak: "3 days",
    lastActive: "2 days ago",
  },
];

const instructorNavItems = [
  { id: "dashboard-summary", label: "Dashboard" },
  { id: "student-roster", label: "Students" },
  { id: "common-contexts", label: "Top Context" },
];

function scrollToSection(sectionId) {
  document.getElementById(sectionId)?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

function InstructorDashboard() {
  return (
    <main className="instructor-page">
      <aside className="instructor-sidebar">
        <div className="instructor-brand">
          <div className="instructor-brand-icon">♧</div>
          <span>CapiLearn</span>
        </div>

        <nav className="instructor-nav">
          {instructorNavItems.map((item, index) => (
            <button
              className={index === 0 ? "active" : ""}
              key={item.id}
              type="button"
              onClick={() => scrollToSection(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <Link className="instructor-logout-link" to="/">
          Log out
        </Link>

        <div className="instructor-profile-card">
          <div className="instructor-avatar">O</div>
          <div>
            <h3>Trogdor (He/Him/Burninator)</h3>
            <p>FCF Instructor</p>
          </div>
        </div>
      </aside>

      <section className="instructor-main">
        <header className="instructor-header" id="dashboard-summary">
          <div>
            <p className="instructor-kicker">Instructor Dashboard</p>
            <h1>Student learning insights</h1>
          </div>
        </header>

        <section className="instructor-stat-grid">
          {summaryStats.map((stat) => (
            <article className="instructor-stat-card" key={stat.label}>
              <p>{stat.label}</p>
              <h2>{stat.value}</h2>
              <span>{stat.helper}</span>
            </article>
          ))}
        </section>

        <section className="instructor-panel roster-panel" id="student-roster">
          <div className="panel-header">
            <div>
              <p className="panel-label">Student Roster</p>
              <h2>Student activity overview</h2>
            </div>
            <button className="small-outline-button">View all students</button>
          </div>

          <div className="roster-table-wrapper">
            <table className="roster-table">
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Top topic</th>
                  <th>Questions</th>
                  <th>Streak</th>
                  <th>Last active</th>
                </tr>
              </thead>

              <tbody>
                {studentRoster.map((student) => (
                  <tr key={student.name}>
                    <td>
                      <div className="student-cell">
                        <div className="student-initial">
                          {student.name.charAt(0)}
                        </div>
                        <span>{student.name}</span>
                      </div>
                    </td>
                    <td>{student.topTopic}</td>
                    <td>{student.questions}</td>
                    <td>{student.streak}</td>
                    <td>{student.lastActive}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="instructor-content-grid">
          <article
            className="instructor-panel topic-panel"
            id="common-contexts"
          >
            <div className="panel-header">
              <div>
                <p className="panel-label">Top 5 Common Context Retrieved</p>
                <h2>Most retrieved learning context</h2>
              </div>
            </div>

            <div className="topic-list">
              {commonContexts.map((context) => (
                <div className="topic-row" key={context.context}>
                  <div className="topic-info">
                    <h3>{context.context}</h3>
                    <p>{context.count} retrievals</p>
                  </div>

                  <div className="topic-bar-block">
                    <div className="topic-bar">
                      <div
                        className="topic-fill"
                        style={{ width: `${context.percentage}%` }}
                      ></div>
                    </div>
                    <span>{context.percentage}%</span>
                  </div>
                </div>
              ))}
            </div>
          </article>
        </section>
      </section>
    </main>
  );
}

export default InstructorDashboard;